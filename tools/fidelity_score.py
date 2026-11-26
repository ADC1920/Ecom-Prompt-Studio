# -*- coding: utf-8 -*-
"""出图保真评分：agent 答固定的九问，脚本算分与否决。

为什么要有它：现有的两层之间是空的。
- visual_audit.py 给感知哈希与色彩统计的启发式分，自己就声明「只用于提示复核，不作依据」。
- vlm_review.py 生成空表等人填，结论全凭人写。
中间缺一层：问题固定、算分由代码做、有硬否决项——这样同一组回答永远得到同一张评分卡，
换个人或换个模型复评也不会漂。

设计取舍（照 molly554/onmodel 的九问量表改造，不是照抄）：
- 九问横跨保真/姿态/身份/瑕疵/比例五维，每问只能答五选一。
- `cannot_tell` 计 1 分而不是 2，且在保真项上直接阻断通过——看不清就不能算过。
- 八个否决码，命中任一即不通过，与分数无关。
- rubric_version 随每条记录落盘，阈值改了版本号必须跟着改，否则历史不可比。

agent 只填 answers，不填分数、不下结论。分数与结论由本脚本算。

用法：
  python tools/fidelity_score.py --template > card.json      # 出空白评分卡
  python tools/fidelity_score.py card.json                   # 算分并输出评分卡
  python tools/fidelity_score.py card.json --json
  python tools/fidelity_score.py --selftest

退出码：0 通过（Verified）；1 不通过；2 输入错误。
"""
import argparse
import json
import sys
from pathlib import Path

RUBRIC_VERSION = "1.0-draft"
# 阈值是起始值，尚未用人标注校准。改动必须同时升 RUBRIC_VERSION，否则历史评分不可比。
PASS_TOTAL = 8
PASS_FIDELITY = 2

# 九问：id →（维度，问题）。问题文本固定，不给 agent 改写的余地。
QUESTIONS = {
    "shape": ("保真", "产品的轮廓、比例与结构细节是否与实物图一致？"),
    "color": ("保真", "色相、饱和度、明度是否一致（含黑色是否仍够黑）？"),
    "material": ("保真", "表面质感与材质是否一致（玻璃透光、金属反光、织物纹理、印花）？"),
    "text": ("保真", "产品上的每个印字、字母、数字与 Logo 是否逐字一致？（无字则选相同）"),
    "parts": ("保真", "部件是否与实物一致：不缺、不多、不粘连？"),
    "pose": ("姿态", "是否遵循参考姿态的姿势、取景与机位？"),
    "identity": ("身份", "人物是否与参考模特一致，且没有把产品图里的手、模特假人或他人带进来？"),
    "artifacts": ("瑕疵", "有无解剖错误（每手五指）、形变、杂乱文字、水印、融化？"),
    "scale": ("比例", "产品尺寸相对身体或参照物是否合理？（无法判断选不适用）"),
}

ANSWERS = {"same": 2, "minor": 1, "different": 0, "cannot_tell": 1, "not_applicable": 2}

FIDELITY_ITEMS = ("shape", "color", "material", "text", "parts")

# 否决码：命中即不通过，不看分数
VETO_CODES = {
    "WRONG_PRODUCT": ("shape", "成品是另一个产品"),
    "COLOR_FAMILY": ("color", "颜色族系错了（不是同色系偏差）"),
    "TEXT_WRONG": ("text", "大字号文字或 Logo 错误、缺失、杜撰"),
    "PART_MISSING": ("parts", "产品少了一个部件"),
    "PART_MERGED": ("parts", "两个部件被粘成一个"),
    "PART_EXTRA": ("parts", "多出产品本来没有的部件"),
    "LEAK_HAND_MANNEQUIN": ("identity", "产品图里的手、模特假人或他人出现在成片里"),
    "SEVERE_DEFORMITY": ("artifacts", "产品主体或人体严重变形"),
}

NON_VETO_CODES = {
    "SHAPE_OFF": "轮廓或结构细节有偏差",
    "LENGTH_DRIFT": "长度跟着姿态参考走，不跟产品",
    "COLOR_OFF": "同色系内的色差",
    "MATERIAL_OFF": "质感或材质不同（玻璃/金属/织物/印花）",
    "TEXT_GARBLE": "小字糊成乱码或不可读",
    "LABEL_OCCLUDED": "手指或道具挡住了印字",
    "POSE": "姿态或取景与参考不同",
    "IDENTITY": "人物与参考模特不同",
    "ARTIFACT": "解剖错误、杂乱文字、水印、融化",
    "SCALE_OFF": "产品相对身体过大或过小",
}


