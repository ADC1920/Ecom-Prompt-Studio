# -*- coding: utf-8 -*-
"""判据规则引擎：用可校验的规则代替「读原文记规则」。

三个规则文件在 ecom-prompt-sop/references/_rules/：
- platform.json  平台阈值、文字与模特政策、AI 标注义务、文案禁项
- category.json  品类禁用宣称、需要证据的说法、出图要点
- scenario.json  场景必填槽位、画面禁项、详情页信息块下限

用法：
  python tools/rules_engine.py --list platform
  python tools/rules_engine.py --check slots.json --platform amazon --scenario 首图 --category 美妆日化
  python tools/rules_engine.py --inject slots.json --platform amazon --scenario 首图
  python tools/rules_engine.py --selftest

退出码：0 无 error；1 有问题；2 输入错误。
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES_DIR = HERE.parent / "ecom-prompt-sop" / "references" / "_rules"

# 文案类关键词：平台禁文字时，槽位里出现这些词说明准备在画面里写字
TEXT_HINTS = ["主标题", "副标题", "卖点文字", "图内文字", "文案", "促销语", "角标文字", "价格", "折扣"]
# 白底平台的场景描述里，出现这些材质说明背景不是白的
NONWHITE_HINTS = ["亚麻", "木", "石", "水泥", "墙", "布", "绒", "皮", "砖", "草", "沙滩", "天空", "街", "室内", "咖啡"]
EVIDENCE_PLACEHOLDER = ["待补充", "待确认", "待核对", "以实物为准", "占位"]
# 否定表述：「不出现水印」「禁止水印」是正确写法，不能算违规
NEGATIONS = ["不", "禁", "无", "避免", "勿", "别", "除"]


def _clause_at(text, idx):
    """取词所在分句（按中文与英文标点切）。否定判断看整句，而不是固定字符窗口。"""
    seps = "，。；;,:\n"
    starts = [text.rfind(c, 0, idx) for c in seps]
    start = max(starts) + 1 if max(starts) >= 0 else 0
    ends = [text.find(c, idx) for c in seps]
    end = min([e for e in ends if e >= 0], default=len(text))
    return text[start:end]


def occurs_positively(text, word):
    """词出现且所在分句没有否定词才算命中。

    例：「不出现文字、水印、边框」整句是否定，三个词都不算命中；
        「产品带边框，不要文字」第一句是肯定，边框算命中。
    """
    start = 0
    while True:
        idx = text.find(word, start)
        if idx < 0:
            return False
        clause = _clause_at(text, idx)
        if not any(n in clause for n in NEGATIONS):
            return True
        start = idx + len(word)


def load_rules(dirpath=None):
    base = Path(dirpath) if dirpath else RULES_DIR
    rules = {}
    for name in ["platform", "category", "scenario"]:
        p = base / f"{name}.json"
        if not p.exists():
            raise FileNotFoundError(f"规则文件缺失：{p}")
        rules[name] = json.loads(p.read_text(encoding="utf-8"))
    return rules


def all_text(slots):
    parts = []
    for k in ["lock", "style_lock", "scene", "subject", "details", "usecase", "constraints"]:
        v = slots.get(k)
        if isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))
    return "\n".join(parts)


def guess_category(text, rules):
    """按触发词猜品类，命中最多者胜；拿不准返回 None。"""
    best, best_hits = None, 0
    for name, spec in rules["category"]["categories"].items():
        hits = sum(1 for t in spec.get("triggers", []) if t in text)
        if hits > best_hits:
            best, best_hits = name, hits
    return best if best_hits else None


def validate(slots, rules, platform="generic", scenario=None, category=None):
    """返回问题列表。level=error 会阻止交付，warn 需人工判断。"""
    issues = []

    def add(level, cid, detail, hint=""):
        issues.append({"level": level, "id": cid, "detail": detail, "hint": hint})

    pf = rules["platform"]["platforms"].get(platform)
    if not pf:
        add("error", "platform", f"未知平台 {platform}", "用 --list platform 查看可用值")

    text = all_text(slots)
    scene = str(slots.get("scene") or "")
    detail = str(slots.get("details") or "")

    # 场景必填槽位
    if scenario:
        sc = rules["scenario"]["scenarios"].get(scenario)
        if not sc:
            add("error", "scenario", f"未知场景 {scenario}", "用 --list scenario 查看可用值")
        else:
            for slot in sc.get("slot_required", []):
                if not str(slots.get(slot) or "").strip():
                    add("error", "slot", f"场景「{scenario}」要求槽位 {slot}，当前为空", "补上该槽位或用 --inject 看去哪补")
            for word in sc.get("forbid", []):
                if occurs_positively(text, word):
                    add("warn", "scene-forbid", f"场景「{scenario}」禁止「{word}」，但槽位里出现了", "确认是否真的需要；首图类禁项通常不能保留")
            if sc.get("text_allowed") is False:
                for hint in TEXT_HINTS:
                    if occurs_positively(detail + str(slots.get("usecase") or ""), hint):
                        add("warn", "text", f"场景「{scenario}」不允许图内文字，槽位里出现「{hint}」", "文字挪到辅图或详情页")
                        break
            if sc.get("min_info_blocks") and len([1 for k in ("details", "usecase") if str(slots.get(k) or "").strip()]) < 2:
                add("warn", "density", f"场景「{scenario}」要求至少 {sc['min_info_blocks']} 个信息层级，details 与 usecase 至少都要写", "补信息模块或改场景")

    # 平台白底 vs 场景描述
    if pf and pf.get("white_bg") and scene:
        if "白" not in scene and any(w in scene for w in NONWHITE_HINTS):
            add("warn", "bg-conflict", f"{pf['label']} 要求纯白背景，但场景写了非白材质", "首图请改白底；这是辅图则忽略本条")

    # 平台禁文字 vs 细节里带文案
    if pf and not pf.get("text_allowed") and detail:
        for hint in TEXT_HINTS:
            if occurs_positively(detail, hint):
                add("warn", "platform-text", f"{pf['label']} 首图不允许文字，细节里出现「{hint}」", "改到辅图，或确认这是辅图任务")
                break

    # 品类禁用宣称
    if category:
        cat = rules["category"]["categories"].get(category)
        if not cat:
            add("error", "category", f"未知品类 {category}", "用 --list category 查看可用值")
        else:
            for claim in cat.get("claims_forbidden", []):
                base = claim.split("（")[0]
                if base and occurs_positively(text, base):
                    add("error", "claim", f"品类「{category}」禁用宣称「{base}」出现在槽位里", "无资质不得主张；删掉或换成可核验的具体参数")
            for need in cat.get("needs_evidence", []):
                if need in text and not any(ph in text for ph in EVIDENCE_PLACEHOLDER):
                    add("warn", "evidence", f"提到「{need}」但没有占位或证据标注", "改成「待补充" + need + "」或提供真实数据")

    # 兜底：空白整体
    if not str(slots.get("subject") or "").strip():
        add("error", "subject", "subject 槽位为空", "画面必须有产品主体")

    return issues


def inject(slots, rules, platform="generic", scenario=None):
    """按规则补默认约束，返回新 slots 与补充说明。"""
    out = dict(slots)
    notes = []
    pf = rules["platform"]["platforms"].get(platform) or {}
    sc = (rules["scenario"]["scenarios"].get(scenario) or {}) if scenario else {}

    cons = out.get("constraints")
    cons_list = list(cons) if isinstance(cons, (list, tuple)) else ([cons] if cons else [])

    if pf.get("white_bg"):
        add = f"背景纯白 RGB(255,255,255)，产品占画面约 {int(pf.get('occupancy_min', 0.85) * 100)}%，四周留白收紧"
        if not any("纯白" in str(c) for c in cons_list):
            cons_list.append(add)
            notes.append("补平台白底与占比约束")
    if pf and not pf.get("text_allowed"):
        if not any("文字" in str(c) for c in cons_list):
            cons_list.append("首图不出现文字、水印、边框与促销角标")
            notes.append("补平台禁文字约束")
    for word in sc.get("forbid", []):
        if not any(word in str(c) for c in cons_list):
            cons_list.append(f"不出现{word}")
            notes.append(f"补场景禁项：{word}")

    if cons_list:
        out["constraints"] = cons_list
    if pf.get("ai_label") and not any("标注" in str(c) for c in cons_list):
        notes.append(f"标注义务：{pf['ai_label']}")
    return out, notes


def selftest():
    fails = []
    rules = load_rules()

    # 1) 合规白底首图
    ok = {"subject": "哑光不锈钢保温杯", "scene": "纯白无缝背景", "usecase": "Amazon 首图", "constraints": ["不出现文字"]}
    if validate(ok, rules, "amazon", "首图"):
        fails.append(f"合规槽位被误报：{validate(ok, rules, 'amazon', '首图')}")

    # 2) 白底平台 + 非白场景 → warn
    i2 = validate({"subject": "杯子", "scene": "亚麻台面与木质背景", "constraints": ["不出现文字"]}, rules, "amazon", "辅图")
    if not any(x["id"] == "bg-conflict" for x in i2):
        fails.append(f"白底冲突未命中：{i2}")

    # 3) 品类禁用宣称 → error
    i3 = validate({"subject": "面霜", "details": "可以根治痘痘", "constraints": ["不出现文字"]}, rules, "taobao", None, "美妆日化")
    if not any(x["level"] == "error" and x["id"] == "claim" for x in i3):
        fails.append(f"禁用宣称未命中：{i3}")

    # 4) 场景必填缺失 → error
    i4 = validate({"subject": "杯子"}, rules, "amazon", "详情页单屏")
    if not any(x["id"] == "slot" for x in i4):
        fails.append(f"必填槽位缺失未命中：{i4}")

    # 5) 注入：白底平台自动补约束
    out, notes = inject({"subject": "杯子", "constraints": []}, rules, "amazon", "首图")
    cons = " ".join(out["constraints"])
    if "纯白" not in cons or "文字" not in cons:
        fails.append(f"注入未补平台约束：{out['constraints']}")

    # 6) 品类自动识别
    if guess_category("这个保温杯做主图", rules) != "百货杯壶":
        fails.append("品类自动识别失败")

    # 7) 否定表述不误报：constraints 写「不出现文字、水印、边框」是对的，不能判违规
    i7 = validate({"subject": "杯子", "scene": "纯白背景", "constraints": ["不出现文字、水印、边框"]}, rules, "amazon", "首图")
    if any(x["id"] == "scene-forbid" for x in i7):
        fails.append(f"否定表述被误判为违规：{i7}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 7 组用例全部通过")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="判据规则引擎")
    ap.add_argument("--check", metavar="SLOTS_JSON", help="校验槽位文件")
    ap.add_argument("--inject", metavar="SLOTS_JSON", help="按规则补约束并输出槽位")
    ap.add_argument("--platform", default="generic")
    ap.add_argument("--scenario")
    ap.add_argument("--category")
    ap.add_argument("--list", choices=["platform", "category", "scenario"], help="列出可用值")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    try:
        rules = load_rules()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"规则加载失败：{e}", file=sys.stderr)
        return 2

    if args.list:
        key = {"platform": "platforms", "category": "categories", "scenario": "scenarios"}[args.list]
        for name, spec in sorted(rules[args.list][key].items()):
            label = spec.get("label") or ""
            print(f"{name:14} {label}")
        return 0

    target = args.check or args.inject
    if not target:
        ap.print_help()
        return 0

    try:
        slots = json.loads(Path(target).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"槽位读取失败：{e}", file=sys.stderr)
        return 2

    if args.inject:
        out, notes = inject(slots, rules, args.platform, args.scenario)
        if args.json:
            print(json.dumps({"slots": out, "notes": notes}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            for n in notes:
                print(f"[注入] {n}", file=sys.stderr)
        return 0

    issues = validate(slots, rules, args.platform, args.scenario, args.category)
    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        if not issues:
            print("未发现问题")
        for i in issues:
            print(f"  {i['level'].upper():5} [{i['id']}] {i['detail']}")
            if i.get("hint"):
                print(f"        → {i['hint']}")
    return 1 if any(i["level"] == "error" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
