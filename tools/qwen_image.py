#!/usr/bin/env python3
"""Qwen-Image 2.1 Pro 出图通道（阿里云百炼 DashScope 同步接口）。

密钥只从环境变量 DASHSCOPE_API_KEY 或 --key-file 读取，不落盘、不打印。

授权闸门：本项目要求每次出图前取得用户授权（见 tools/IMAGE-GEN-AUTHORIZATION.md）。
--authorize / --purpose / --unit-price 三项缺一不可，否则不发出请求。

用法：
    python tools/qwen_image.py -p "提示词" -o out \
        --authorize "用户 2026-10-29 14:20 回复：可以" --purpose "产品A 天猫主图第2张" --unit-price 0.25
    python tools/qwen_image.py -f prompt.txt -i front.jpg -i detail.jpg --size 1024*1024 \
        --authorize "..." --purpose "..." --unit-price 0.25
    python tools/qwen_image.py --selftest
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
DEFAULT_MODEL = "qwen-image-2.1-pro"
MAX_IMAGES = 10


def read_key(key_file):
    if key_file:
        key = Path(key_file).read_text(encoding="utf-8-sig").strip()
    else:
        key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        sys.exit("缺少 API key：设置环境变量 DASHSCOPE_API_KEY，或用 --key-file 指定文件")
    return key


def normalize_size(size):
    """接受 1024*1024 / 1024x1024 / auto，输出 DashScope 要求的 宽*高。"""
    if size is None or size == "auto":
        return "auto"
    m = re.fullmatch(r"(\d+)[*x×](\d+)", size.strip())
    if not m:
        sys.exit(f"size 格式错误：{size}（应为 auto 或 宽*高，如 1024*1024）")
    w, h = int(m.group(1)), int(m.group(2))
    if not (512 <= w <= 2048 and 512 <= h <= 2048):
        sys.exit(f"size 超范围：{w}x{h}（边长 512 到 2048）")
    if max(w, h) / min(w, h) > 8:
        sys.exit(f"size 宽高比超范围：{w}:{h}（上限 8:1）")
    return f"{w}*{h}"


def encode_image(path):
    p = Path(path)
    if not p.is_file():
        sys.exit(f"参考图不存在：{path}")
    if p.stat().st_size > 10 * 1024 * 1024:
        sys.exit(f"参考图超过 10MB：{path}")
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    if not mime.startswith("image/"):
        sys.exit(f"不支持的图片格式：{path}")
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def build_payload(prompt, images, size, n, seed, prompt_extend, watermark, model):
    content = [{"text": prompt}] + [{"image": img} for img in images]
    params = {"size": normalize_size(size), "n": n, "prompt_extend": prompt_extend, "watermark": watermark}
    if seed is not None:
        params["seed"] = seed
    return {"model": model, "input": {"messages": [{"role": "user", "content": content}]}, "parameters": params}


def parse_images(resp):
    """从 DashScope 响应里取出图片 URL；字段缺失时回退到递归找 image 键。"""
    urls = []
    for choice in resp.get("output", {}).get("choices", []):
        for item in choice.get("message", {}).get("content", []):
            if isinstance(item, dict) and item.get("image"):
                urls.append(item["image"])
    if not urls:
        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "image" and isinstance(v, str):
                        urls.append(v)
                    else:
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(resp.get("output", {}))
    return urls


def check_authorization(authorize, purpose, unit_price, num, model, size, out_dir):
    """出图前的授权闸门：三项齐全才放行，并打印与落盘预计花费。"""
    missing = [
        name
        for name, value in (
            ("--authorize", authorize),
            ("--purpose", purpose),
            ("--unit-price", unit_price),
        )
        if value is None or (isinstance(value, str) and not value.strip())
    ]
    if missing:
        sys.exit(
            "缺少授权参数："
            + "、".join(missing)
            + "\n本项目要求每次出图前取得用户授权，先向用户说明用途与预计花费。"
            "\n规则见 tools/IMAGE-GEN-AUTHORIZATION.md"
        )
    if unit_price < 0:
        sys.exit(f"--unit-price 不能为负：{unit_price}")

    total = round(unit_price * num, 4)
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "size": size,
        "num": num,
        "unit_price": unit_price,
        "estimated_cost": total,
        "purpose": purpose.strip(),
        "authorize": authorize.strip(),
    }
    print(
        f"[授权确认] 模型={model} 张数={num} 单价={unit_price}元 预计花费={total}元\n"
        f"           用途={record['purpose']}\n"
        f"           授权={record['authorize']}",
        file=sys.stderr,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "authorization.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def request(payload, key, timeout):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code}：{body[:800]}")
    except urllib.error.URLError as e:
        sys.exit(f"请求失败：{e.reason}")


def download(url, out_dir, index):
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(url.split("?")[0]).suffix.lower() or ".png"
    path = out_dir / f"qwen_{time.strftime('%Y%m%d_%H%M%S')}_{index}{ext}"
    with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def selftest():
    import tempfile

    assert normalize_size("1024*1024") == "1024*1024"
    assert normalize_size("1024x1536") == "1024*1536"
    assert normalize_size("auto") == "auto"
    for bad in ("511*1024", "4096*4096", "1024", "1024*2048*3"):
        try:
            normalize_size(bad)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad}")
    p = build_payload("测试", ["data:image/png;base64,AA"], "1024*1024", 1, 7, False, False, DEFAULT_MODEL)
    assert p["parameters"] == {"size": "1024*1024", "n": 1, "prompt_extend": False, "watermark": False, "seed": 7}
    assert p["input"]["messages"][0]["content"][0] == {"text": "测试"}
    assert p["input"]["messages"][0]["content"][1] == {"image": "data:image/png;base64,AA"}
    # 默认必须关闭改写：长 SOP 原文投喂时不能被模型重写
    defaults = {action.dest: action.default for action in build_parser()._actions}
    assert defaults["prompt_extend"] is False, "prompt_extend 默认应为 False"
    assert defaults["authorize"] is None and defaults["purpose"] is None and defaults["unit_price"] is None
    fake = {"output": {"choices": [{"message": {"content": [{"image": "https://a/1.png"}]}}]}}
    assert parse_images(fake) == ["https://a/1.png"]
    assert parse_images({"output": {"results": [{"url": "x", "image": "https://a/2.png"}]}}) == ["https://a/2.png"]

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        # 授权三项缺任一都必须拦住，且不写日志
        for kwargs in (
            {"authorize": None, "purpose": "用途", "unit_price": 0.2},
            {"authorize": "用户同意", "purpose": None, "unit_price": 0.2},
            {"authorize": "用户同意", "purpose": "用途", "unit_price": None},
            {"authorize": "  ", "purpose": "用途", "unit_price": 0.2},
        ):
            try:
                check_authorization(kwargs["authorize"], kwargs["purpose"], kwargs["unit_price"], 1, DEFAULT_MODEL, "1024*1024", out)
            except SystemExit:
                pass
            else:
                raise AssertionError(f"应拒绝未授权参数：{kwargs}")
        assert not (out / "authorization.log").exists(), "未授权时不应写审计日志"
        # 三项齐全时放行，花费按 张数 × 单价 计算并落盘
        rec = check_authorization("用户 2026-10-29 同意", "产品A 天猫主图", 0.25, 4, DEFAULT_MODEL, "1024*1536", out)
        assert rec["estimated_cost"] == 1.0, rec
        logged = (out / "authorization.log").read_text(encoding="utf-8").splitlines()
        assert len(logged) == 1
        assert json.loads(logged[0])["purpose"] == "产品A 天猫主图"
    print("selftest ok")


def build_parser():
    ap = argparse.ArgumentParser(description="Qwen-Image 2.1 Pro 出图")
    ap.add_argument("-p", "--prompt", help="提示词文本")
    ap.add_argument("-f", "--prompt-file", help="从文件读取提示词")
    ap.add_argument("-i", "--image", action="append", default=[], help="参考图路径，可重复，最多 10 张")
    ap.add_argument("--size", default="1024*1024", help="auto 或 宽*高，默认 1024*1024")
    ap.add_argument("-n", "--num", type=int, default=1, help="出图数量 1 到 6，默认 1")
    ap.add_argument("--seed", type=int, help="随机种子，固定后结果相对稳定")
    ap.add_argument("--prompt-extend", action="store_true", help="开启提示词智能改写，默认关闭（SOP 原文直接投喂时保原样）")
    ap.add_argument("--watermark", action="store_true", help="添加水印，默认不加")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名，默认 {DEFAULT_MODEL}")
    ap.add_argument("--key-file", help="API key 文件路径；不传则读 DASHSCOPE_API_KEY")
    ap.add_argument("--authorize", help="用户授权凭证（用户原话或带日期说明），必填；见 tools/IMAGE-GEN-AUTHORIZATION.md")
    ap.add_argument("--purpose", help="这批图的用途与落点（产品/平台/页面位置），必填")
    ap.add_argument("--unit-price", type=float, help="每张单价（元，取官方页面当时数值），必填")
    ap.add_argument("-o", "--out", default="out", help="输出目录，默认 out")
    ap.add_argument("--timeout", type=int, default=300, help="请求超时秒数，默认 300")
    ap.add_argument("--selftest", action="store_true", help="离线自检，不调用 API")
    return ap


def main():
    args = build_parser().parse_args()

    if args.selftest:
        selftest()
        return

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig").strip()
    if not prompt:
        sys.exit("缺少提示词：用 -p 或 -f 提供")
    if len(args.image) > MAX_IMAGES:
        sys.exit(f"参考图最多 {MAX_IMAGES} 张，当前 {len(args.image)} 张")
    if not 1 <= args.num <= 6:
        sys.exit("--num 取值范围 1 到 6")

    # 授权闸门在读取密钥和发请求之前，未授权不会产生任何 API 调用
    check_authorization(
        args.authorize,
        args.purpose,
        args.unit_price,
        args.num,
        args.model,
        normalize_size(args.size),
        Path(args.out),
    )

    key = read_key(args.key_file)
    payload = build_payload(
        prompt,
        [encode_image(p) for p in args.image],
        args.size,
        args.num,
        args.seed,
        args.prompt_extend,
        args.watermark,
        args.model,
    )

    started = time.time()
    resp = request(payload, key, args.timeout)
    urls = parse_images(resp)
    if not urls:
        sys.exit(f"响应中未找到图片：{json.dumps(resp, ensure_ascii=False)[:800]}")

    for idx, url in enumerate(urls, 1):
        print(download(url, Path(args.out), idx))
    print(f"request_id={resp.get('request_id', '-')} 耗时={time.time() - started:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
