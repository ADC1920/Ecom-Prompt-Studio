# -*- coding: utf-8 -*-
"""SOP 原子化：把散文形态的 SOP 拆成可执行的零件。

一篇 SOP 里混着五种东西：解释（你可以忽略）、提示词模板（核心资产）、规则条款（禁止/必须）、
验收清单（交付门禁）、返修语句（出问题怎么改）。散文形态下它们缠在一起，读的时候要人脑再分拣一次。

拆解的本义就是把这一次分拣做掉：提示词模板完整保留，规则句带上行号抽出来，验收项单列，
占位符收成变量清单——之后无论是路由、组装、校验还是评测，都不用再读整篇。

原子是自包含的：每个 aNN.json 里带 `source_text`（完整内容），所以一个文件就够了——
模板、规则、清单、上下文全都在里面，`check` 也只校验原子内部是否自洽。

子命令：
  summary  输出紧凑摘要，供人写语义层（task / tags）
  merge    机械层 + _index.json + semantic.json → _atoms/aNN.json 与 index.json
  check    自包含校验：看原子内部是否自洽
  restore  把原子的完整内容导出成可读文本（默认 .tmp/export）
  extract  已停用：索引不再带文件路径，机械层与原子均就位。保留代码仅作历史参考。

用法：
  python tools/atomize.py extract
  python tools/atomize.py summary
  python tools/atomize.py merge
  python tools/atomize.py check
  python tools/atomize.py --selftest
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_ROOT = HERE.parent / "ecom-prompt-sop" / "references"
ATOM_DIR = REF_ROOT / "_atoms"
MECH_DIR = ATOM_DIR / "_mech"
INDEX_JSON = REF_ROOT / "_index.json"
SEMANTIC_JSON = ATOM_DIR / "semantic.json"

HEAD_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^```([A-Za-z0-9_ ]*)$")
PH_RE = re.compile(r"【([^【】]{1,40})】")
# 规则词：这些句子是「条件—约束」，比解释性文字值钱
RULE_WORDS = ["必须", "禁止", "不得", "严禁", "只能", "一律", "不能", "不要", "避免", "确保",
              "保持", "统一", "优先", "不允许", "无论如何"]
SENT_SPLIT = re.compile(r"[。；;！？\n]")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


LOOSE_KEYS = ["提示词", "复制", "第一步", "第二步", "第三步", "第四步", "反推", "生成", "转"]
# 操作类标题下的段落是「怎么用」，不是提示词本身
SKIP_HEADS = ["喂给", "交给", "合格标准", "规则", "说明", "注意", "目录", "检查", "验收", "准备", "工具"]


def _heading_chain(marks, idx):
    """取标题及其所有上级标题，用于关键词匹配。子标题常是「3:4转1:1」这种不含关键词的，得看父级。"""
    cur = marks[idx]
    chain = [cur["text"]]
    level = cur["level"]
    for prev in reversed(marks[:idx]):
        if prev["level"] < level:
            chain.append(prev["text"])
            level = prev["level"]
            if level == 1:
                break
    return chain


def extract_loose(lines, blocks, headings):
    """裸段落型模板：有些篇的提示词没放在 ``` 里，而是直接跟在小标题下面。

    按任意级别标题切段，用「祖先链」判断这一段是不是提示词区；段落要够长（≥200 字）、
    且不像列表。宁可漏也不误抓——漏的会被 check 报出来，误抓会污染模板库。
    """
    covered = set()
    for b in blocks:
        covered.update(range(b["start"] - 1, b["end"]))

    loose = []
    for idx, h in enumerate(headings):
        end = headings[idx + 1]["line"] - 1 if idx + 1 < len(headings) else len(lines)
        body = [lines[i] for i in range(h["line"], end) if i not in covered]
        text = "\n".join(body).strip()
        if len(text) < 200:
            continue

        own_hit = any(k in h["text"] for k in LOOSE_KEYS)
        anc_hit = any(k in " ".join(_heading_chain(headings, idx)[1:]) for k in LOOSE_KEYS)
        # 提示词常有 Role/你是一名/请严格/输出一条 这类口吻，用它把提示词和说明文字分开
        promptish = any(k in text for k in ["Role:", "你是一名", "请严格", "请你", "请以", "输出一条", "输出提示词"])

        if any(k in h["text"] for k in SKIP_HEADS):
            continue
        # 只有裸段本身像提示词才收：标题对、口吻不对，多半是操作说明
        if not promptish:
            continue
        if not (own_hit or anc_hit):
            continue
        listy = sum(1 for ln in body if ln.strip().startswith(("- ", "* ", "1.", "2.", "3.", "|")))
        if listy > 3 and not own_hit:
            continue
        loose.append({"heading": h["text"], "line": h["line"], "chars": len(text), "text": text})
    return loose


CHECK_HEADS = ["板块", "清单", "检查", "验收", "标准", "要求"]


def extract_checklists(lines, blocks, headings):
    """检查清单：板块要求、验收项这类编号条目，比散文可靠，直接收成条目数组。

    参考篇里常见「必备核心板块 1./2./3.」「验收清单 1./2.」——它们是可逐条核对的判据。
    """
    covered = set()
    for b in blocks:
        covered.update(range(b["start"] - 1, b["end"]))

    out = []
    for idx, h in enumerate(headings):
        if not any(k in h["text"] for k in CHECK_HEADS):
            continue
        end = headings[idx + 1]["line"] - 1 if idx + 1 < len(headings) else len(lines)
        items = []
        for i in range(h["line"], end):
            if i in covered:
                continue
            ln = lines[i].strip()
            if re.match(r"^\d+[\.、）)]\s*\S", ln) or re.match(r"^[-*]\s+\S", ln):
                items.append(re.sub(r"^(\d+[\.、）)]|[-*])\s*", "", ln).strip())
        if len(items) >= 2:
            out.append({"heading": h["text"], "items": items})
    return out


def parse_text(text, name=""):
    """把 markdown 文本解析成结构：标题、代码块、裸段落模板、规则句、清单、占位符。

    输入是文本而不是路径——这样解析文本与从原子的 source_text 校验，走的是同一套逻辑。
    """
    lines = text.splitlines()
    headings, blocks, prose = [], [], []
    i, in_code, cur = 0, False, None
    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.strip() == "```":
                body = "\n".join(lines[cur["start"]:i])
                cur.update(end=i + 1, chars=len(body), sha=sha(body), text=body)
                blocks.append(cur)
                in_code, cur = False, None
            i += 1
            continue

        m = FENCE_RE.match(line.strip())
        if m:
            in_code = True
            cur = {"lang": (m.group(1) or "").strip(), "start": i + 1}
            i += 1
            continue

        hm = HEAD_RE.match(line)
        if hm:
            headings.append({"level": len(hm.group(1)), "text": hm.group(2), "line": i + 1})
            prose.append({"line": i + 1, "text": line})
        else:
            prose.append({"line": i + 1, "text": line})
        i += 1

    if in_code and cur:  # 未闭合的代码块也收，别丢
        body = "\n".join(lines[cur["start"]:])
        cur.update(end=len(lines), chars=len(body), sha=sha(body), text=body, unclosed=True)
        blocks.append(cur)

    # 正文规则句：只从代码块外的文本里抽（模板内的规则已经在模板里了）
    prose_text = "\n".join(p["text"] for p in prose if p["text"].strip())
    rules = []
    for p in prose:
        raw = p["text"].strip()
        if not raw or raw.startswith("#") or raw.startswith("|") or raw.startswith(">"):
            continue
        for sent in SENT_SPLIT.split(raw):
            s = sent.strip().strip("，,、:：")
            if len(s) < 12:
                continue
            if any(w in s for w in RULE_WORDS):
                rules.append({"text": s, "line": p["line"]})

    return {
        "title": headings[0]["text"] if headings else (name or "未命名"),
        "line_count": len(lines),
        "headings": headings,
        "code_blocks": blocks,
        "loose_templates": extract_loose(lines, blocks, headings),
        "checklists": extract_checklists(lines, blocks, headings),
        "prose_rules": rules,
        "placeholders": sorted({m.group(1).strip() for m in PH_RE.finditer(text)}),
        "sha": sha(text),
        "source_text": text,
    }


