# -*- coding: utf-8 -*-
"""出图后平台机检：把 platform-rules.md 里能机检的硬约束落成检查。

检查项：格式、尺寸、比例、文件大小、透明通道、背景纯度、主体占比、图内文字。
平台基线见下方 PLATFORMS 表，取值是保守基线，不是平台审核结论；平台官方规则更新时以官方为准。

用法：
  python tools/check_image.py out/main-01.png --platform amazon
  python tools/check_image.py out/main-01.png --platform amazon --fix
  python tools/check_image.py out/*.png --platform tiktok-shop --json --strict
  python tools/check_image.py --selftest

退出码：0 无 fail；1 有 fail（--strict 时 warn 也算失败）；2 缺 Pillow，只能做结构检查。
仅依赖 Pillow；OCR 另需 pytesseract 与 tesseract，缺失时明确标 skipped，不算通过。
"""
import argparse
import json
import os
import struct
import sys
import warnings
from pathlib import Path

try:
    from PIL import Image, ImageChops

    HAS_PIL = True
except ImportError:  # 缺 Pillow 时降级为结构检查，不阻断
    HAS_PIL = False

# 保守基线。ratio / ratio_tol：目标比例与容差；white_tol：与纯白的单通道容差；
# occupancy_min：主体 bbox 面积比下限；long_side_min：长边像素下限；max_bytes：文件大小上限。
PLATFORMS = {
    "amazon": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=True, white_tol=6, border_white_min=0.98,
                   occupancy_min=0.85, long_side_min=1600, max_bytes=10 * 1024 * 1024, text_allowed=False),
    "amazon-aplus": dict(ratio=None, ratio_tol=0.05, white_bg=False, white_tol=12, border_white_min=0.90,
                         occupancy_min=0.60, long_side_min=1200, max_bytes=10 * 1024 * 1024, text_allowed=True),
    "tiktok-shop": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=False, white_tol=12, border_white_min=0.90,
                        occupancy_min=0.65, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=False),
    "temu": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=True, white_tol=8, border_white_min=0.95,
                 occupancy_min=0.80, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=False),
    "taobao": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=False, white_tol=12, border_white_min=0.88,
                   occupancy_min=0.65, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=True),
    "tmall": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=True, white_tol=8, border_white_min=0.95,
                  occupancy_min=0.80, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=False),
    "jd": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=True, white_tol=8, border_white_min=0.95,
               occupancy_min=0.80, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=False),
    "shopee": dict(ratio=(1, 1), ratio_tol=0.02, white_bg=False, white_tol=12, border_white_min=0.88,
                   occupancy_min=0.65, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=True),
    "douyin": dict(ratio=(3, 4), ratio_tol=0.03, white_bg=False, white_tol=12, border_white_min=0.80,
                   occupancy_min=0.55, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=True),
    "xiaohongshu": dict(ratio=(3, 4), ratio_tol=0.03, white_bg=False, white_tol=12, border_white_min=0.80,
                        occupancy_min=0.55, long_side_min=800, max_bytes=10 * 1024 * 1024, text_allowed=True),
    "shopify": dict(ratio=None, ratio_tol=0.05, white_bg=False, white_tol=12, border_white_min=0.85,
                    occupancy_min=0.55, long_side_min=800, max_bytes=20 * 1024 * 1024, text_allowed=True),
    "generic": dict(ratio=(1, 1), ratio_tol=0.03, white_bg=False, white_tol=12, border_white_min=0.88,
                    occupancy_min=0.65, long_side_min=800, max_bytes=20 * 1024 * 1024, text_allowed=True),
}

ALIASES = {
    "amazon-us": "amazon", "amazon.com": "amazon", "亚马逊": "amazon",
    "tiktok": "tiktok-shop", "tk": "tiktok-shop",
    "pdd": "temu", "拼多多": "temu",
    "tb": "taobao", "淘宝": "taobao", "天猫": "tmall",
    "京东": "jd",
    "lazada": "shopee", "虾皮": "shopee",
    "抖音": "douyin", "小红书": "xiaohongshu",
    "独立站": "shopify",
}

STAT_RATIO_BG_TOL = 24      # 与背景色的欧氏距离阈值，超过视为前景
BBOX_TRIM = 0.005           # bbox 抗噪：前后各裁掉 0.5% 的极值坐标
SAMPLE_SIDE = 512           # 统计用缩略图长边，够用且避免逐像素遍历大图