def template():
    """空白评分卡。agent 填 answers，其余留给脚本。"""
    return {
        "rubric_version": RUBRIC_VERSION,
        "image_real": "",
        "image_generated": "",
        "pose_reference": "",
        "answers": {q: "" for q in QUESTIONS},
        "defects": [],
        "text_in_real": "",
        "text_in_generated": "",
        "reviewer": "",
        "reviewed_at": "",
    }


def _norm(value):
    if not isinstance(value, str):
        return None
    v = value.strip().casefold().replace("-", "_").replace(" ", "_")
    return v if v in ANSWERS else None


def validate(card):
    """结构校验。缺项、非法值一律报错——不猜、不填默认。"""
    problems = []
    if not isinstance(card, dict):
        return ["评分卡必须是 JSON 对象"]
    if card.get("rubric_version") != RUBRIC_VERSION:
        problems.append(f"rubric_version 应为 {RUBRIC_VERSION}，实际 {card.get('rubric_version')!r}")
    answers = card.get("answers")
    if not isinstance(answers, dict):
        return problems + ["缺 answers 对象"]
    for q in QUESTIONS:
        if q not in answers:
            problems.append(f"缺问题 {q}")
            continue
        if _norm(answers[q]) is None:
            problems.append(f"{q} 的答案非法：{answers[q]!r}（可选 {sorted(ANSWERS)}）")
    for defect in card.get("defects") or []:
        code = str(defect.get("code") or "")
        if code not in VETO_CODES and code not in NON_VETO_CODES:
            problems.append(f"未知缺陷码：{code}")
        if not str(defect.get("evidence") or "").strip():
            problems.append(f"缺陷 {code} 缺 evidence（看到什么）")
    return problems


def score(card):
    """算分。全部由代码完成，agent 不参与。"""
    answers = {q: _norm(v) for q, v in card["answers"].items()}
    points = {q: ANSWERS[v] for q, v in answers.items()}

    # 保真维取五问最低分：五项全 same 才是 2
    fidelity = min(points[q] for q in FIDELITY_ITEMS)
    dims = {
        "保真": fidelity,
        "姿态": points["pose"],
        "身份": points["identity"],
        "瑕疵": points["artifacts"],
        "比例": points["scale"],
    }
    total = sum(dims.values())

    defects = card.get("defects") or []
    vetos = [d for d in defects if d.get("code") in VETO_CODES]

    # cannot_tell 在保真项上阻断通过：看不清就是没验过，不能当通过
    blind = [q for q in FIDELITY_ITEMS if answers[q] == "cannot_tell"]

    reasons = []
    if vetos:
        reasons.append("否决码命中：" + "、".join(f"{d['code']}（{VETO_CODES[d['code']][1]}）" for d in vetos))
    if blind:
        reasons.append("保真项看不清：" + "、".join(blind) + "，无法确认产品一致")
    if fidelity < PASS_FIDELITY:
        reasons.append(f"保真维 {fidelity}/2 未达 {PASS_FIDELITY}/2")
    if total < PASS_TOTAL:
        reasons.append(f"总分 {total}/{len(dims) * 2} 未达 {PASS_TOTAL}")

    return {
        "rubric_version": RUBRIC_VERSION,
        "verified": not reasons,
        "fidelity": fidelity,
        "dimensions": dims,
        "total": total,
        "max_total": len(dims) * 2,
        "points": points,
        "veto_codes": [d["code"] for d in vetos],
        "blind_items": blind,
        "verdict_reasons": reasons,
        "defect_count": len(defects),
    }


def render(card, result):
    """输出给人看的评分卡。格式固定，便于历史比对。"""
    lines = [f"rubric {result['rubric_version']}", ""]
    for dim, value in result["dimensions"].items():
        mark = "✓" if value == 2 else ("!" if value == 1 else "✗")
        lines.append(f"  {mark} {dim:<4} {value} / 2")
    lines.append("  " + "-" * 40)
    verdict = "Verified（通过）" if result["verified"] else "Not verified（不通过）"
    lines.append(f"  总分 {result['total']} / {result['max_total']}    {verdict}")
    if result["veto_codes"]:
        lines.append(f"  否决：{'、'.join(result['veto_codes'])}")
    if result["blind_items"]:
        lines.append(f"  看不清：{'、'.join(result['blind_items'])}")
    if result["verdict_reasons"]:
        lines.append("  原因：")
        for reason in result["verdict_reasons"]:
            lines.append(f"    - {reason}")
    weak = [f"{q}={card['answers'][q]}" for q in QUESTIONS
            if _norm(card["answers"][q]) in ("minor", "different", "cannot_tell")]
    if weak:
        lines.append(f"  需看：{'、'.join(weak)}")
    lines.append("")
    lines.append("  这是初筛，不是证书。上架前自己再看一眼原图。")
    return "\n".join(lines)


