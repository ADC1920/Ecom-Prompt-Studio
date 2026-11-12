# -*- coding: utf-8 -*-
"""MCP server：把原子库与判据脚本暴露成四个可调用工具。

为什么需要它：不接 MCP 时，agent 要拿一条模板得走四步——读 SKILL.md、判工位、读
_atoms/aNN.json、从 templates 挑一个，全靠模型自觉，任何一步错就取错。这里把那四步
压成一次调用。

四个工具都是现有脚本与索引的薄包装，不引入新判据：
- query_atom      按品类/产物/动作定位原子（读 _index.json，不做语义猜测）
- get_template    取原子里的模板 + 该原子的规则与清单
- validate_prompt 跑 rules_engine 与 slop_check
- check_output    跑 check_image 做平台机检

用法（stdio，ZCode 通过 .mcp.json 拉起）：
  python tools/mcp_server.py

协议实现只用标准库：MCP 的 JSON-RPC 2.0 帧就是「一行一个 JSON」，不引第三方 SDK。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SOP_DIR = REPO_ROOT / "ecom-prompt-sop"
INDEX_JSON = SOP_DIR / "references" / "_atoms" / "index.json"
ATOM_DIR = SOP_DIR / "references" / "_atoms"

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ecom-prompt-studio", "version": "2.1.0"}


def _load_index():
    if not INDEX_JSON.exists():
        return []
    data = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
    return data.get("items") or []


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
    category = (args.get("category") or "").strip()
    output = (args.get("output") or "").strip()
    action = (args.get("action") or "").strip()
    text = (args.get("text") or "").strip()
    limit = int(args.get("limit") or 3)

    atoms = _load_index()
    if not atoms:
        return {"error": "原子索引缺失，先跑 python tools/atomize.py merge"}

    scored = []
    for a in atoms:
        s = _score(a, category, output, action, text)
        if s > 0:
            scored.append((s, a))
    scored.sort(key=lambda x: -x[0])

    if not scored:
        return {
            "hits": [],
            "note": "没有原子命中。检查品类是否在 34 篇覆盖范围内，或改用通用篇（a01/a02/a03）。",
        }

    hits = []
    for s, a in scored[:limit]:
        hits.append({
            "atom": a.get("id"),
            "title": a.get("title"),
            "stations": a.get("stations"),
            "outputs": a.get("outputs"),
            "task": a.get("task"),
            "score": s,
        })
    return {"hits": hits, "total_matched": len(scored)}


def get_template(args):
    atom_id = (args.get("atom") or "").strip()
    idx = args.get("index")
    if not atom_id:
        return {"error": "缺少 atom 参数，例如 a21"}

    path = ATOM_DIR / f"{atom_id}.json"
    if not path.exists():
        return {"error": f"原子不存在：{atom_id}"}

    atom = json.loads(path.read_text(encoding="utf-8"))
    templates = atom.get("templates") or []
    if idx is not None:
        try:
            i = int(idx)
        except (TypeError, ValueError):
            return {"error": f"index 必须是整数，收到 {idx!r}"}
        if i < 0 or i >= len(templates):
            return {"error": f"index 越界：{i}，该原子有 {len(templates)} 个模板"}
        picked = [templates[i]]
    else:
        picked = templates

    return {
        "atom": atom_id,
        "title": atom.get("title"),
        "stations": atom.get("stations"),
        "template_count": len(templates),
        "templates": picked,
        "rules": atom.get("rules") or [],
        "checklists": atom.get("checklists") or [],
        "placeholders": atom.get("placeholders") or [],
    }


def _run_script(script, argv, timeout=60):
    import subprocess
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
    prompt = args.get("prompt") or ""
    if not prompt.strip():
        return {"error": "缺少 prompt 参数"}

    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(prompt)
        tmp = f.name

    try:
        out = {"slop": _run_script("slop_check.py", [tmp, "--json"])}
        platform = args.get("platform")
        scenario = args.get("scenario")
        category = args.get("category")
        if platform:
            slots = args.get("slots")
            if slots:
                import tempfile as tf
                with tf.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as sf:
                    json.dump(slots, sf, ensure_ascii=False)
                    slot_path = sf.name
                argv = ["--check", slot_path, "--platform", platform]
                if scenario:
                    argv += ["--scenario", scenario]
                if category:
                    argv += ["--category", category]
                out["rules"] = _run_script("rules_engine.py", argv)
                Path(slot_path).unlink(missing_ok=True)
            else:
                out["rules"] = {"skipped": "未提供 slots，跳过规则引擎（它校验的是槽位而非自由文本）"}
        else:
            out["rules"] = {"skipped": "未提供 platform，跳过规则引擎"}
        return out
    finally:
        Path(tmp).unlink(missing_ok=True)


def check_output(args):
    image = args.get("image") or ""
    platform = args.get("platform") or ""
    if not image:
        return {"error": "缺少 image 参数（图片路径）"}
    if not platform:
        return {"error": "缺少 platform 参数（如 amazon / taobao / tmall）"}
    if not Path(image).exists():
        return {"error": f"图片不存在：{image}"}

    argv = [image, "--platform", platform, "--json"]
    if args.get("strict"):
        argv.append("--strict")
    return _run_script("check_image.py", argv, timeout=120)


TOOLS = [
    {
        "name": "query_atom",
        "description": "按品类、产物、动作定位 SOP 原子，返回命中的原子编号与依据。用于替代人工判工位。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "品类，如 百货杯壶、美妆日化、服饰"},
                "output": {"type": "string", "description": "产物，如 主图、详情页、SKU图、模特图、视频"},
                "action": {"type": "string", "description": "动作，如 生成、反推、翻新、批量、翻译"},
                "text": {"type": "string", "description": "用户原话，用于关键词兜底打分"},
                "limit": {"type": "integer", "description": "最多返回几条，默认 3"},
            },
        },
    },
    {
        "name": "get_template",
        "description": "取指定原子的提示词模板，连同该原子的规则、验收清单与占位符一起返回。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "atom": {"type": "string", "description": "原子编号，如 a21"},
                "index": {"type": "integer", "description": "可选，只取第几个模板（从 0 开始）"},
            },
            "required": ["atom"],
        },
    },
    {
        "name": "validate_prompt",
        "description": "校验提示词：反 AI 感与合规用语（slop_check），可选按平台/场景/品类跑规则引擎。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "待校验的提示词全文"},
                "platform": {"type": "string", "description": "可选，平台 id，如 amazon"},
                "scenario": {"type": "string", "description": "可选，场景，如 首图"},
                "category": {"type": "string", "description": "可选，品类"},
                "slots": {"type": "object", "description": "可选，五槽位结构化对象；提供后才跑规则引擎"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "check_output",
        "description": "出图后平台机检：白底纯度、主体占比、比例、分辨率、文件大小、透明通道、图内文字。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "图片路径"},
                "platform": {"type": "string", "description": "平台 id，如 amazon、taobao、tmall"},
                "strict": {"type": "boolean", "description": "严格模式：警告也算失败"},
            },
            "required": ["image", "platform"],
        },
    },
]

HANDLERS = {
    "query_atom": query_atom,
    "get_template": get_template,
    "validate_prompt": validate_prompt,
    "check_output": check_output,
}


def respond(msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    msg_id = req.get("id")

    if method == "initialize":
        return respond(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "notifications/initialized":
        return
    if method == "tools/list":
        return respond(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        handler = HANDLERS.get(name)
        if not handler:
            return respond(msg_id, error={"code": -32601, "message": f"未知工具：{name}"})
        try:
            payload = handler(params.get("arguments") or {})
            return respond(msg_id, {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "isError": bool(payload.get("error")),
            })
        except Exception as e:
            return respond(msg_id, error={"code": -32603, "message": f"{type(e).__name__}: {e}"})
    if method in ("ping",):
        return respond(msg_id, {})
    if msg_id is not None:
        respond(msg_id, error={"code": -32601, "message": f"未实现方法：{method}"})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except json.JSONDecodeError:
            respond(None, error={"code": -32700, "message": "无法解析的 JSON"})
    return 0


def selftest():
    """离线自检：不打网络、不碰真实密钥，只验索引与原子可读。"""
    fails = []
    atoms = _load_index()
    if len(atoms) != 34:
        fails.append(f"原子索引应为 34 条，实际 {len(atoms)}")

    got = query_atom({"category": "杯壶", "output": "主图"})
    hits = got.get("hits") or []
    if not hits:
        fails.append("query_atom 对「杯壶+主图」无命中")
    elif hits[0]["atom"] != "a21":
        fails.append(f"杯壶主图应首选 a21，实际 {hits[0]['atom']}")

    tpl = get_template({"atom": "a21", "index": 0})
    if not tpl.get("templates"):
        fails.append("get_template 取 a21 模板失败")
    if tpl.get("error"):
        fails.append(f"get_template 报错：{tpl['error']}")

    miss = get_template({"atom": "a99"})
    if not miss.get("error"):
        fails.append("不存在的原子应返回 error")

    # slop_check 默认把堆词记为 warn 且退出 0，只有 --strict 才判失败
    v = validate_prompt({"prompt": "8k masterpiece 极致完美的保温杯主图"})
    if "\"warn\": 4" not in (v["slop"].get("stdout") or "").replace(",", "").replace(" ", ""):
        if "空洞堆词" not in (v["slop"].get("stdout") or ""):
            fails.append("堆词提示词应被 slop_check 报出空洞堆词")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 索引、定位、取模板、堆词拦截 全部通过")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
