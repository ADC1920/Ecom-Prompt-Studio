# -*- coding: utf-8 -*-
"""视觉复核清单生成器：把「该人看什么」整理成一份带图的复核单。

为什么这样做而不是直接调模型判图：VLM 判图在「精确编辑是否生效、保留约束是否满足」
这类细粒度判断上并不可靠（EditJudge-Bench 2026 实测），把它的分数当通过/不通过依据
会把错误固化。所以这里只做两件事：

1. 用 visual_audit 的启发式给出嫌疑分（提示复核，不判定）
2. 生成一份结构化复核清单：每个原子自带的检查项 + 保留清单，逐条留空等人填

结论永远由人给。脚本不输出 pass。

用法：
  python tools/vlm_review.py --atom a21 --image out/main-01.png
  python tools/vlm_review.py --atom a21 --image out/main-01.png --ref product.jpg --out out/review.md
  python tools/vlm_review.py --selftest
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
ATOM_DIR = REPO_ROOT / "ecom-prompt-sop" / "references" / "_atoms"


def load_atom(atom_id):
    p = ATOM_DIR / f"{atom_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def audit_scores(image, ref=None):
    """调 visual_audit 拿启发式分数。失败不影响复核单生成。"""
    argv = [sys.executable, str(HERE / "visual_audit.py"), image, "--json"]
    if ref:
        argv += ["--ref", ref]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return None
    raw = (p.stdout or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def build_review(atom, image, audit):
    lines = []
    title = atom.get("title") or atom.get("id")
    lines.append(f"# 视觉复核单 · {title}")
    lines.append("")
    lines.append(f"- 原子：`{atom.get('id')}`")
    lines.append(f"- 待检图：`{image}`")
    lines.append("- 结论：**待人工填写**（本单不给通过/不通过）")
    lines.append("")

    lines.append("## 启发式嫌疑分")
    lines.append("")
    if audit is None:
        lines.append("visual_audit 未能运行（可能缺 Pillow）。这一节留空，不影响下游复核。")
    else:
        items = audit if isinstance(audit, list) else [audit]
        for it in items:
            if not isinstance(it, dict):
                continue
            ai = it.get("ai_feel") or it.get("ai_score") or "—"
            cons = it.get("consistency") or it.get("similarity") or "—"
            lines.append(f"- `{it.get('file', image)}`：AI 感 {ai}，与参考图一致度 {cons}")
        lines.append("")
        lines.append("这两项都是启发式，只用于指示「先看哪里」，不能作为通过依据。")
    lines.append("")

    lines.append("## 逐条复核")
    lines.append("")
    lines.append("| 判据 | 结论（通过/不通过/不适用） | 证据 |")
    lines.append("|---|---|---|")
    for c in (atom.get("checklists") or []):
        if isinstance(c, dict):
            for item in (c.get("items") or []):
                lines.append(f"| {item} |  |  |")
        else:
            lines.append(f"| {c} |  |  |")
    if not (atom.get("checklists") or []):
        lines.append("| 该原子无内置清单，按工位门禁逐条核对 |  |  |")
    lines.append("")

    lines.append("## 产品保留清单逐项核对")
    lines.append("")
    lines.append("出图必须与参考图是同一个产品。逐项打勾，任何一项不一致就重出：")
    lines.append("")
    lines.append("| 特征 | 一致 | 不一致 |")
    lines.append("|---|---|---|")
    for feat in ("形状与比例", "颜色", "材质纹理", "logo 位置与内容", "结构细节（接缝/按键/纹理方向）"):
        lines.append(f"| {feat} |  |  |")
    lines.append("")

    lines.append("## 必须人工确认（机检覆盖不到）")
    lines.append("")
    lines.append("- 模特造型是否符合人物政策")
    lines.append("- AI 标注义务是否已履行（见 `_rules/aigc-disclosure.json`）")
    lines.append("- 是否货不对板（图与实物不一致）")
    lines.append("")
    return "\n".join(lines)


def selftest():
    fails = []
    atom = load_atom("a21")
    if atom is None:
        fails.append("a21 原子读取失败")

    md = build_review(atom or {"id": "a21", "title": "t"}, "out/x.png", None)
    if "待人工填写" not in md:
        fails.append("复核单缺少人工结论占位")
    if "通过/不通过" not in md:
        fails.append("复核单未声明结论由人工给")
    for feat in ("形状与比例", "颜色", "材质纹理"):
        if feat not in md:
            fails.append(f"复核单缺少保留清单项：{feat}")

    bad = load_atom("a99")
    if bad is not None:
        fails.append("不存在的原子应返回 None")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 复核单结构、人工结论占位、保留清单、未知原子处理 全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="视觉复核清单生成器（只提示，不判定）")
    ap.add_argument("--atom", help="原子编号，如 a21")
    ap.add_argument("--image", help="待检图片路径")
    ap.add_argument("--ref", help="可选，产品参考图，用于一致性启发式")
    ap.add_argument("--out", help="可选，写入文件；不给则打印到 stdout")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.atom or not args.image:
        ap.print_help()
        return 2

    atom = load_atom(args.atom)
    if atom is None:
        print(f"原子不存在：{args.atom}", file=sys.stderr)
        return 2
    if not Path(args.image).exists():
        print(f"图片不存在：{args.image}", file=sys.stderr)
        return 2

    audit = audit_scores(args.image, args.ref)
    md = build_review(atom, args.image, audit)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"复核单已写入 {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
