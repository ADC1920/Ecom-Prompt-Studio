# -*- coding: utf-8 -*-
"""五槽位提示词组装器：把结构化槽位编译成可直接投喂的提示词。

槽位规范见 ecom-prompt-sop/references/prompt-slots.md。
本脚本只负责顺序、完整度校验与平台约束补充，内容仍由 SOP 原文与用户产品信息决定。

用法：
  python tools/compose_prompt.py --template > slots.json
  python tools/compose_prompt.py slots.json
  python tools/compose_prompt.py slots.json --platform amazon --check
  python tools/compose_prompt.py slots.json --json
  python tools/compose_prompt.py --selftest

退出码：0 正常；1 缺必填项或自查出现 error。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from check_image import ALIASES, PLATFORMS
except ImportError:  # 平台补充是增强项，缺了不影响组装
    ALIASES, PLATFORMS = {}, {}

try:
    from slop_check import check as slop_check
except ImportError:
    slop_check = None

try:
    from rules_engine import load_rules, validate as rules_validate
except ImportError:
    rules_validate = None

REQUIRED = ["subject", "constraints"]
OPTIONAL = ["scene", "details", "usecase"]
SEGMENT_LABEL = {
    "scene": "场景",
    "subject": "主体",
    "details": "细节",
    "usecase": "用途",
    "constraints": "约束",
}
TEMPLATE = {
    "lock": "以全部参考图为准，参考图之间不一致时以最清晰角度为准。保留清单：产品品类、轮廓、比例、颜色、材质、包装、Logo、标签与可见细节不变。",
    "style_lock": "色板 / 光影 / 背景系统 / 镜头 / 构图 / 文字层级 / 材质处理 / 道具白名单 / 品牌调性 十项写全后整段复用。",
    "platform": "generic",
    "scene": "背景材质、空间关系、景深、道具白名单、整体氛围。",
    "subject": "产品品类、轮廓比例、颜色材质、包装与标签、朝向与画面占位。",
    "details": "卖点、可见文字、标签内容、材质特写、结构件、必要限定语；每条都要能追溯到图片可见或用户提供。",
    "usecase": "目标平台、页面位置、比例、受众、商用场景。",
    "constraints": [
        "保留产品形状、比例、颜色、logo 位置与材质",
        "不要出现文字、水印、多余手指、重复产品或无关道具",
    ],
}


def as_text(value):
    """槽位允许写字符串或字符串数组，统一成一句。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value if str(v).strip()]
        return "；".join(items)
    return str(value).strip()


def platform_clause(name):
    """把机检基线翻译成一句平台约束，补在用途段末尾。"""
    key = ALIASES.get(name, name)
    spec = PLATFORMS.get(key)
    if not spec:
        return ""
    parts = []
    if spec.get("ratio"):
        parts.append(f"画面比例 {spec['ratio'][0]}:{spec['ratio'][1]}")
    if spec.get("white_bg"):
        parts.append("背景纯白 RGB(255,255,255)，产品占画面约 85%，四周留白收紧")
    if not spec.get("text_allowed"):
        parts.append("首图不得出现文字、水印、边框与促销角标")
    return "；".join(parts) + "。" if parts else ""


def compose(slots, platform=None):
    """按固定顺序组装，返回 (提示词, 警告列表)。缺必填项抛 ValueError。"""
    missing = [k for k in REQUIRED if not as_text(slots.get(k))]
    if missing:
        raise ValueError(f"缺少必填槽位：{', '.join(missing)}（subject 与 constraints 必须有）")

    blocks = []
    lock = as_text(slots.get("lock"))
    style = as_text(slots.get("style_lock"))
    head = []
    if lock:
        head.append(lock if lock.startswith("以全部参考图为准") else f"以全部参考图为准，参考图之间不一致时以最清晰角度为准。{lock}")
    if style:
        head.append(f"风格锁：{style}" if not style.startswith("风格锁") else style)
    if head:
        blocks.append("".join(head))

    warnings = []
    for key in ["scene", "subject", "details", "usecase"]:
        text = as_text(slots.get(key))
        if text:
            blocks.append(f"{SEGMENT_LABEL[key]}：{text}")
        elif key in OPTIONAL:
            warnings.append(f"槽位 {key} 为空，成品会缺少{SEGMENT_LABEL[key]}层")

    usecase = as_text(slots.get("usecase"))
    pf = platform or slots.get("platform") or "generic"
    clause = platform_clause(pf)
    if clause:
        if usecase:
            blocks[-1] = f"{SEGMENT_LABEL['usecase']}：{usecase}。{clause}"
        else:
            blocks.append(f"{SEGMENT_LABEL['usecase']}：{clause}")

    # 交叉校验：平台要纯白，场景却写了非白材质，多半是把辅图当首图了
    spec = PLATFORMS.get(ALIASES.get(pf, pf)) or {}
    scene_text = as_text(slots.get("scene"))
    if spec.get("white_bg") and scene_text and "白" not in scene_text:
        warnings.append("该平台要求纯白背景，场景槽位未提白色；若这张是首图请改白底，辅图不受此限")

    blocks.append(f"约束：{as_text(slots.get('constraints'))}")
    return "\n\n".join(blocks), warnings


