# -*- coding: utf-8 -*-
"""电商提示词工作台统一 CLI：原子检索、取模板、提示词校验、出图机检。

为什么有它：不接任何 agent 平台时，拿一条模板要走四步——读 SKILL.md、判工位、读
_atoms/aNN.json、从 templates 挑一个，全靠模型自觉，任一步错就取错。这里把四步压成
一条命令，输出 JSON，供人或任意 agent 直接消费。

四个子命令都是现有脚本与索引的薄包装，不引入新判据：
  query-atom       按品类/产物/动作定位原子（读 index.json，不做语义猜测）
  get-template     取原子里的模板 + 该原子的规则、清单、占位符
  validate-prompt  跑 slop_check，可选按平台/场景/品类跑 rules_engine
  check-output     跑 check_image 做平台机检

用法：
  python tools/cli.py query-atom --category 杯壶 --output 主图
  python tools/cli.py get-template --atom a21 --index 0
  python tools/cli.py validate-prompt --file prompt.txt --platform amazon
  python tools/cli.py check-output out/main-01.png --platform amazon --strict
  python tools/cli.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SOP_DIR = REPO_ROOT / "skills" / "ecom-prompt-sop"
ATOM_DIR = SOP_DIR / "references" / "_atoms"
INDEX_JSON = ATOM_DIR / "index.json"


def _load_index():
    if not INDEX_JSON.exists():
        return []
    return json.loads(INDEX_JSON.read_text(encoding="utf-8")).get("items") or []


def _haystack(atom):
    """索引里 categories 常为空，真实可用的匹配面是标题、任务、标签三者合并。"""
    parts = [atom.get("title") or "", atom.get("task") or ""]
    parts.extend(atom.get("tags") or [])
    parts.extend(atom.get("categories") or [])
    return " ".join(parts)


def _score(atom, category, output, action, text):
    """按索引里的结构化字段打分。命中即有依据，不猜。"""
    score = 0
    hay = _haystack(atom)
    if category and category in hay:
        score += 40
    if output:
        outs = atom.get("outputs") or []
        if any(output in o for o in outs):
            score += 25
        elif output and output in hay:
            score += 15
    if action and action in hay:
        score += 25
    if text:
        for ch in text:
            if ch.strip() and ch in hay:
                score += 1
    return min(score, 90)


def query_atom(args):
    atoms = _load_index()
    if not atoms:
        return {"error": "原子索引缺失，先跑 python tools/atomize.py merge"}

    scored = []
    for a in atoms:
        s = _score(a, (args.category or "").strip(), (args.output or "").strip(),
                   (args.action or "").strip(), (args.text or "").strip())
        if s > 0:
            scored.append((s, a))
    scored.sort(key=lambda x: -x[0])

    if not scored:
        return {
            "hits": [],
            "note": "没有原子命中。检查品类是否在 34 篇覆盖范围内，或改用通用篇（a01/a02/a03）。",
        }

    hits = [{
        "atom": a.get("id"),
        "title": a.get("title"),
        "stations": a.get("stations"),
        "outputs": a.get("outputs"),
        "task": a.get("task"),
        "score": s,
    } for s, a in scored[: args.limit]]
    return {"hits": hits, "total_matched": len(scored)}


def get_template(args):
    if not args.atom:
        return {"error": "缺少 --atom，例如 a21"}

    path = ATOM_DIR / f"{args.atom}.json"
    if not path.exists():
        return {"error": f"原子不存在：{args.atom}"}

    atom = json.loads(path.read_text(encoding="utf-8"))
    templates = atom.get("templates") or []
    picked = templates
    if args.index is not None:
        if args.index < 0 or args.index >= len(templates):
            return {"error": f"index 越界：{args.index}，该原子有 {len(templates)} 个模板"}
        picked = [templates[args.index]]

    return {
        "atom": args.atom,
        "title": atom.get("title"),
        "stations": atom.get("stations"),
        "template_count": len(templates),
        "templates": picked,
        "rules": atom.get("rules") or [],
        "checklists": atom.get("checklists") or [],
        "placeholders": atom.get("placeholders") or [],
    }


def _run_script(script, argv, timeout=60):
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / script)] + argv,
            capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
        return {"exit": p.returncode, "stdout": (p.stdout or "").strip(), "stderr": (p.stderr or "").strip()}
    except subprocess.TimeoutExpired:
        return {"exit": -1, "stdout": "", "stderr": f"{script} 超时（{timeout}s）"}
    except OSError as e:
        return {"exit": -1, "stdout": "", "stderr": f"{script} 无法执行：{e}"}


def validate_prompt(args):
    prompt = args.prompt
    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    if not (prompt or "").strip():
        return {"error": "缺少提示词：用 --file 指定文件或从 stdin 传入"}

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(prompt)
        tmp = f.name

    try:
        out = {"slop": _run_script("slop_check.py", [tmp, "--json"])}
        if args.platform and args.slots:
            # 规则引擎校验的是槽位而不是自由文本，两个都给了才跑
            out["rules"] = _run_script("rules_engine.py", [
                "--check", args.slots, "--platform", args.platform,
                *(["--scenario", args.scenario] if args.scenario else []),
                *(["--category", args.category] if args.category else []),
            ])
        elif args.platform:
            out["rules"] = {"skipped": "未提供 --slots，跳过规则引擎（它校验槽位而非自由文本）"}
        else:
            out["rules"] = {"skipped": "未提供 --platform，跳过规则引擎"}
        return out
    finally:
        Path(tmp).unlink(missing_ok=True)


def check_output(args):
    if not Path(args.image).exists():
        return {"error": f"图片不存在：{args.image}"}
    argv = [args.image, "--platform", args.platform, "--json"]
    if args.strict:
        argv.append("--strict")
    return _run_script("check_image.py", argv, timeout=120)


def find_rule(args):
    """按关键词或 id 查规则，返回规则全文与所属原子。

    规则全文只在原子里存一份，rules.json 只做定位——这里按 id 回原子取正文。
    """
    if not args.query:
        return {"error": "缺少 --query（关键词或规则 id）"}

    path = ATOM_DIR / "rules.json"
    if not path.exists():
        return {"error": "规则索引缺失，先跑 python tools/atomize.py merge"}

    items = json.loads(path.read_text(encoding="utf-8")).get("items") or []
    q = args.query.strip()
    hits = [r for r in items if q in r["id"]] if q.startswith("a") and ".r" in q else items

    if not (q.startswith("a") and ".r" in q):
        # 关键词模式：回原子取正文后匹配，而不是只匹配索引字段
        found = []
        cache = {}
        for r in items:
            aid = r["atom"]
            if aid not in cache:
                ap = ATOM_DIR / f"{aid}.json"
                cache[aid] = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else {}
            text = next((x["text"] for x in cache[aid].get("rules") or [] if x["id"] == r["id"]), "")
            if q in text:
                found.append({**r, "text": text})
        hits = found

    out = []
    for r in hits[: args.limit]:
        aid = r["atom"]
        ap = ATOM_DIR / f"{aid}.json"
        text = r.get("text")
        if text is None and ap.exists():
            atom = json.loads(ap.read_text(encoding="utf-8"))
            text = next((x["text"] for x in atom.get("rules") or [] if x["id"] == r["id"]), "")
        out.append({
            "id": r["id"], "atom": aid, "atom_title": r.get("title"),
            "line": r.get("line"), "stations": r.get("stations"),
            "categories": r.get("categories"), "text": text,
        })
    return {"query": q, "hits": out, "total_matched": len(hits)}


def build_parser():
    ap = argparse.ArgumentParser(
        prog="cli.py",
        description="电商提示词工作台 CLI：原子检索 / 取模板 / 提示词校验 / 出图机检",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("query-atom", help="按品类/产物/动作定位原子")
    p.add_argument("--category", help="品类，如 百货杯壶、美妆日化、服饰")
    p.add_argument("--output", help="产物，如 主图、详情页、SKU图、模特图、视频")
    p.add_argument("--action", help="动作，如 生成、反推、翻新、批量、翻译")
    p.add_argument("--text", help="用户原话，用于关键词兜底打分")
    p.add_argument("--limit", type=int, default=3, help="最多返回几条，默认 3")
    p.set_defaults(func=query_atom)

    p = sub.add_parser("get-template", help="取原子的模板、规则、清单与占位符")
    p.add_argument("--atom", required=True, help="原子编号，如 a21")
    p.add_argument("--index", type=int, help="只取第几个模板（从 0 开始）")
    p.set_defaults(func=get_template)

    p = sub.add_parser("validate-prompt", help="反 AI 感自查 + 可选规则引擎校验")
    p.add_argument("--file", help="提示词文件路径；省略则从 stdin 读")
    p.add_argument("--platform", help="平台 id，如 amazon")
    p.add_argument("--scenario", help="场景，如 首图")
    p.add_argument("--category", help="品类")
    p.add_argument("--slots", help="五槽位 JSON 文件路径；提供后才跑规则引擎")
    p.set_defaults(func=validate_prompt)

    p = sub.add_parser("check-output", help="出图后平台机检")
    p.add_argument("image", help="图片路径")
    p.add_argument("--platform", required=True, help="平台 id，如 amazon、taobao、tmall")
    p.add_argument("--strict", action="store_true", help="严格模式：警告也算失败")
    p.set_defaults(func=check_output)

    p = sub.add_parser("find-rule", help="按关键词或规则 id 查规则全文与所属原子")
    p.add_argument("--query", required=True, help="关键词，或规则 id（如 a21.re5d4b02d34f3）")
    p.add_argument("--limit", type=int, default=5, help="最多返回几条，默认 5")
    p.set_defaults(func=find_rule)

    return ap


def selftest():
    """离线自检：不打网络、不碰真实密钥，只验索引与原子可读。"""
    fails = []
    atoms = _load_index()
    if len(atoms) != 34:
        fails.append(f"原子索引应为 34 条，实际 {len(atoms)}")

    ns = argparse.Namespace(category="杯壶", output="主图", action=None, text=None, limit=3)
    hits = query_atom(ns).get("hits") or []
    if not hits:
        fails.append("query-atom 对「杯壶+主图」无命中")
    elif hits[0]["atom"] != "a21":
        fails.append(f"杯壶主图应首选 a21，实际 {hits[0]['atom']}")

    tpl = get_template(argparse.Namespace(atom="a21", index=0))
    if not tpl.get("templates"):
        fails.append("get-template 取 a21 模板失败")
    if tpl.get("error"):
        fails.append(f"get-template 报错：{tpl['error']}")

    miss = get_template(argparse.Namespace(atom="a99", index=None))
    if not miss.get("error"):
        fails.append("不存在的原子应返回 error")

    ns = argparse.Namespace(prompt="8k masterpiece 极致完美的保温杯主图", file=None,
                            platform=None, scenario=None, category=None, slots=None)
    v = validate_prompt(ns)
    stdout = (v["slop"].get("stdout") or "")
    if "空洞堆词" not in stdout and '"warn": 4' not in stdout.replace(",", "").replace(" ", ""):
        fails.append("堆词提示词应被 slop_check 报出空洞堆词")

    # 规则索引：571 条必须全在，且能按关键词回查正文
    rules_json = ATOM_DIR / "rules.json"
    if not rules_json.exists():
        fails.append("规则索引 rules.json 缺失，跑 atomize.py merge")
    else:
        idx = json.loads(rules_json.read_text(encoding="utf-8"))
        if idx.get("count") != 571:
            fails.append(f"规则索引应 571 条，实际 {idx.get('count')}")
        got = find_rule(argparse.Namespace(query="白底", limit=3))
        if not got.get("hits"):
            fails.append("find-rule 对「白底」无命中")
        elif not any("白底" in (h.get("text") or "") for h in got["hits"]):
            fails.append("find-rule 返回的规则正文不含关键词")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 索引、定位、取模板、堆词拦截 全部通过")
    return 0


def main(argv=None):
    if "--selftest" in (argv if argv is not None else sys.argv):
        return selftest()

    args = build_parser().parse_args(argv)
    if args.cmd == "validate-prompt" and not args.file:
        args.prompt = sys.stdin.read()
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
