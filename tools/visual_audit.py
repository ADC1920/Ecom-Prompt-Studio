# -*- coding: utf-8 -*-
"""视觉验收：产品一致性与 AI 感启发式检查。

机检（check_image）管的是几何与合规硬约束（白底、占比、比例、文字），本脚本管两件机检管不了的事：

1. **一致性**：出图与参考图是不是同一个产品——用感知哈希加颜色直方图给相似度。
2. **AI 感**：图有没有过度光滑、过饱和、死白高光等典型痕迹——用图像统计特征给嫌疑分。

两样都是**启发式**，不是模型判断：分数只用于「提示复核」，不能作为通过或不通过的最终依据。
真正的视觉质量仍要人看，或用视觉模型（本项目未接）。

用法：
  python tools/visual_audit.py out/main-01.png --ref product_front.jpg
  python tools/visual_audit.py out/*.png --ref product.jpg --json
  python tools/visual_audit.py --selftest

退出码：0 无高风险；1 一致度过低或 AI 感过重；2 缺 Pillow。
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

try:
    from PIL import Image, ImageFilter

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def _pixels(im):
    """取像素列表；Pillow 12 起 getdata 标记弃用，统一在这里抑制告警。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return list(im.getdata())


SAMPLE = 256          # 统计用缩略长边
AHASH_SIDE = 8        # 感知哈希 8x8
CONSISTENCY_FAIL = 60  # 一致度低于此值判高风险
AI_SMELL_FAIL = 70     # AI 感嫌疑分高于此值判高风险


