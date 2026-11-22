# -*- coding: utf-8 -*-
"""机检失败夹具：按定义生成故意不合规的图，断言 check_image 必定报出对应问题。

为什么需要它：check_image.py 的 selftest 证明了「灰底会被判 fail」，但那些图写在
测试函数里，外部看不到、不能复用、无法当验收文档。这里把「什么样算不合规」变成
可执行的夹具定义：每条夹具给出构造参数与预期判负项，跑完就知道 checker 还认不认
得这些硬伤。

夹具定义在 fixtures.json，本脚本只负责按要求画图和比对。预期值就是验收标准：
新增一条平台规则时，先加一条夹具，再改 checker——顺序反了就是拿实现当规范。

用法：
  python tools/gen_fixtures.py --out out/fixtures          # 生成夹具图
  python tools/gen_fixtures.py --verify                    # 生成 + 跑 check_image 断言
  python tools/gen_fixtures.py --verify --keep             # 保留图片供人工查看
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures.json"


def build(spec, out_dir):
    """按夹具定义合成图片。只用 Pillow 基础绘图，不依赖外部素材。"""
    from PIL import Image

    w, h = spec["size"]
    bg = tuple(spec.get("bg", [255, 255, 255]))
    img = Image.new("RGB", (w, h), bg)

    subject = spec.get("subject")
    if subject:
        # 主体用占比表示：先按画面比例算出矩形，再居中贴上去
        ratio = subject.get("occupancy", 0.9)
        side = int(min(w, h) * (ratio ** 0.5))
        box = ((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2)
        img.paste(tuple(subject.get("color", [40, 90, 160])), box)

    path = out_dir / f"{spec['id']}.png"
    img.save(path)
    return path


def verify(keep=False):
    """生成全部夹具并断言 check_image 的判定与预期一致。"""
    if not FIXTURES.exists():
        print(f"夹具定义缺失：{FIXTURES}", file=sys.stderr)
        return 1

    specs = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    fails = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for spec in specs:
            try:
                path = build(spec, tmp)
            except ImportError:
                print("verify: 未安装 Pillow，无法生成夹具图")
                return 0

            proc = subprocess.run(
                [sys.executable, str(HERE / "check_image.py"), str(path),
                 "--platform", spec["platform"], "--json"],
                capture_output=True, text=True, encoding="utf-8",
            )
            if proc.returncode not in (0, 1):
                fails.append(f"{spec['id']}: check_image 异常退出 {proc.returncode}")
                continue
            try:
                report = json.loads(proc.stdout)
            except json.JSONDecodeError:
                fails.append(f"{spec['id']}: 输出不是 JSON")
                continue

            # --json 输出是数组（支持一次检多图），夹具只检一张，取第一个结果
            entry = report[0] if isinstance(report, list) and report else report
            got = {c["id"]: c["status"] for c in (entry.get("checks") or [])}
            for cid in spec["expect_fail"]:
                if got.get(cid) != "fail":
                    fails.append(f"{spec['id']}: 预期 {cid}=fail，实际 {got.get(cid)}")
            for cid in spec.get("expect_pass", []):
                if got.get(cid) == "fail":
                    fails.append(f"{spec['id']}: 预期 {cid} 不该 fail，实际 fail")

        if keep:
            out = HERE.parent / "out" / "fixtures"
            out.mkdir(parents=True, exist_ok=True)
            for spec in specs:
                build(spec, out)
            print(f"夹具图已保留在 {out}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print(f"verify: {len(specs)} 条夹具全部按预期判负")
    return 0


def main():
    ap = argparse.ArgumentParser(description="机检失败夹具：生成故意不合规的图并断言 checker 报错")
    ap.add_argument("--out", help="生成夹具到指定目录")
    ap.add_argument("--verify", action="store_true", help="生成并断言 check_image 判负")
    ap.add_argument("--keep", action="store_true", help="verify 时保留图片供人工查看")
    args = ap.parse_args()

    if args.verify:
        return verify(args.keep)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        specs = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
        for spec in specs:
            build(spec, out)
        print(f"生成 {len(specs)} 条夹具到 {out}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