def selftest():
    """正反用例各跑一遍，确认判据既能放行也能拦。"""
    fails = []

    def card_with(overrides=None, defects=None):
        c = template()
        for q in QUESTIONS:
            c["answers"][q] = "same"
        c["answers"].update(overrides or {})
        c["defects"] = defects or []
        return c

    # 1) 全 same → 通过
    r = score(card_with())
    if not r["verified"]:
        fails.append(f"全 same 应通过，实际 {r['verdict_reasons']}")
    if r["total"] != 10:
        fails.append(f"全 same 应 10 分，实际 {r['total']}")

    # 2) 一项 minor → 通过但不满分
    r = score(card_with({"artifacts": "minor"}))
    if not r["verified"]:
        fails.append(f"单项 minor 应仍通过，实际 {r['verdict_reasons']}")

    # 3) 保真项 different → 保真 0，必须拦
    r = score(card_with({"shape": "different"}))
    if r["verified"]:
        fails.append("保真项 different 应拦下，实际通过")

    # 4) 保真项 cannot_tell → 必须拦（看不清不能算过）
    r = score(card_with({"text": "cannot_tell"}))
    if r["verified"]:
        fails.append("保真项 cannot_tell 应拦下，实际通过")
    if "text" not in r["blind_items"]:
        fails.append("cannot_tell 应记入 blind_items")

    # 5) 非保真项 cannot_tell → 计 1 分，仍可通过
    r = score(card_with({"scale": "cannot_tell"}))
    if not r["verified"]:
        fails.append(f"非保真项 cannot_tell 应仍通过，实际 {r['verdict_reasons']}")

    # 6) 否决码 → 即使全 same 也拦
    r = score(card_with(defects=[{"code": "PART_EXTRA", "evidence": "多了一个盖子"}]))
    if r["verified"]:
        fails.append("否决码命中应拦下，实际通过")
    if "PART_EXTRA" not in r["veto_codes"]:
        fails.append("否决码未记入 veto_codes")

    # 7) 非否决缺陷 → 不阻断
    r = score(card_with(defects=[{"code": "COLOR_OFF", "evidence": "略偏暖"}]))
    if not r["verified"]:
        fails.append(f"非否决缺陷不应阻断，实际 {r['verdict_reasons']}")

    # 8) 总分不足 → 拦（保真满分但其余四项都 different）
    r = score(card_with({"pose": "different", "identity": "different",
                         "artifacts": "different", "scale": "different"}))
    if r["verified"]:
        fails.append("总分 6/10 应拦下，实际通过")

    # 9) 结构校验必须拒绝非法答案与未知缺陷码
    bad = card_with({"shape": "很好"})
    if not validate(bad):
        fails.append("非法答案应被校验拒绝")
    bad2 = card_with(defects=[{"code": "NOT_A_CODE", "evidence": "x"}])
    if not validate(bad2):
        fails.append("未知缺陷码应被校验拒绝")
    bad3 = card_with(defects=[{"code": "TEXT_GARBLE"}])
    if not validate(bad3):
        fails.append("缺 evidence 的缺陷应被校验拒绝")

    # 10) 空白模板允许空答案（它就是给人填的），但答案键必须齐全、版本号必须对
    tpl = template()
    if set(tpl["answers"]) != set(QUESTIONS):
        fails.append("空白模板的 answers 键与九问不一致")
    if tpl["rubric_version"] != RUBRIC_VERSION:
        fails.append("空白模板的 rubric_version 与实际不符")
    filled = card_with()
    if validate(filled):
        fails.append(f"填满的评分卡不应有结构错误，实际 {validate(filled)}")

    if fails:
        for f in fails:
            print(f"FAIL {f}")
        return 1
    print("selftest: 10 组用例通过（放行、拦截、否决、看不清、总分、结构校验）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="出图保真评分：九问固定，脚本算分")
    ap.add_argument("card", nargs="?", help="填好的评分卡 JSON；省略则配合 --template 输出空白卡")
    ap.add_argument("--template", action="store_true", help="输出空白评分卡")
    ap.add_argument("--json", action="store_true", help="输出 JSON 结果")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.template or not args.card:
        print(json.dumps(template(), ensure_ascii=False, indent=2))
        return 0

    path = Path(args.card)
    if not path.exists():
        print(f"评分卡不存在：{path}", file=sys.stderr)
        return 2
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"评分卡不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    problems = validate(card)
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 2

    result = score(card)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(card, result))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
