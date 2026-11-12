# -*- coding: utf-8 -*-
"""真实 agent 触发评测：验证装进真实引擎后技能会不会真的被触发。

和 evals/ 的现有触发回归不是一回事：那边的做法是把 description 与路由表喂给模型，
只断言它输出的路由结论；模型本身没有装技能的概念，所以抓不到「装了但没触发」这类问题。
这一套改动是把同一个技能目录交给真引擎，看它是否自行加载并走到正确原子。

三层分工（借 NVIDIA SkillEvaluator 的分层思路）：
- Tier 1 静态检查：tools/lint_skills.py，每次提交跑
- Tier 2 近似触发：evals/，每次 PR 跑，便宜
- Tier 3 真实触发：本脚本，只在里程碑手动跑，慢且可能计费

用法：
  # 先看会跑哪些用例、大概花多少（不发请求）
  python evals/real_trigger.py --dry-run

  # 真跑（需要引擎可执行文件与凭据，按你的环境自备）
  python evals/real_trigger.py --engine "claude -p" --limit 5

  # 只跑某几条用例
  python evals/real_trigger.py --engine "claude -p" --ids 1,17,20,23

引擎约定：命令从 stdin 读提示词，把回答写到 stdout。任何满足这条约定的引擎都能接
（claude -p、zcode -p、codex exec 等）。脚本不假设具体引擎的旗标。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
CASES = HERE / "cases.json"


def load_cases():
    data = json.loads(CASES.read_text(encoding="utf-8"))
    return data.get("cases") or data.get("items") or []


def build_prompt(case):
    """真实引擎里技能由引擎自己加载，这里只发用户原话。"""
    return case.get("input") or ""


def parse_reply(text):
    """从回答里找技能名与原子编号。真实引擎输出是自由文本，只做宽松提取。"""
    skills = set()
    for name in ("ecom-prompt-sop", "ecom-main-image-prompts", "ecom-detail-page-prompts"):
        if name in text:
            skills.add(name)
    atoms = set(re.findall(r"\ba(\d{2})\b", text, re.I))
    return {"skills": sorted(skills), "atoms": ["a" + a.zfill(2) for a in sorted(atoms)]}


def judge(case, reply):
    """对照用例预期判命中。只用包含匹配，避免把格式差异当成错。"""
    expect = case.get("expect") or {}
    got = parse_reply(reply)
    problems = []

    want_skill = expect.get("skill")
    if want_skill and want_skill not in got["skills"]:
        problems.append(f"未出现预期技能 {want_skill}（实际 {got['skills'] or '无'}）")

    want_atom = expect.get("atom")
    if want_atom and want_atom not in got["atoms"]:
        problems.append(f"未出现预期原子 {want_atom}（实际 {got['atoms'] or '无'}）")

    return (not problems), problems, got


def run_engine(engine, prompt, timeout):
    try:
        p = subprocess.run(
            engine, input=prompt, shell=True, capture_output=True,
            text=True, encoding="utf-8", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"超时（{timeout}s）"
    except OSError as e:
        return None, f"无法启动引擎：{e}"
    if p.returncode != 0:
        return None, f"引擎退出码 {p.returncode}：{(p.stderr or '')[:200]}"
    return p.stdout or "", None


def main():
    ap = argparse.ArgumentParser(description="真实 agent 触发评测（Tier 3）")
    ap.add_argument("--engine", help="引擎命令，从 stdin 读提示词、stdout 输出回答")
    ap.add_argument("--limit", type=int, help="只跑前 N 条")
    ap.add_argument("--ids", help="逗号分隔的用例 id，如 1,17,20,23")
    ap.add_argument("--timeout", type=int, default=180, help="单条超时秒数，默认 180")
    ap.add_argument("--json", action="store_true", help="输出 JSON 汇总")
    ap.add_argument("--dry-run", action="store_true", help="只列出将跑的用例，不发请求")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    cases = load_cases()
    if not cases:
        print(f"没有读到用例：{CASES}", file=sys.stderr)
        return 2

    if args.ids:
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        cases = [c for c in cases if str(c.get("id")) in want]
    if args.limit:
        cases = cases[: args.limit]

    if args.dry_run or not args.engine:
        print(f"将跑 {len(cases)} 条用例（真实引擎评测，可能计费）：")
        for c in cases:
            exp = c.get("expect") or {}
            print(f"  #{c.get('id')}  {c.get('input')}  →  {exp.get('skill', '-')} / {exp.get('atom', '-')}")
        if not args.engine:
            print("\n未提供 --engine，仅列出。加 --engine \"<命令>\" 才会真跑。")
        return 0

    if shutil.which(args.engine.split()[0]) is None:
        print(f"找不到引擎命令：{args.engine.split()[0]}", file=sys.stderr)
        return 2

    results = []
    for c in cases:
        reply, err = run_engine(args.engine, build_prompt(c), args.timeout)
        if err:
            results.append({"id": c.get("id"), "ok": False, "problems": [err], "got": None})
            continue
        ok, problems, got = judge(c, reply)
        results.append({"id": c.get("id"), "ok": ok, "problems": problems, "got": got})

    passed = sum(1 for r in results if r["ok"])
    if args.json:
        print(json.dumps({"total": len(results), "passed": passed, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"{mark}  #{r['id']}")
            for p in r["problems"]:
                print(f"      {p}")
        print(f"\n{passed}/{len(results)} 通过")

    # 与 evals/README.md 的基线表对比：这里只报告，不擅自改基线
    if passed < len(results):
        print("\n有失败项。真实触发失败通常意味着 description 或路由表在实际引擎里不够强，"
              "而不是用例写错了——先看命中的是哪个技能，再决定改描述还是改判据。", file=sys.stderr)
        return 1
    return 0


def selftest():
    fails = []

    ok, problems, got = judge({"expect": {"skill": "ecom-prompt-sop", "atom": "a21"}},
                              "我用 ecom-prompt-sop 的 a21 来做")
    if not ok:
        fails.append(f"应命中却判失败：{problems}")

    ok, problems, _ = judge({"expect": {"skill": "ecom-main-image-prompts"}},
                            "走 ecom-prompt-sop 的 a03")
    if ok:
        fails.append("技能不匹配应判失败")

    ok, _, _ = judge({"expect": {"atom": "a21"}}, "用 a3 做")
    if ok:
        fails.append("原子编号不完整时不应误判为 a21")

    got = parse_reply("选 a03 和 a21")
    if sorted(got["atoms"]) != ["a03", "a21"]:
        fails.append(f"原子提取错误：{got['atoms']}")

    cases = load_cases()
    if not cases:
        fails.append("用例读取失败")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 命中判定、不匹配判定、编号提取、用例读取 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