def selftest():
    fails = []
    good = dict(TEMPLATE)
    text, warns = compose(good, "amazon")
    order = ["以全部参考图为准", "风格锁", "场景：", "主体：", "细节：", "用途：", "约束："]
    pos = [text.find(m) for m in order]
    if any(p < 0 for p in pos):
        fails.append(f"组装段落缺失：{list(zip(order, pos))}")
    elif pos != sorted(pos):
        fails.append(f"段落顺序错误：{list(zip(order, pos))}")
    if "1:1" not in text or "纯白" not in text:
        fails.append("平台约束未补入（amazon 应有 1:1 与纯白）")

    # 必填拦截
    try:
        compose({"scene": "只有场景"})
        fails.append("缺 subject/constraints 时未拦截")
    except ValueError:
        pass

    # 可选缺失只警告
    _, w = compose({"subject": "杯子", "constraints": "无文字"})
    if len(w) < 3:
        fails.append(f"可选槽位缺失应给警告，实际 {w}")

    # 数组形式的约束
    t2, _ = compose({"subject": "杯子", "constraints": ["无文字", "无水印"]})
    if "无文字；无水印" not in t2:
        fails.append("数组形式 constraints 未拼接")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 4 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="五槽位提示词组装器")
    ap.add_argument("slots", nargs="?", help="槽位 JSON 文件；不传读 stdin")
    ap.add_argument("--template", action="store_true", help="输出空白模板 JSON")
    ap.add_argument("--platform", help="平台名，自动补比例与白底约束")
    ap.add_argument("--scenario", help="场景名（首图/辅图/详情页单屏等），配 --rules 用来校验必填槽位")
    ap.add_argument("--category", help="品类名，配 --rules 用来校验禁用宣称")
    ap.add_argument("--rules", action="store_true", help="组装后跑判据规则校验（_rules/ 下的三个规则文件）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（含提示词、警告、自查结果）")
    ap.add_argument("--check", action="store_true", help="组装后跑反 AI 感自查，error 即失败")
    ap.add_argument("--selftest", action="store_true", help="离线自检")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    try:
        raw = Path(args.slots).read_text(encoding="utf-8-sig") if args.slots else sys.stdin.read()
        slots = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"槽位 JSON 读取失败：{e}", file=sys.stderr)
        return 1

    try:
        text, warnings = compose(slots, args.platform)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    issues = []
    if args.check and slop_check:
        issues = slop_check(text)
        if any(i["level"] == "error" for i in issues):
            warnings.append("自查命中 error 级问题，必须先改完再交付")

    rule_issues = []
    if args.rules:
        if not rules_validate:
            warnings.append("rules_engine 不可用，跳过判据校验")
        else:
            try:
                rule_issues = rules_validate(
                    slots,
                    load_rules(),
                    args.platform or slots.get("platform") or "generic",
                    args.scenario,
                    args.category,
                )
                for i in rule_issues:
                    warnings.append(f"[{i['level']}] {i['detail']}" + (f" → {i['hint']}" if i.get("hint") else ""))
            except (FileNotFoundError, json.JSONDecodeError) as e:
                warnings.append(f"规则文件读取失败，跳过判据校验：{e}")

    if args.json:
        print(json.dumps({"prompt": text, "warnings": warnings, "issues": issues, "rules": rule_issues}, ensure_ascii=False, indent=2))
    else:
        print(text)
        for w in warnings:
            print(f"[警告] {w}", file=sys.stderr)
        for i in issues:
            if i["level"] == "error":
                print(f"[ERROR] {i['category']}：{i['match']} → {i['hint']}", file=sys.stderr)

    has_error = any(i["level"] == "error" for i in issues) or any(i["level"] == "error" for i in rule_issues)
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
