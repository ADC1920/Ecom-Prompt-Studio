# -*- coding: utf-8 -*-
"""修复句效果统计：从闭环跑出来的 manifest 里算出哪条修复句真正管用。

闭环每轮会记下「这次因为哪些机检项失败、追加了哪些修复句」。把多轮结果聚合起来，
就能知道：写纯白背景那句到底让多少张图过了白底、写 1:1 那句的命中率是多少。
以后调整修复句措辞，用这份统计判断是变好还是变坏。

用法：
  python tools/fix_stats.py                       # 读 out/loop 下全部 manifest
  python tools/fix_stats.py --dir out/loop --json
  python tools/fix_stats.py --selftest

退出码：0 正常；1 没有可统计的数据；2 路径错误。
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

FIX_LABEL = {
    "background": "背景纯白",
    "occupancy": "主体占比",
    "ratio": "画面比例",
    "size": "输出尺寸",
    "text": "图内文字",
    "alpha": "透明通道",
    "subject": "主体缺失",
    "filesize": "文件大小",
}


def load_manifests(base):
    base = Path(base)
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("manifest.json")):
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def analyze(manifests):
    """按修复句统计：尝试次数、下一轮该 fail 消失的次数、成功率。"""
    stats = defaultdict(lambda: {"attempts": 0, "fixed": 0, "texts": set()})
    total_rounds, passed, exhausted = 0, 0, 0
    for _, mf in manifests:
        rounds = mf.get("rounds") or []
        total_rounds += len(rounds)
        if mf.get("result") == "passed":
            passed += 1
        elif mf.get("result") == "exhausted":
            exhausted += 1

        for i, r in enumerate(rounds[:-1]):
            nxt = rounds[i + 1]
            prev = set(r.get("fails") or [])
            after = set(nxt.get("fails") or [])
            for f in r.get("fixes") or []:
                fid = f.get("id") if isinstance(f, dict) else None
                if not fid:
                    continue
                stats[fid]["attempts"] += 1
                if fid not in after:
                    stats[fid]["fixed"] += 1
                if isinstance(f, dict) and f.get("text"):
                    stats[fid]["texts"].add(f["text"])

    rows = []
    for fid, s in stats.items():
        rate = s["fixed"] / s["attempts"] if s["attempts"] else 0.0
        rows.append({
            "id": fid,
            "label": FIX_LABEL.get(fid, fid),
            "attempts": s["attempts"],
            "fixed": s["fixed"],
            "rate": round(rate, 3),
        })
    rows.sort(key=lambda r: (-r["rate"], -r["attempts"]))
    return {
        "manifests": len(manifests),
        "passed": passed,
        "exhausted": exhausted,
        "avg_rounds": round(total_rounds / len(manifests), 2) if manifests else 0,
        "fixes": rows,
    }


def selftest():
    fails = []
    m1 = {"result": "passed", "rounds": [
        {"round": 1, "verdict": "fail", "fails": ["background", "ratio"],
         "fixes": [{"id": "background", "text": "背景纯白"}, {"id": "ratio", "text": "1:1"}]},
        {"round": 2, "verdict": "pass", "fails": [], "fixes": []},
    ]}
    m2 = {"result": "exhausted", "rounds": [
        {"round": 1, "verdict": "fail", "fails": ["background"],
         "fixes": [{"id": "background", "text": "背景纯白"}]},
        {"round": 2, "verdict": "fail", "fails": ["background", "occupancy"],
         "fixes": [{"id": "background", "text": "背景纯白"}, {"id": "occupancy", "text": "占比 85%"}]},
        {"round": 3, "verdict": "fail", "fails": ["occupancy"], "fixes": []},
    ]}
    got = analyze([("a", m1), ("b", m2)])
    if got["manifests"] != 2 or got["passed"] != 1 or got["exhausted"] != 1:
        fails.append(f"汇总计数错误：{got}")

    rows = {r["id"]: r for r in got["fixes"]}
    if rows["ratio"]["rate"] != 1.0:
        fails.append(f"ratio 修复率应为 1.0，实际 {rows['ratio']['rate']}")
    # background 共 3 次尝试：m1 第 1 轮成功、m2 第 1 轮失败、m2 第 2 轮成功 → 2/3
    if rows["background"]["attempts"] != 3 or rows["background"]["fixed"] != 2:
        fails.append(f"background 统计错误：{rows['background']}")
    if rows["occupancy"]["attempts"] != 1 or rows["occupancy"]["fixed"] != 0:
        fails.append(f"occupancy 统计错误：{rows['occupancy']}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 4 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="修复句效果统计")
    ap.add_argument("--dir", default="out/loop", help="manifest 所在目录，默认 out/loop")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not Path(args.dir).exists():
        print(f"目录不存在：{args.dir}", file=sys.stderr)
        return 2

    manifests = load_manifests(args.dir)
    if not manifests:
        print(f"{args.dir} 下没有 manifest.json，先跑一次出图闭环", file=sys.stderr)
        return 1

    got = analyze(manifests)
    if not got["fixes"]:
        if got["avg_rounds"] <= 1:
            print("这些 manifest 都是单轮的（dry-run 只跑一轮），没有「下一轮」可比，判断不了修复句有没有效。"
                  "\n要看修复统计，用 --generate 跑真闭环（缺授权时有授权闸门拦着，不会真的花钱）。", file=sys.stderr)
        else:
            print("manifest 里有轮次但没记修复句：可能是旧格式（fixes 是字符串而非 {id, text}）。"
                  "\n当前版本闭环写的是带 id 的对象，重跑一次闭环即可。", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(got, ensure_ascii=False, indent=2))
        return 0

    print(f"闭环 {got['manifests']} 次 · 通过 {got['passed']} · 耗尽 {got['exhausted']} · 平均 {got['avg_rounds']} 轮")
    print()
    print(f"{'机检项':10} {'修复句':10} {'尝试':>4} {'生效':>4} {'成功率':>7}")
    for r in got["fixes"]:
        print(f"{r['id']:10} {r['label']:10} {r['attempts']:>4} {r['fixed']:>4} {r['rate']*100:>6.0f}%")
    low = [r for r in got["fixes"] if r["attempts"] >= 2 and r["rate"] < 0.5]
    if low:
        print()
        print("命中率低于 50% 的修复句，说明措辞没被模型执行，建议改写：")
        for r in low:
            print(f"  {r['id']}（{r['label']}）{r['fixed']}/{r['attempts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
