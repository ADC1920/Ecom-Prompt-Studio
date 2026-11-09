# -*- coding: utf-8 -*-
"""出图闭环：生成 → 平台机检 → 把修复句写回提示词 → 重跑，直到通过或到轮次上限。

解决的问题：机检报告一堆 fail，人要逐条翻译成提示词修改再手动重出，一轮一轮试。
这里把「报告 → 修复句 → 下一轮提示词」这一段自动化，每轮落盘，最后给一份 manifest。

用法：
  # 离线推演：给现成图，只跑判定与修复句生成，不调用任何出图 API
  python tools/run_loop.py prompt.txt --platform amazon --image out/main.png --dry-run

  # 真跑：调 qwen_image.py 出图，授权三件必填（规则见 tools/IMAGE-GEN-AUTHORIZATION.md）
  python tools/run_loop.py prompt.txt --platform amazon --generate --max-rounds 3 \
    --authorize "用户 2026-11-09 19:50 回复：可以" --purpose "产品A Amazon 主图" --unit-price 0.25

产物：--out 目录下 round-<n>/prompt.txt 与图片，以及 manifest.json。
退出码：0 通过；1 到轮次上限仍未通过；2 参数或依赖缺失。
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from check_image import ALIASES, PLATFORMS, analyze
except ImportError as e:  # 机检是本脚本的核心依赖
    sys.exit(f"缺少 check_image.py：{e}")

_slop_spec = importlib.util.find_spec("slop_check")
slop_check = None
if _slop_spec:
    from slop_check import check as slop_check

try:
    from visual_audit import audit as visual_audit_fn
except ImportError:  # 视觉验收是增强项，缺了不影响几何机检
    visual_audit_fn = None

# 机检项 → 追加到提示词的修复句。只写正向要求，不堆负面词。
FIXES = {
    "background": "背景为纯白 RGB(255,255,255)，产品底部保留自然接触阴影，不要灰底、渐变底或环境色。",
    "occupancy": "产品占画面约 85%，四周留白收紧，不要大块空白。",
    "ratio": "画面为 1:1 正方形构图，产品完整入画不裁切。",
    "size": "输出长边不少于 1600 像素，边缘锐利，材质纹理清晰。",
    "text": "画面中不出现任何文字、字母、数字、符号、水印、logo 贴片与信息卡。",
    "alpha": "背景完全不透明并铺满画面。",
    "subject": "画面必须有一个清晰完整的产品主体，不要空景或纯背景。",
    "filesize": "输出控制在 10MB 以内，保持高质量 JPEG。",
}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def generate(prompt_path, out_dir, args):
    """调 qwen_image.py 出图，返回新图路径。授权闸门在子进程内，这里只做参数完整性预检。"""
    cmd = [
        sys.executable, str(HERE / "qwen_image.py"),
        "-f", str(prompt_path), "-o", str(out_dir), "-n", "1",
        "--authorize", args.authorize, "--purpose", args.purpose,
        "--unit-price", str(args.unit_price),
    ]
    if args.size:
        cmd += ["--size", args.size]
    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]
    if args.key_file:
        cmd += ["--key-file", args.key_file]
    for ref in args.ref:
        cmd += ["-i", ref]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"出图失败：{(proc.stderr or proc.stdout).strip()[:400]}")
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("出图脚本未返回图片路径")
    return lines[-1]


def selftest():
    import tempfile

    if not Path(HERE / "check_image.py").exists():
        print("FAIL 缺少 check_image.py")
        return 1
    try:
        from PIL import Image
    except ImportError:
        print("selftest: 未安装 Pillow，跳过像素相关用例")
        return 0

    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        prompt = tmp / "p.txt"
        prompt.write_text("白底主图，产品居中，柔和顶光。", encoding="utf-8")

        # 1) 灰底小图 dry-run：应判 fail 并生成修复句
        bad = tmp / "bad.png"
        im = Image.new("RGB", (900, 1200), (208, 208, 208))
        im.paste((40, 80, 140), (250, 400, 650, 800))
        im.save(bad)
        rc = main([str(prompt), "--platform", "amazon", "--image", str(bad), "--dry-run", "--out", str(tmp / "loop1")])
        mf = json.loads((tmp / "loop1" / "manifest.json").read_text(encoding="utf-8"))
        if rc != 1:
            fails.append(f"不合格图应退出 1，实际 {rc}")
        if mf["rounds"][0]["verdict"] != "fail":
            fails.append("不合格图未判 fail")
        if not mf["rounds"][0]["fixes"]:
            fails.append("未生成修复句")
        if "纯白 RGB" not in (tmp / "loop1" / "manifest.json").read_text(encoding="utf-8"):
            fails.append("修复句未写入 manifest")

        # 2) 合规白底图 dry-run：应通过
        ok = tmp / "ok.png"
        good = Image.new("RGB", (1600, 1600), (255, 255, 255))
        good.paste((40, 80, 140), (80, 80, 1520, 1520))
        good.save(ok)
        rc = main([str(prompt), "--platform", "amazon", "--image", str(ok), "--dry-run", "--out", str(tmp / "loop2")])
        mf2 = json.loads((tmp / "loop2" / "manifest.json").read_text(encoding="utf-8"))
        if rc != 0:
            fails.append(f"合规图应退出 0，实际 {rc}")
        if mf2["result"] != "passed":
            fails.append(f"合规图未判 passed：{mf2['result']}")

        # 3) 真跑模式缺授权参数必须被拦住，且不产生任何调用
        rc = main([str(prompt), "--platform", "amazon", "--generate", "--dry-run", "--out", str(tmp / "loop3")])
        if rc != 2:
            fails.append(f"缺授权参数应退出 2，实际 {rc}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 3 组用例全部通过")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="出图闭环：机检不过就把修复句写回提示词重跑")
    ap.add_argument("prompt", nargs="?", help="提示词文件")
    ap.add_argument("--platform", default="generic", help="平台名，见 tools/check_image.py 的 PLATFORMS")
    ap.add_argument("--image", help="离线模式待检图")
    ap.add_argument("--ref", action="append", default=[], help="生成模式的参考图，可重复")
    ap.add_argument("--generate", action="store_true", help="真跑出图（需授权三件）")
    ap.add_argument("--dry-run", action="store_true", help="只做判定与修复句推演，不出图")
    ap.add_argument("--max-rounds", type=int, default=3, help="最多几轮，默认 3")
    ap.add_argument("--out", default="out/loop", help="产物目录，默认 out/loop")
    ap.add_argument("--size", help="出图尺寸，透传给 qwen_image.py")
    ap.add_argument("--seed", type=int, help="固定种子")
    ap.add_argument("--key-file", help="密钥文件，透传给 qwen_image.py")
    ap.add_argument("--authorize", help="用户授权凭证（用户原话或带日期说明）")
    ap.add_argument("--purpose", help="这批图的用途与落点")
    ap.add_argument("--unit-price", type=float, help="每张单价（元）")
    ap.add_argument("--selftest", action="store_true", help="离线自检")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.prompt:
        print("缺少提示词文件参数", file=sys.stderr)
        return 2

    if args.generate and args.dry_run:
        args.generate = False
    if args.generate and not (args.authorize and args.purpose and args.unit_price is not None):
        print("真跑模式必须给全 --authorize / --purpose / --unit-price（规则见 tools/IMAGE-GEN-AUTHORIZATION.md）", file=sys.stderr)
        return 2
    if not args.generate and not args.image:
        print("离线模式必须用 --image 指定待检图", file=sys.stderr)
        return 2
    if args.max_rounds < 1:
        print("--max-rounds 至少 1", file=sys.stderr)
        return 2

    prompt_file = Path(args.prompt)
    if not prompt_file.exists():
        print(f"提示词文件不存在：{prompt_file}", file=sys.stderr)
        return 2
    platform = ALIASES.get(args.platform, args.platform)
    if platform not in PLATFORMS:
        print(f"未知平台 {args.platform}，可选：{', '.join(sorted(PLATFORMS))}", file=sys.stderr)
        return 2
    spec = PLATFORMS[platform]

    current = prompt_file.read_text(encoding="utf-8-sig").strip()
    loop_dir = Path(args.out)
    loop_dir.mkdir(parents=True, exist_ok=True)
    rounds, result, total_cost = [], "exhausted", 0.0

    # 离线模式的图不会变，多轮只是重复同一份判定；只跑一轮，把修复句给出来即可。
    rounds_cap = args.max_rounds if args.generate else 1
    if not args.generate and args.max_rounds > 1:
        print("离线模式图不变，只跑 1 轮；要看多轮演进请用 --generate", file=sys.stderr)

    for n in range(1, rounds_cap + 1):
        rd = loop_dir / f"round-{n}"
        rd.mkdir(parents=True, exist_ok=True)
        round_prompt = rd / "prompt.txt"
        round_prompt.write_text(current + "\n", encoding="utf-8")

        issues = slop_check(current) if slop_check else []
        slop_stat = {
            "error": sum(1 for i in issues if i["level"] == "error"),
            "warn": sum(1 for i in issues if i["level"] == "warn"),
        }

        entry = {"round": n, "prompt": str(round_prompt), "prompt_sha": sha(current), "slop": slop_stat}
        try:
            if args.generate:
                image = generate(round_prompt, rd, args)
                total_cost += args.unit_price or 0
                entry["cost"] = round(args.unit_price or 0, 3)
            else:
                image = args.image
        except RuntimeError as e:
            entry["error"] = str(e)
            rounds.append(entry)
            break

        checks, metrics = analyze(image, spec)
        failed = [c for c in checks if c["status"] == "fail"]
        entry.update({
            "image": image,
            "verdict": "fail" if failed else "pass",
            "fails": [c["id"] for c in failed],
            "skipped": [c["id"] for c in checks if c["status"] == "skipped"],
            "metrics": metrics,
        })
        # 视觉验收只记录不判定：一致度与 AI 感是启发式，不能替代人看
        if args.ref and visual_audit_fn:
            try:
                entry["visual"] = visual_audit_fn(image, args.ref[0])
            except Exception as e:  # 审计失败不该中断闭环
                entry["visual"] = {"error": str(e)[:160]}
        rounds.append(entry)

        if not failed:
            result = "passed"
            break

        fix_list = [{"id": c["id"], "text": FIXES[c["id"]]} for c in failed if c["id"] in FIXES]
        entry["fixes"] = fix_list
        if not fix_list:
            break
        # 下一轮：原提示词 + 修复句。累积写，保留每一轮改过什么，便于回看。
        current = current + "\n" + "".join(f["text"] for f in fix_list)

    manifest = {
        "tool": "run_loop.py",
        "mode": "generate" if args.generate else "dry-run",
        "platform": platform,
        "max_rounds": args.max_rounds,
        "prompt_file": str(prompt_file),
        "result": result,
        "total_cost": round(total_cost, 3),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rounds": rounds,
    }
    (loop_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (loop_dir / "final-prompt.txt").write_text(current + "\n", encoding="utf-8")

    print(f"{platform} · {manifest['mode']} · {len(rounds)} 轮 · {result}")
    for r in rounds:
        line = f"  round-{r['round']}: {r.get('verdict', r.get('error', '-'))}"
        if r.get("fails"):
            line += f"  fail={','.join(r['fails'])}"
        if r.get("fixes"):
            line += f"  修复句 {len(r['fixes'])} 条"
        if r.get("cost"):
            line += f"  花费 {r['cost']}"
        v = r.get("visual") or {}
        if v.get("consistency"):
            line += f"  一致度 {v['consistency']['score']}"
        if v.get("ai_smell"):
            line += f"  AI感 {v['ai_smell']['score']}"
        print(line)
    print(f"  manifest: {loop_dir / 'manifest.json'}")
    print(f"  final:    {loop_dir / 'final-prompt.txt'}")
    return 0 if result == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
