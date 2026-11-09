# -*- coding: utf-8 -*-
"""提示词产出检查：反 AI 感与合规风险。

管两件事：
1. 合规：绝对化用语、虚假促销、医疗功效宣称——写进提示词就等于写进图，风险随图走。
2. 观感：SD 时代的堆词（8k / masterpiece / hyperrealistic）和 AI-tell 特征词，会把图推向塑料感。

只检查**产出的提示词或在图文案**，不检查 SOP 内容（其中的示例值是给模型看的示例，不是成品文案）。

用法：
  python tools/slop_check.py prompt.txt
  python tools/slop_check.py prompt.txt --json --strict
  python tools/slop_check.py --text "8k, masterpiece, 全网最低价"

退出码：0 无问题；1 有 error（--strict 时 warn 也算）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# (级别, 类别, 模式, 说明)
# 级别：error=广告法或平台高风险；warn=需证据或明显拉低成片质量；info=提示性
RULES = [
    # 绝对化用语：《广告法》第九条明确禁止
    ("error", "绝对化用语", r"最(好|佳|优|强|先进|低价|便宜|实惠|新|流行|火爆)", "改用可核验的具体参数，如「续航 12 小时」"),
    ("error", "绝对化用语", r"(?<!第)第一(?!步|时间|视角|张|屏|层|条|章|天|眼|阶段|行|列|部分|次|轮|节|段|项|位|批|版本|代)", "「第一」属绝对化用语，先删或改成具体排序依据"),
    ("error", "绝对化用语", r"唯一|独家|首创|首个|首家|绝无仅有|史无前例|万能|包治", "需权威证明才可主张，默认删"),
    ("error", "绝对化用语", r"国家级|世界级|顶级|顶尖|天花板|王者", "等级用语无依据即违规"),
    ("error", "绝对化用语", r"100\s*%|百分百|百分之百", "涉功效或效果时禁用；确为事实需标注条件与依据"),
    # 虚假促销
    ("warn", "促销表述", r"限时秒杀|全网最低|最低价|史上最低|亏本|赔本|清仓|最后一天|仅此一天|错过不再", "促销口径必须与后台活动一致，且需可核验依据"),
    ("warn", "促销表述", r"原价\s*[\d¥￥]|划线价|劲爆价|疯抢", "价格类信息以店铺后台为准，AI 生成图不放价格除非你已确认"),
    # 医疗与功效
    ("error", "功效宣称", r"治疗|根治|治愈|消炎|抗癌|降血压|降血糖|减肥|排毒|无副作用|祛斑|生发", "功效宣称需资质与检测报告，AI 出图不得主张"),
    ("warn", "功效宣称", r"纯天然|零添加|无添加|医用级|食品级|药妆", "需检测报告或备案，否则改为中性描述"),
    # 认证与背书
    ("error", "认证背书", r"(?i)(FDA|CE|CCC|SGS|ISO)\s*(认证|approved|certified)", "认证标识必须用真实证书，AI 不得绘制或声称"),
    ("warn", "认证背书", r"(?i)畅销|爆款|销量第一|百万好评|明星同款", "销量与背书需真实数据，且平台多禁止主图出现"),
    # 堆词与 AI 感（SD 时代遗产，现代模型不需要，写了反而塑料）
    ("warn", "空洞堆词", r"(?i)\b(8k|4k|16k|uhd|masterpiece|best quality|highly detailed|ultra[- ]?detailed|hyper[- ]?detailed|hyper[- ]?realistic|insane detail|award[- ]?winning)\b", "删掉这些堆词；用材质、光位、镜头参数替代"),
    ("warn", "空洞堆词", r"(?i)\b(stunning|breathtaking|gorgeous|perfect|flawless|epic|amazing|beautiful)\b", "形容词换成可执行描述：谁、在哪、什么光、什么镜头"),
    ("warn", "空洞堆词", r"极致|完美|震撼|绝美|超高级|炸裂|逆天|神级|史诗级|顶级质感", "中文同类堆词，改成具体视觉特征"),
    ("warn", "空洞堆词", r"(?i)\b(cinematic lighting|studio lighting|soft lighting)\b", "单独写灯法没用；写清主光方向、色温、柔硬、补光与投影"),
    # AI-tell 视觉特征
    ("info", "AI 痕迹", r"(?i)(perfectly symmetr|over[- ]?smooth|plastic (sheen|skin)|airbrushed|impossibly (clean|perfect)|floating (product|object)|no shadow)", "这些特征会暴露 AI 感，改写成真实材质与物理关系"),
    ("info", "AI 痕迹", r"(?i)(halo|glow) around", "主体边缘光晕是典型 AI 痕迹，删掉或改成真实轮廓光描述"),
    # 负面堆砌
    ("warn", "负面堆砌", r"(?i)\bno\s+\w+[,，]\s*no\s+\w+[,，]\s*no\s+\w+[,，]\s*no\s+\w+", "负词超过 3 条效果递减；改用一句输出边界句"),
]

COMPILED = [(lvl, cat, re.compile(pat), hint) for lvl, cat, pat, hint in RULES]
LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}


def check(text):
    """返回问题列表；同一条规则同位置只报一次。"""
    found = []
    lines = text.splitlines() or [text]
    for idx, line in enumerate(lines, 1):
        for lvl, cat, rx, hint in COMPILED:
            for m in rx.finditer(line):
                hit = m.group(0)
                # 中文绝对化里「最好」常作为口语（做好最好），仍按风险保留，交由人判断
                found.append({
                    "level": lvl,
                    "category": cat,
                    "match": hit,
                    "line": idx,
                    "context": line.strip()[:80],
                    "hint": hint,
                })
    # 去重：同级别+同类别+同命中+同行只留一条
    seen, out = set(), []
    for f in found:
        key = (f["level"], f["category"], f["match"], f["line"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    out.sort(key=lambda f: (LEVEL_ORDER[f["level"]], f["line"]))
    return out


def selftest():
    fails = []

    # 正例：干净的提示词不应报错
    clean = "白底主图，产品正面居中，柔和顶光，接触阴影落在产品底部。保留原有 logo 与标签文字。"
    issues = check(clean)
    if issues:
        fails.append(f"干净提示词被误报: {issues}")

    # 负例：绝对化用语必须命中 error
    issues = check("最好的保温杯，全网最低价，限时秒杀")
    if not any(i["level"] == "error" and "绝对化" in i["category"] for i in issues):
        fails.append("绝对化用语未命中")
    if not any(i["category"] == "促销表述" for i in issues):
        fails.append("促销表述未命中")

    # 免误报：「第一步」「第一时间」不应命中绝对化
    issues = check("第一步先锁产品，第一时间检查阴影")
    if any(i["level"] == "error" for i in issues):
        fails.append(f"「第一步/第一时间」被误判为绝对化: {issues}")

    # 堆词必须命中 warn
    issues = check("8k masterpiece hyperrealistic, ultra-detailed product shot")
    if not any(i["category"] == "空洞堆词" for i in issues):
        fails.append("英文堆词未命中")

    # 医疗功效必须命中 error
    issues = check("这款面膜可以根治痘痘")
    if not any(i["category"] == "功效宣称" and i["level"] == "error" for i in issues):
        fails.append("功效宣称未命中")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 5 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="提示词产出检查：反 AI 感与合规风险")
    ap.add_argument("files", nargs="*", help="待检文本文件，可多个")
    ap.add_argument("--text", help="直接检查一段文本")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--strict", action="store_true", help="warn 也算失败（CI 用）")
    ap.add_argument("--selftest", action="store_true", help="离线自检")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    targets = []
    if args.text:
        targets.append(("<text>", args.text))
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f"文件不存在：{f}", file=sys.stderr)
            return 1
        targets.append((str(p), p.read_text(encoding="utf-8", errors="replace")))

    if not targets:
        ap.print_help()
        return 0

    results, bad = [], False
    for name, text in targets:
        issues = check(text)
        counts = {"error": 0, "warn": 0, "info": 0}
        for i in issues:
            counts[i["level"]] += 1
        if counts["error"] or (args.strict and counts["warn"]):
            bad = True
        results.append({"file": name, "counts": counts, "issues": issues})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        label = {"error": "ERROR", "warn": "WARN ", "info": "INFO "}
        for r in results:
            c = r["counts"]
            print(f"\n{r['file']}  ·  {c['error']} error / {c['warn']} warn / {c['info']} info")
            for i in r["issues"]:
                print(f"  {label[i['level']]}  [{i['category']}] {i['match']}  (第 {i['line']} 行)")
                print(f"        {i['context']}")
                print(f"        → {i['hint']}")
            if not r["issues"]:
                print("  未发现问题")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