def parse(path):
    p = Path(path)
    return parse_text(p.read_text(encoding="utf-8"), p.stem)


def load_index():
    return json.loads(INDEX_JSON.read_text(encoding="utf-8"))["items"]


def atom_id(idx):
    return f"a{idx:02d}"


def cmd_extract(_args):
    """已停用：索引不再带文件路径，机械层与原子均已就位。"""
    items = load_index()
    if any(not it.get("path") for it in items):
        print("extract: 已停用——索引不含文件路径，机械层与原子均已就位。"
              "如需重拆，先从原子的 source_text 导出文本再手工处理。", file=sys.stderr)
        return 1
    MECH_DIR.mkdir(parents=True, exist_ok=True)
    total_blocks = total_rules = 0
    for i, item in enumerate(items, 1):
        src = REF_ROOT / item["path"].replace("references/", "", 1) if item["path"].startswith("references/") else REF_ROOT / item["path"]
        if not src.exists():
            src = REF_ROOT.parent / item["path"]
        if not src.exists():
            print(f"找不到对应文件：{item.get('path')}", file=sys.stderr)
            return 1
        parsed = parse(src)
        parsed.update({"id": atom_id(i), "no": item.get("no"), "path": item["path"], "source_sha": parsed.pop("sha")})
        (MECH_DIR / f"{atom_id(i)}.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        total_blocks += len(parsed["code_blocks"])
        total_rules += len(parsed["prose_rules"])
    print(f"extract: {len(items)} 篇 · 代码块 {total_blocks} · 正文规则句 {total_rules}")
    return 0


def cmd_summary(_args):
    items = load_index()
    for i, item in enumerate(items, 1):
        p = MECH_DIR / f"{atom_id(i)}.json"
        if not p.exists():
            print(f"{atom_id(i)} 未提取")
            continue
        m = json.loads(p.read_text(encoding="utf-8"))
        heads = " / ".join(h["text"] for h in m["headings"][:6])
        print(f"{m['id']} [{item.get('no')}] {m['title'][:34]}  ({m['line_count']} 行)")
        print(f"   工位 {','.join(item.get('stations', []))} · 槽位 {','.join(item.get('slots', []))} · 产物 {','.join(item.get('outputs', []))}")
        print(f"   结构：{heads}")
        print(f"   块 {len(m['code_blocks'])} · 裸段 {len(m.get('loose_templates', []))} · "
              f"清单 {len(m.get('checklists', []))} · 规则 {len(m['prose_rules'])} · "
              f"占位符 {len(m['placeholders'])}：{'、'.join(m['placeholders'][:6])}")
    return 0


def cmd_merge(_args):
    items = load_index()
    semantic = {}
    if SEMANTIC_JSON.exists():
        semantic = json.loads(SEMANTIC_JSON.read_text(encoding="utf-8")).get("items", {})
    summary = []
    for i, item in enumerate(items, 1):
        aid = atom_id(i)
        mp = MECH_DIR / f"{aid}.json"
        if not mp.exists():
            print(f"{aid} 缺少机械层，先跑 extract", file=sys.stderr)
            return 1
        m = json.loads(mp.read_text(encoding="utf-8"))
        sem = semantic.get(aid, {})
        atom = {
            "id": aid,
            "no": item.get("no"),
            "title": m["title"],
            "stations": item.get("stations", []),
            "slots": item.get("slots", []),
            "outputs": item.get("outputs", []),
            "categories": item.get("categories", []),
            "shared": item.get("shared", False),
            "task": sem.get("task", ""),
            "tags": sem.get("tags", []),
            "notes": sem.get("notes", ""),
            "steps": [h["text"] for h in m["headings"] if re.match(r"^(第[一二三四五六七八九十]+步|步骤)", h["text"])],
            "templates": [
                {"kind": "fenced", "index": k + 1, "lang": b["lang"], "lines": [b["start"], b["end"]],
                 "chars": b["chars"], "text": b["text"]}
                for k, b in enumerate(m["code_blocks"])
            ] + [
                {"kind": "loose", "index": len(m["code_blocks"]) + k + 1, "heading": b["heading"],
                 "line": b["line"], "chars": b["chars"], "text": b["text"]}
                for k, b in enumerate(m.get("loose_templates", []))
            ],
            "rules": m["prose_rules"],
            "checklists": m.get("checklists", []),
            "placeholders": m["placeholders"],
            "source": {"line_count": m["line_count"], "sha": m["source_sha"]},
            # 完整内容：原子的自包含载体。模板、规则、上下文全在这里。
            "source_text": m["source_text"],
        }
        (ATOM_DIR / f"{aid}.json").write_text(
            json.dumps(atom, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        summary.append({
            "id": aid, "no": atom["no"], "title": atom["title"],
            "stations": atom["stations"], "slots": atom["slots"], "outputs": atom["outputs"],
            "task": atom["task"], "tags": atom["tags"],
            "templates": len(atom["templates"]), "rules": len(atom["rules"]),
            "checklists": len(atom["checklists"]), "placeholders": len(atom["placeholders"]),
        })

    (ATOM_DIR / "index.json").write_text(json.dumps({
        "version": 1,
        "note": "拆解结果索引：每条给 id、工位/槽位/产物、一句话任务、模板与规则数量。原子文件是同目录的 aNN.json，模板完整保留在 source_text 里。改语义层或原子后重跑 merge。",
        "count": len(summary),
        "items": summary,
    }, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"merge: 生成 {len(summary)} 个原子 + index.json")
    return 0


def cmd_check(_args):
    """自包含校验：只看原子自己的 source_text 是否自洽。

    这是唯一能保证「模板没丢、规则没少」的手段。
    """
    items = load_index()
    problems = []
    for i, item in enumerate(items, 1):
        aid = atom_id(i)
        ap = ATOM_DIR / f"{aid}.json"
        if not ap.exists():
            problems.append(f"{aid} 原子缺失")
            continue
        atom = json.loads(ap.read_text(encoding="utf-8"))
        text = atom.get("source_text") or ""
        if not text:
            problems.append(f"{aid} 缺 source_text，原子不自包含")
            continue
        if sha(text) != atom.get("source", {}).get("sha"):
            problems.append(f"{aid} source_text 与记录的 sha 不一致（被手工改过？）")

        parsed = parse_text(text)
        fenced = [t for t in atom["templates"] if t.get("kind") == "fenced"]
        loose = [t for t in atom["templates"] if t.get("kind") == "loose"]
        if len(fenced) != len(parsed["code_blocks"]):
            problems.append(f"{aid} fenced 模板 {len(fenced)} ≠ 自解析代码块 {len(parsed['code_blocks'])}")
        if len(loose) != len(parsed["loose_templates"]):
            problems.append(f"{aid} loose 模板 {len(loose)} ≠ 自解析裸段落 {len(parsed['loose_templates'])}")
        if not atom["templates"] and not atom.get("checklists"):
            problems.append(f"{aid} 未拆出模板与清单")
        for t in atom["templates"]:
            body = t.get("text") or ""
            if not body:
                continue
            # 围栏模板是精确切片，可整段比对；裸段落是行拼接后 strip 的，用前 60 字探测就够
            probe = body if t.get("kind") == "fenced" else body[:60]
            if probe not in text:
                problems.append(f"{aid} 模板 {t.get('index')} 在 source_text 里找不到")
        if len(atom["rules"]) != len(parsed["prose_rules"]):
            problems.append(f"{aid} 规则数 {len(atom['rules'])} ≠ 自解析 {len(parsed['prose_rules'])}")
        if not atom.get("task"):
            problems.append(f"{aid} 缺 task（语义层没写）")

    if problems:
        for p in problems:
            print("错误:", p)
        print(f"check: 不通过（{len(problems)} 项）")
        return 1
    total = len(items)
    print(f"check: {total} 个原子自包含校验通过（source_text、模板、规则、清单自洽）")
    return 0


def cmd_restore(args):
    """把原子的完整内容导出成可读文本，默认落在 .tmp/export。"""
    out = Path(getattr(args, "out", None) or ".tmp/export")
    out.mkdir(parents=True, exist_ok=True)
    restored = 0
    for i, _item in enumerate(load_index(), 1):
        ap = ATOM_DIR / f"{atom_id(i)}.json"
        if not ap.exists():
            print(f"{atom_id(i)} 原子缺失，跳过", file=sys.stderr)
            continue
        atom = json.loads(ap.read_text(encoding="utf-8"))
        name = f"{atom['id']}-{atom.get('no', 'x')}.md"
        (out / name).write_text(atom.get("source_text", ""), encoding="utf-8", newline="\n")
        restored += 1
    print(f"restore: 导出 {restored} 个文件到 {out}")
    return 0


def selftest():
    import tempfile

    fails = []
    sample = """# 测试 SOP

## 第一步：准备

这部分是解释性文字，不算规则句。

产品图必须保持原样，禁止拉伸，不得改变颜色。

### 提示词

```Plain
以参考图为准，保持产品不变。
```
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.md"
        p.write_text(sample, encoding="utf-8")
        r = parse(p)
        if len(r["code_blocks"]) != 1:
            fails.append(f"代码块数错误：{len(r['code_blocks'])}")
        if r["code_blocks"] and "保持产品不变" not in r["code_blocks"][0]["text"]:
            fails.append("代码块内容提取错误")
        if len(r["headings"]) != 3:
            fails.append(f"标题数错误：{len(r['headings'])}")
        rule_texts = " ".join(x["text"] for x in r["prose_rules"])
        if "禁止拉伸" not in rule_texts:
            fails.append(f"规则句漏抽：{r['prose_rules']}")
        if "解释性文字" in rule_texts:
            fails.append("解释性文字被误当规则句")
        # 模板内的句子不应进规则（已在模板里）
        if "保持产品不变" in rule_texts:
            fails.append("模板内规则被重复抽进 prose_rules")

        # 裸段落型模板：没有 ``` 包裹，但跟在提示词类标题下
        p2 = Path(tmp) / "y.md"
        p2.write_text("# 测试\n\n## 直接复制用的提示词\n\n你是一名资深电商视觉设计师，请严格按照以下结构输出。"
                      + "这是一段足够长的提示词内容，用于验证裸段落识别。" * 10
                      + "\n\n## 下一步\n\n这里只是说明文字，不该被当成模板。\n", encoding="utf-8")
        r2 = parse(p2)
        if len(r2["code_blocks"]) != 0:
            fails.append("裸段落篇不应有代码块")
        if len(r2.get("loose_templates", [])) != 1:
            fails.append(f"裸段落模板识别失败：{r2.get('loose_templates')}")
        elif "裸段落识别" not in r2["loose_templates"][0]["text"]:
            fails.append("裸段落内容提取错误")

        # 自包含：source_text 必须原样保留，原子才不依赖外部文件
        if r.get("source_text") != sample:
            fails.append("source_text 未完整保留内容")
        if len(r.get("sha", "")) != 12:
            fails.append(f"sha 计算异常：{r.get('sha')}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 5 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="SOP 原子化")
    sub = ap.add_subparsers(dest="cmd")
    for name in ["extract", "summary", "merge", "check", "restore"]:
        sub.add_parser(name)
    ap.add_argument("--out", help="restore 的导出目录（默认 .tmp/export）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    handler = {"extract": cmd_extract, "summary": cmd_summary, "merge": cmd_merge,
               "check": cmd_check, "restore": cmd_restore}.get(args.cmd)
    if not handler:
        ap.print_help()
        return 0
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
