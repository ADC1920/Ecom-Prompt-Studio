# -*- coding: utf-8 -*-
"""触发用例一致性检查（零依赖，Python 标准库）。

用途：evals/cases.json 是机器可读源，tools/trigger-cases.md 是人类可读视图。
本脚本保证两边不漂移，并确认每条预期路径在仓库里真实存在。

检查项：
1. cases.json 与 trigger-cases.md 的用例编号集合一致
2. 两边同一编号的输入文本一致
3. 两边对技能归属的判定一致（ecom-prompt-sop / 两个导演 / 不触发）
4. expect.doc_contains 至少命中一个真实 SOP 文件
5. 负例必须是 skill=none，且不带 doc_contains

用法: python evals/check_cases.py [仓库根]，退出码 0 通过，1 失败。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
CASES_JSON = ROOT / "evals" / "cases.json"
CASES_MD = ROOT / "tools" / "trigger-cases.md"
SOP_ROOT = ROOT / "ecom-prompt-sop"

ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
SKILLS = ["ecom-main-image-prompts", "ecom-detail-page-prompts", "ecom-prompt-sop"]


def expected_skill_from_cell(cell: str) -> str:
    if "不触发" in cell:
        return "none"
    for name in SKILLS:
        if name in cell:
            return name
    return ""


def load_markdown_cases() -> dict:
    rows = {}
    for line in CASES_MD.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        num, text, expected = m.groups()
        if not num.isdigit():
            continue
        rows[int(num)] = {"input": text.strip(), "skill": expected_skill_from_cell(expected)}
    return rows


def main() -> int:
    problems = []
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = {int(c["id"]): c for c in data["cases"]}
    md_cases = load_markdown_cases()

    if set(cases) != set(md_cases):
        only_json = sorted(set(cases) - set(md_cases))
        only_md = sorted(set(md_cases) - set(cases))
        problems.append(f"用例编号不一致：仅 cases.json {only_json}，仅 trigger-cases.md {only_md}")

    for cid in sorted(set(cases) & set(md_cases)):
        c, md = cases[cid], md_cases[cid]
        if c["input"].strip() != md["input"]:
            problems.append(f"#{cid} 输入不一致：cases.json「{c['input']}」 vs trigger-cases.md「{md['input']}」")
        if c["expect"]["skill"] != md["skill"]:
            problems.append(f"#{cid} 技能判定不一致：cases.json {c['expect']['skill']} vs trigger-cases.md {md['skill'] or '(未识别)'}")

    for cid, c in sorted(cases.items()):
        expect = c["expect"]
        doc = expect.get("doc_contains", "")
        if expect["skill"] == "none":
            if doc:
                problems.append(f"#{cid} 负例不应带 doc_contains")
            continue
        if expect["skill"] != "ecom-prompt-sop":
            if doc:
                problems.append(f"#{cid} 转交导演技能时不应断言 SOP 路径")
            continue
        if not doc:
            problems.append(f"#{cid} 命中 SOP 库但缺少 doc_contains")
            continue
        matched = list(SOP_ROOT.rglob(f"*{Path(doc).name}*.md"))
        if not matched:
            problems.append(f"#{cid} doc_contains 找不到对应 SOP：{doc}")

    for p in problems:
        print(f"错误: {p}")
    if problems:
        print(f"结果: 错误 {len(problems)}（不通过）")
        return 1
    print(f"结果: 用例 {len(cases)} 条，cases.json 与 trigger-cases.md 一致，路径全部有效（通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