def ahash(img):
    g = img.convert("L").resize((AHASH_SIDE, AHASH_SIDE), Image.LANCZOS)
    px = _pixels(g)
    avg = sum(px) / len(px)
    bits = 0
    for i, v in enumerate(px):
        if v >= avg:
            bits |= 1 << i
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def color_sim(a, b):
    """RGB 各 16 桶直方图，余弦相似度。用于兜住感知哈希对配色的不敏感。"""
    def hist(img):
        small = img.convert("RGB").resize((64, 64))
        ha, hb, hc = [], [], []
        for r, g, bl in _pixels(small):
            ha.append(r // 16)
            hb.append(g // 16)
            hc.append(bl // 16)
        out = [0] * 48
        for v in ha:
            out[v] += 1
        for v in hb:
            out[16 + v] += 1
        for v in hc:
            out[32 + v] += 1
        return out

    x, y = hist(a), hist(b)
    dot = sum(i * j for i, j in zip(x, y))
    nx = sum(i * i for i in x) ** 0.5
    ny = sum(j * j for j in y) ** 0.5
    return dot / (nx * ny) if nx and ny else 0.0


def subject_crop(img, side=256):
    """裁出产品主体再比对。整图比会被背景差异带偏——换背景不该算「换了产品」。"""
    small = img.convert("RGB")
    small.thumbnail((side, side))
    w, h = small.size
    n = max(2, min(w, h) // 12)
    px = []
    for b in [(0, 0, n, n), (w - n, 0, w, n), (0, h - n, n, h), (w - n, h - n, w, h)]:
        px.extend(_pixels(small.crop(b)))
    if not px:
        return img
    bg = tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))

    pts = []
    for y in range(h):
        for x in range(w):
            p = small.getpixel((x, y))
            if sum((p[i] - bg[i]) ** 2 for i in range(3)) > 24 ** 2:
                pts.append((x, y))
    if not pts:
        return img

    k = img.width / w
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    box = (int(min(xs) * k), int(min(ys) * k), int((max(xs) + 1) * k), int((max(ys) + 1) * k))
    box = (max(0, box[0]), max(0, box[1]), min(img.width, box[2]), min(img.height, box[3]))
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return img
    return img.crop(box)


def consistency(ref, out):
    """返回 0-100 的一致度与分项。比对的是主体区域，不是整图。"""
    ref_c, out_c = subject_crop(ref), subject_crop(out)
    h_ref, h_out = ahash(ref_c), ahash(out_c)
    dist = hamming(h_ref, h_out)
    hash_sim = 1 - dist / 64
    cs = color_sim(ref_c, out_c)
    score = round((hash_sim * 0.55 + cs * 0.45) * 100, 1)
    return score, {"ahash_distance": dist, "hash_sim": round(hash_sim, 3), "color_sim": round(cs, 3)}


def ai_smell(img):
    """启发式嫌疑分 0-100：过饱和、过度平滑、死白高光、边缘密度四路加权。

    分数越高越像「AI 出的图」。阈值没有学术依据，是按常见 AI 图特征挑的工程经验值。
    """
    small = img.convert("RGB")
    small.thumbnail((SAMPLE, SAMPLE))
    w, h = small.size
    px = _pixels(small)
    total = max(1, len(px))

    # 饱和度
    sat_sum, high_sat, dead_white = 0.0, 0, 0
    for r, g, b in px:
        mx, mn = max(r, g, b), min(r, g, b)
        s = 0 if mx == 0 else (mx - mn) / mx
        sat_sum += s
        if s > 0.75:
            high_sat += 1
        if mn > 248:
            dead_white += 1
    mean_sat = sat_sum / total
    high_sat_ratio = high_sat / total
    dead_white_ratio = dead_white / total

    # 边缘密度（Pillow C 实现，比逐像素 Sobel 快）
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES)
    ev = _pixels(edges)
    edge_ratio = sum(1 for v in ev if v > 40) / max(1, len(ev))

    # 平滑度：梯度均值越低越平滑
    grad = sum(ev) / max(1, len(ev))

    score = 0.0
    score += min(1.0, max(0.0, (mean_sat - 0.35) / 0.35)) * 25      # 饱和 0.35 以下不扣
    score += min(1.0, high_sat_ratio / 0.25) * 20
    score += min(1.0, max(0.0, (6.0 - grad) / 6.0)) * 25             # 梯度低于 6 视为过平滑
    score += min(1.0, dead_white_ratio / 0.20) * 15
    score += min(1.0, max(0.0, (0.06 - edge_ratio) / 0.06)) * 15     # 边缘过少也是塑料感信号

    return round(min(100.0, score), 1), {
        "mean_saturation": round(mean_sat, 3),
        "high_saturation_ratio": round(high_sat_ratio, 3),
        "dead_white_ratio": round(dead_white_ratio, 3),
        "edge_ratio": round(edge_ratio, 3),
        "gradient_mean": round(grad, 2),
    }


def audit(out_path, ref_path=None):
    """返回一条验收结果。"""
    with Image.open(out_path) as im:
        out = im.convert("RGB")
        a_score, a_metrics = ai_smell(out)
        result = {
            "output": str(out_path),
            "ai_smell": {"score": a_score, "metrics": a_metrics},
        }
        if a_score >= AI_SMELL_FAIL:
            result["ai_smell"]["verdict"] = "high"
            result["ai_smell"]["hint"] = "AI 感偏重：降低饱和度、加真实材质纹理、避免死白高光与过度平滑"
        elif a_score >= 45:
            result["ai_smell"]["verdict"] = "medium"
            result["ai_smell"]["hint"] = "有一定 AI 感，建议补材质细节与阴影层次"
        else:
            result["ai_smell"]["verdict"] = "low"

        if ref_path:
            with Image.open(ref_path) as rim:
                c_score, c_metrics = consistency(rim.convert("RGB"), out)
            result["consistency"] = {"score": c_score, "metrics": c_metrics, "reference": str(ref_path)}
            if c_score < CONSISTENCY_FAIL:
                result["consistency"]["verdict"] = "low"
                result["consistency"]["hint"] = "与参考图差异大：确认是不是同一个产品，或换更强的参考图锁定"
            else:
                result["consistency"]["verdict"] = "ok"
    return result


def selftest():
    import tempfile
    import random

    if not HAS_PIL:
        print("selftest: 未安装 Pillow，跳过")
        return 0

    fails = []
    random.seed(7)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 平滑渐变：AI 感应偏高
        smooth = Image.new("RGB", (512, 512))
        sp = smooth.load()
        for y in range(512):
            for x in range(512):
                v = int(180 + 60 * (x / 512))
                sp[x, y] = (v, v - 20, 255 - v // 3)
        p_smooth = tmp / "smooth.png"
        smooth.save(p_smooth)

        # 噪声纹理：AI 感应偏低
        noisy = Image.new("RGB", (512, 512))
        np_ = noisy.load()
        for y in range(512):
            for x in range(512):
                base = 120 + int(40 * (x / 512))
                np_[x, y] = (max(0, min(255, base + random.randint(-45, 45))),
                             max(0, min(255, base - 10 + random.randint(-45, 45))),
                             max(0, min(255, base - 20 + random.randint(-45, 45))))
        p_noisy = tmp / "noisy.png"
        noisy.save(p_noisy)

        s_score, _ = ai_smell(smooth)
        n_score, _ = ai_smell(noisy)
        if not s_score > n_score:
            fails.append(f"平滑图 AI 感应高于噪声图，实际 {s_score} vs {n_score}")

        # 自身比对一致度 100
        r = audit(p_smooth, p_smooth)
        if r["consistency"]["score"] < 99:
            fails.append(f"自比对一致度应接近 100，实际 {r['consistency']['score']}")

        # 两图一致度应明显低
        r2 = audit(p_smooth, p_noisy)
        if r2["consistency"]["score"] > 90:
            fails.append(f"不同图一致度应偏低，实际 {r2['consistency']['score']}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 4 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="视觉验收：一致性与 AI 感启发式检查")
    ap.add_argument("images", nargs="*", help="待验收图片，可多个")
    ap.add_argument("--ref", help="参考图（产品图），给了才做一致性")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not args.images:
        ap.print_help()
        return 0
    if not HAS_PIL:
        print("未安装 Pillow，无法做视觉验收：pip install pillow", file=sys.stderr)
        return 2

    results, bad = [], False
    for p in args.images:
        if not Path(p).exists():
            results.append({"output": p, "error": "文件不存在"})
            bad = True
            continue
        try:
            r = audit(p, args.ref)
        except Exception as e:  # 坏图不该中断整批
            results.append({"output": p, "error": str(e)[:200]})
            bad = True
            continue
        results.append(r)
        if r["ai_smell"]["verdict"] == "high" or r.get("consistency", {}).get("verdict") == "low":
            bad = True

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"\n{r['output']}")
            if r.get("error"):
                print(f"  错误：{r['error']}")
                continue
            a = r["ai_smell"]
            print(f"  AI 感嫌疑 {a['score']}/100 · {a['verdict']}")
            m = a["metrics"]
            print(f"    饱和 {m['mean_saturation']}  高饱和占比 {m['high_saturation_ratio']}  "
                  f"死白 {m['dead_white_ratio']}  边缘 {m['edge_ratio']}  梯度 {m['gradient_mean']}")
            if a.get("hint"):
                print(f"    → {a['hint']}")
            c = r.get("consistency")
            if c:
                print(f"  与参考图一致度 {c['score']}/100 · {c['verdict']}")
                print(f"    感知哈希距离 {c['metrics']['ahash_distance']}/64  颜色相似 {c['metrics']['color_sim']}")
                if c.get("hint"):
                    print(f"    → {c['hint']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