def probe_size(path):
    """纯标准库读 PNG/JPEG 尺寸，Pillow 缺失时的兜底。返回 (w, h, fmt) 或 None。"""
    with open(path, "rb") as f:
        head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", head[16:24])
            return w, h, "PNG"
        if head[:2] == b"\xff\xd8":
            f.seek(2)
            while True:
                b = f.read(1)
                while b and b != b"\xff":
                    b = f.read(1)
                if not b:
                    return None
                marker = f.read(1)
                if not marker or marker in b"\xd8\xd9":
                    continue
                seg = f.read(2)
                if len(seg) < 2:
                    return None
                length = struct.unpack(">H", seg)[0]
                if marker[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                    data = f.read(5)
                    if len(data) < 5:
                        return None
                    h, w = struct.unpack(">HH", data[1:5])
                    return w, h, "JPEG"
                f.seek(length - 2, 1)
    return None


def _median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 0


def _pixels(im):
    """取像素列表；Pillow 12 起 getdata 标记弃用，这里统一抑制告警并保留旧接口。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return list(im.getdata())


def corner_background(small):
    """四角采样 + 中位数，得到背景色估计。产品图背景通常占四角。"""
    w, h = small.size
    n = max(2, min(w, h) // 12)
    boxes = [(0, 0, n, n), (w - n, 0, w, n), (0, h - n, n, h), (w - n, h - n, w, h)]
    pixels = []
    for b in boxes:
        pixels.extend(_pixels(small.crop(b)))
    if not pixels:
        return (255, 255, 255)
    return (_median(p[0] for p in pixels), _median(p[1] for p in pixels), _median(p[2] for p in pixels))


def analyze(path, spec, white_tol=None):
    """返回 checks 列表与 metrics。Pillow 缺失时只给结构项。"""
    w, h, fmt = probe_size(path) or (0, 0, "UNKNOWN")
    size_bytes = os.path.getsize(path)
    checks, metrics = [], {"width": w, "height": h, "format": fmt, "bytes": size_bytes}

    def add(cid, status, detail, hint=""):
        checks.append({"id": cid, "status": status, "detail": detail, "hint": hint})

    if not w or not h:
        add("format", "fail", "无法识别宽高（Pillow 缺失时仅支持 PNG/JPEG）", "安装 Pillow：pip install pillow")
        return checks, metrics

    long_side = max(w, h)
    metrics["long_side"] = long_side

    # 比例
    if spec.get("ratio"):
        tw, th = spec["ratio"]
        actual = w / h
        target = tw / th
        err = abs(actual - target) / target
        metrics["ratio"] = round(actual, 4)
        if err <= spec["ratio_tol"]:
            add("ratio", "pass", f"{w}x{h} 比例 {actual:.3f} 符合 {tw}:{th}")
        elif err <= spec["ratio_tol"] * 2:
            add("ratio", "warn", f"比例 {actual:.3f} 接近 {tw}:{th}，偏差 {err*100:.1f}%", "建议按目标比例重出或补边")
        else:
            add("ratio", "fail", f"比例 {actual:.3f} 不符 {tw}:{th}", f"用 --fix 补齐到 {tw}:{th}")

    # 尺寸
    if long_side >= spec["long_side_min"]:
        add("size", "pass", f"长边 {long_side}px 满足 ≥{spec['long_side_min']}px")
    elif long_side >= spec["long_side_min"] * 0.8:
        add("size", "warn", f"长边 {long_side}px 低于建议值 {spec['long_side_min']}px", "放大后仍可能被压缩，建议重出更大尺寸")
    else:
        add("size", "fail", f"长边 {long_side}px 明显不足 {spec['long_side_min']}px", "用 --fix 放大或重出")

    # 文件大小
    if spec["max_bytes"] and size_bytes > spec["max_bytes"]:
        add("filesize", "fail", f"{size_bytes/1048576:.1f}MB 超过上限 {spec['max_bytes']/1048576:.0f}MB", "降质量或改 JPEG 重存")
    else:
        add("filesize", "pass", f"{size_bytes/1024:.0f}KB 在限额内")

    if not HAS_PIL:
        add("pixels", "skipped", "未安装 Pillow，背景/占比/文字项无法检查", "pip install pillow 后重跑；skipped 不等于通过")
        return checks, metrics

    with Image.open(path) as im:
        has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        metrics["alpha"] = has_alpha
        if has_alpha:
            add("alpha", "warn", "图片带透明通道", "主图应铺满且不透明，先合成到白底")
        else:
            add("alpha", "pass", "无透明通道")

        small = im.convert("RGB")
        small.thumbnail((SAMPLE_SIDE, SAMPLE_SIDE))
        sw, sh = small.size
        bg = corner_background(small)
        metrics["background_rgb"] = list(bg)

        # 边缘带白度
        band = max(1, int(min(sw, sh) * 0.02))
        border = []
        for box in [(0, 0, sw, band), (0, sh - band, sw, sh), (0, 0, band, sh), (sw - band, 0, sw, sh)]:
            border.extend(_pixels(small.crop(box)))
        tol = spec["white_tol"] if white_tol is None else white_tol
        white_hits = sum(1 for p in border if max(abs(p[0] - 255), abs(p[1] - 255), abs(p[2] - 255)) <= tol)
        white_ratio = white_hits / max(1, len(border))
        metrics["border_white_ratio"] = round(white_ratio, 4)

        # 前景掩码与 bbox（在缩略图上算，比例等比不变）
        pts = []
        for y in range(sh):
            row = y * sw
            for x in range(sw):
                p = small.getpixel((x, y))
                d2 = (p[0] - bg[0]) ** 2 + (p[1] - bg[1]) ** 2 + (p[2] - bg[2]) ** 2
                if d2 > STAT_RATIO_BG_TOL ** 2:
                    pts.append((x, y))
        if pts:
            xs = sorted(p[0] for p in pts)
            ys = sorted(p[1] for p in pts)
            cut = max(1, int(len(pts) * BBOX_TRIM))
            x0, x1 = xs[cut], xs[-cut]
            y0, y1 = ys[cut], ys[-cut]
            bw, bh = max(1, x1 - x0 + 1), max(1, y1 - y0 + 1)
            bbox_ratio = (bw * bh) / (sw * sh)
            long_ratio = max(bw / sw, bh / sh)
            metrics["bbox_ratio"] = round(bbox_ratio, 4)
            metrics["subject_long_ratio"] = round(long_ratio, 4)
            metrics["subject_pixel_ratio"] = round(len(pts) / (sw * sh), 4)
        else:
            bbox_ratio, long_ratio = 0.0, 0.0
            metrics["bbox_ratio"] = 0.0
            add("subject", "fail", "未检出主体，可能整图都是背景色", "确认出图是否失败")

        # 背景判定
        if spec["white_bg"]:
            if white_ratio >= spec["border_white_min"] and max(abs(c - 255) for c in bg) <= tol:
                add("background", "pass", f"边缘纯白占比 {white_ratio*100:.1f}%，背景 RGB{tuple(bg)}")
            elif white_ratio >= spec["border_white_min"] * 0.9:
                add("background", "warn", f"边缘接近纯白（{white_ratio*100:.1f}%），背景 RGB{tuple(bg)}",
                    "该平台要求 RGB(255,255,255)，用 --fix 归一到纯白")
            else:
                add("background", "fail", f"背景不是纯白：边缘纯白仅 {white_ratio*100:.1f}%，估计 RGB{tuple(bg)}",
                    "Amazon / 天猫 / 京东 / Temu 主图需 RGB(255,255,255)，用 --fix 或重出")
        else:
            if white_ratio >= spec["border_white_min"]:
                add("background", "pass", f"背景为浅色/白（边缘纯白 {white_ratio*100:.1f}%）")
            else:
                add("background", "warn", f"背景非白（边缘纯白 {white_ratio*100:.1f}%）",
                    "该平台允许场景背景，确认产品是否仍是第一视觉中心")

        # 占比：以主体最长边占画布比例为主判定，对应平台「产品 fill 85%」的口径；
        # 面积比同时报出，便于判断是空边过多还是主体偏窄。
        occ = long_ratio
        if occ >= spec["occupancy_min"]:
            add("occupancy", "pass", f"主体最长边占画布 {occ*100:.1f}%，面积比 {bbox_ratio*100:.1f}%")
        elif occ >= spec["occupancy_min"] - 0.05:
            add("occupancy", "warn", f"主体最长边占画布 {occ*100:.1f}%，略低于 {spec['occupancy_min']*100:.0f}%",
                "留白偏多，建议收紧构图后重出")
        else:
            add("occupancy", "fail", f"主体最长边仅占画布 {occ*100:.1f}%，低于 {spec['occupancy_min']*100:.0f}%",
                "产品太小会被判不合格；用 --fix-occupancy 扩主体或重出")

        # 图内文字（OCR 可选）
        ocr = {"status": "skipped", "reason": "pytesseract 未安装"}
        try:
            import pytesseract

            text = pytesseract.image_to_string(im, lang="chi_sim+eng").strip()
            visible = [line for line in text.splitlines() if line.strip() and len(line.strip()) > 1]
            ocr = {"status": "done", "lines": len(visible), "sample": visible[:3]}
            if visible and not spec["text_allowed"]:
                add("text", "fail", f"检出 {len(visible)} 行文字，该平台首图不允许文字：{visible[0][:30]}",
                    "去掉图内文字后重出，文字挪到辅图或详情页")
            elif visible:
                add("text", "warn", f"检出 {len(visible)} 行文字", "该平台允许文字，但须真实可证，禁绝对化用语")
            else:
                add("text", "pass", "未检出图内文字")
        except ImportError:
            add("text", "skipped", "OCR 不可用，图内文字未检查", "pip install pytesseract 并安装 tesseract；skipped 不等于通过")
        metrics["ocr"] = ocr

    return checks, metrics


def fix(path, spec, out_dir, fix_occupancy=False):
    """可修正项自动修正：白底归一、比例补齐、尺寸放大（可选主体扩占比）。

    只做几何与背景，不重绘内容；输出新文件，不覆盖原图。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as im:
        img = im.convert("RGB")
        w, h = img.size

        if spec["white_bg"]:
            small = img.copy()
            small.thumbnail((SAMPLE_SIDE, SAMPLE_SIDE))
            bg = corner_background(small)
            diff = ImageChops.difference(img, Image.new("RGB", img.size, tuple(bg)))
            r, g, b = diff.split()
            mask = ImageChops.lighter(ImageChops.lighter(r, g), b)
            mask = mask.point(lambda v: 255 if v <= spec["white_tol"] else 0)
            img.paste((255, 255, 255), mask=mask)

        if fix_occupancy:
            small = img.copy()
            small.thumbnail((SAMPLE_SIDE, SAMPLE_SIDE))
            bg2 = corner_background(small)
            pts = []
            for y in range(small.size[1]):
                for x in range(small.size[0]):
                    p = small.getpixel((x, y))
                    if (p[0]-bg2[0])**2 + (p[1]-bg2[1])**2 + (p[2]-bg2[2])**2 > STAT_RATIO_BG_TOL**2:
                        pts.append((x, y))
            if pts:
                k = w / small.size[0]
                xs = sorted(p[0] for p in pts)
                ys = sorted(p[1] for p in pts)
                cut = max(1, int(len(pts) * BBOX_TRIM))
                box = (int(xs[cut] * k), int(ys[cut] * k), int(xs[-cut] * k), int(ys[-cut] * k))
                box = (max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3]))
                if box[2] - box[0] > 8 and box[3] - box[1] > 8:
                    subject = img.crop(box)
                    side = int(max(subject.width, subject.height) / max(0.05, spec["occupancy_min"]) ** 0.5)
                    side = max(side, subject.width, subject.height)
                    canvas = Image.new("RGB", (side, side), (255, 255, 255))
                    canvas.paste(subject, ((side - subject.width) // 2, (side - subject.height) // 2))
                    img = canvas

        if spec.get("ratio"):
            tw, th = spec["ratio"]
            cur = img.width / img.height
            if abs(cur - tw / th) / (tw / th) > spec["ratio_tol"]:
                if cur > tw / th:
                    nw, nh = img.width, int(round(img.width * th / tw))
                else:
                    nw, nh = int(round(img.height * tw / th)), img.height
                canvas = Image.new("RGB", (nw, nh), (255, 255, 255))
                canvas.paste(img, ((nw - img.width) // 2, (nh - img.height) // 2))
                img = canvas

        if max(img.size) < spec["long_side_min"]:
            scale = spec["long_side_min"] / max(img.size)
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)

    target = out_dir / f"{Path(path).stem}-checked.png"
    img.save(target)
    return target


def selftest():
    """离线自检：合成图验证白底、占比、比例与修正链路，不联网、不读外部文件。"""
    import tempfile

    if not HAS_PIL:
        print("selftest: 未安装 Pillow，仅能验证结构检查与参数解析")
        return 0

    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1) 纯白底 + 居中色块（长边占 90%）→ amazon 应通过
        white = Image.new("RGB", (1600, 1600), (255, 255, 255))
        white.paste((40, 90, 160), (80, 80, 1520, 1520))
        p1 = tmp / "ok.png"
        white.save(p1)
        checks, metrics = analyze(str(p1), PLATFORMS["amazon"])
        if any(c["status"] == "fail" for c in checks):
            fails.append(f"纯白合规图被误判 fail: {[c for c in checks if c['status'] == 'fail']}")
        if metrics.get("bbox_ratio", 0) < 0.7:
            fails.append(f"占比计算异常: {metrics.get('bbox_ratio')}")

        # 2) 灰底图 → amazon 应判背景 fail，--fix 后应转 pass
        grey = Image.new("RGB", (1200, 1200), (208, 208, 208))
        grey.paste((30, 60, 120), (100, 100, 1100, 1100))
        p2 = tmp / "grey.png"
        grey.save(p2)
        checks, _ = analyze(str(p2), PLATFORMS["amazon"])
        if not any(c["id"] == "background" and c["status"] == "fail" for c in checks):
            fails.append("灰底图未被识别为背景 fail")
        fixed = fix(str(p2), PLATFORMS["amazon"], tmp / "fixed")
        checks2, _ = analyze(str(fixed), PLATFORMS["amazon"])
        if any(c["id"] == "background" and c["status"] == "fail" for c in checks2):
            fails.append(f"--fix 后背景仍 fail: {[c for c in checks2 if c['status'] == 'fail']}")

        # 3) 3:4 竖图 → tiktok-shop(1:1) 应判比例 fail
        tall = Image.new("RGB", (900, 1200), (255, 255, 255))
        tall.paste((10, 10, 10), (100, 100, 800, 1100))
        p3 = tmp / "tall.png"
        tall.save(p3)
        checks, _ = analyze(str(p3), PLATFORMS["tiktok-shop"])
        if not any(c["id"] == "ratio" and c["status"] == "fail" for c in checks):
            fails.append("3:4 图未在 1:1 平台被判比例 fail")

        # 4) PNG 尺寸解析与 Pillow 一致
        info = probe_size(str(p3))
        if not info or info[:2] != (900, 1200):
            fails.append(f"PNG 头解析异常: {info}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 4 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="出图后平台机检")
    ap.add_argument("images", nargs="*", help="待检图片路径，可多个")
    ap.add_argument("--platform", default="generic", help="平台名，见 PLATFORMS；默认 generic")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--strict", action="store_true", help="warn 也视为失败（CI 用）")
    ap.add_argument("--fix", nargs="?", const="out/checked", help="自动修正并输出到目录，默认 out/checked")
    ap.add_argument("--fix-occupancy", action="store_true", help="修正时按目标占比放大主体（会裁掉边缘留白）")
    ap.add_argument("--selftest", action="store_true", help="离线自检，不读外部图片")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.images:
        ap.print_help()
        return 0

    platform = ALIASES.get(args.platform, args.platform)
    if platform not in PLATFORMS:
        print(f"未知平台 {args.platform}，可选：{', '.join(sorted(PLATFORMS))}", file=sys.stderr)
        return 1
    spec = PLATFORMS[platform]

    results, has_fail, degraded = [], False, not HAS_PIL
    for path in args.images:
        if not Path(path).exists():
            results.append({"file": path, "verdict": "error", "detail": "文件不存在"})
            has_fail = True
            continue
        checks, metrics = analyze(path, spec)
        entry = {"file": path, "platform": platform, "checks": checks, "metrics": metrics}
        if args.fix:
            entry["fixed"] = str(fix(path, spec, args.fix, args.fix_occupancy))
        statuses = [c["status"] for c in checks]
        if "fail" in statuses or (args.strict and "warn" in statuses):
            entry["verdict"] = "fail"
            has_fail = True
        elif "warn" in statuses or "skipped" in statuses:
            entry["verdict"] = "warn"
        else:
            entry["verdict"] = "pass"
        results.append(entry)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        icon = {"pass": "OK  ", "warn": "WARN", "fail": "FAIL", "skipped": "SKIP"}
        for r in results:
            print(f"\n{r['file']}  ·  {r['platform']}  ·  {r['verdict']}")
            m = r.get("metrics", {})
            if m.get("width"):
                print(f"  {m['width']}x{m['height']}  {m.get('long_side')}px  {m['bytes']/1024:.0f}KB"
                      f"  主体 {m.get('bbox_ratio', 0)*100:.1f}%  边缘白 {m.get('border_white_ratio', 0)*100:.1f}%")
            for c in r["checks"]:
                print(f"  {icon.get(c['status'], '?')}  {c['detail']}")
                if c.get("hint") and c["status"] in ("fail", "warn", "skipped"):
                    print(f"        → {c['hint']}")
            if r.get("fixed"):
                print(f"  已修正输出：{r['fixed']}")

    if degraded:
        print("\n注意：未安装 Pillow，背景/占比/文字项全部 skipped，结论不完整。", file=sys.stderr)
        return 2
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
