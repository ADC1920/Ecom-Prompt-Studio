# -*- coding: utf-8 -*-
"""正样本语料库：把「已经出过好图」的提示词存下来，下次按相似度检索当范例。

为什么需要它：SOP 原文给的是方法，但方法教不会手感——真正让提示词变好的是「见过好的」。
把验证过的提示词连同平台、品类、场景、机检结果、人工评分一起存下来，下次同类任务先检索 top-k
作为 few-shot 范例，比让模型从零想更稳。

语料存在 ecom-prompt-sop/references/_corpus/entries.jsonl，一行一条。

用法：
  python tools/corpus.py add --title "保温杯 Amazon 白底首图" --prompt-file p.txt \\
      --platform amazon --category 百货杯壶 --scenario 首图 --score 8 --tags 白底,主图
  python tools/corpus.py search --query "保温杯 白底主图" -n 3
  python tools/corpus.py fewshot --query "保温杯 白底主图" -n 2
  python tools/corpus.py list
  python tools/corpus.py --selftest

退出码：0 正常；1 无结果或自检失败；2 输入错误。
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS_DIR = HERE.parent / "ecom-prompt-sop" / "references" / "_corpus"
ENTRIES = CORPUS_DIR / "entries.jsonl"


def tokenize(text):
    """中文按 2-gram，英文数字按词。零依赖，够做相似度排序。"""
    text = str(text or "").lower()
    tokens = set()
    buf = ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "-_"):
            buf += ch
        else:
            if len(buf) >= 2:
                tokens.add(buf)
            buf = ""
            if "\u4e00" <= ch <= "\u9fff":
                tokens.add(ch)
    if len(buf) >= 2:
        tokens.add(buf)

    cn = "".join(ch if "\u4e00" <= ch <= "\u9fff" else " " for ch in text)
    for seg in cn.split():
        for i in range(len(seg) - 1):
            tokens.add(seg[i:i + 2])
    return tokens


def load():
    if not ENTRIES.exists():
        return []
    out = []
    for line in ENTRIES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def save(entries):
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    # newline="\n" 固定 LF：Windows 文本模式默认会把 \n 转成 \r\n，语料文件要跨平台一致
    with ENTRIES.open("w", encoding="utf-8", newline="\n") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def score_entry(entry, q_tokens, query, platform=None, category=None):
    """标题权重高于正文；平台与品类精确命中加分。"""
    s = 0.0
    s += 3.0 * len(q_tokens & tokenize(entry.get("title", "")))
    s += 2.0 * len(q_tokens & tokenize(" ".join(entry.get("tags", []))))
    s += 1.0 * len(q_tokens & tokenize(entry.get("prompt", "")))
    if platform and entry.get("platform") == platform:
        s += 4.0
    if category and entry.get("category") == category:
        s += 4.0
    if query and query in str(entry.get("title", "")):
        s += 6.0
    if entry.get("score"):
        s += float(entry["score"]) * 0.2   # 同分时评分高的靠前
    return s


def search(entries, query, n=3, platform=None, category=None):
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    ranked = []
    for e in entries:
        s = score_entry(e, q_tokens, query, platform, category)
        if s > 0:
            ranked.append((s, e))
    ranked.sort(key=lambda x: -x[0])
    return ranked[:n]


def to_fewshot(hits):
    """把命中样本编译成可直接嵌入提示词的范例段。"""
    lines = ["下面是同类任务的已验证范例，只学结构与颗粒度，不要照抄产品与卖点："]
    for idx, (sc, e) in enumerate(hits, 1):
        lines.append(f"\n【范例 {idx}】{e.get('title', '')}")
        meta = []
        if e.get("platform"):
            meta.append(f"平台 {e['platform']}")
        if e.get("category"):
            meta.append(f"品类 {e['category']}")
        if e.get("scenario"):
            meta.append(f"场景 {e['scenario']}")
        if e.get("score"):
            meta.append(f"人工评分 {e['score']}/10")
        if meta:
            lines.append("（" + " · ".join(meta) + "）")
        lines.append(e.get("prompt", "").strip())
    return "\n".join(lines)


def selftest():
    import tempfile

    fails = []
    entries = [
        {"id": "t1", "title": "保温杯 Amazon 白底首图", "platform": "amazon", "category": "百货杯壶",
         "scenario": "首图", "prompt": "纯白背景，哑光不锈钢保温杯正面，占画面 85%。", "score": 8, "tags": ["白底", "主图"]},
        {"id": "t2", "title": "口红详情页单屏", "platform": "taobao", "category": "美妆日化",
         "scenario": "详情页单屏", "prompt": "暖调背景，口红膏体特写，右侧参数卡。", "score": 7, "tags": ["详情页"]},
        {"id": "t3", "title": "背包场景图", "platform": "shopify", "category": "包包",
         "scenario": "场景图", "prompt": "街头场景，双肩包斜挎，自然光。", "score": 6, "tags": ["场景"]},
    ]

    hits = search(entries, "保温杯 白底", 2)
    if not hits or hits[0][1]["id"] != "t1":
        fails.append(f"检索排序错误：{[h[1]['id'] for h in hits]}")

    hits2 = search(entries, "口红", 2)
    if not hits2 or hits2[0][1]["id"] != "t2":
        fails.append(f"口红检索错误：{[h[1]['id'] for h in hits2]}")

    fs = to_fewshot(hits)
    if "范例 1" not in fs or "保温杯" not in fs:
        fails.append("few-shot 编译失败")

    # 平台加权
    hits3 = search(entries, "主图", 3, platform="amazon")
    if not hits3 or hits3[0][1]["id"] != "t1":
        fails.append("平台加权未生效")

    # tokenize 基本行为
    if not ({"保温", "温杯"} <= tokenize("保温杯")):
        fails.append(f"分词异常：{tokenize('保温杯')}")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 5 组用例全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="正样本语料库")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="录入一条样本")
    a.add_argument("--title", required=True)
    a.add_argument("--prompt-file", required=True)
    a.add_argument("--platform")
    a.add_argument("--category")
    a.add_argument("--scenario")
    a.add_argument("--score", type=float)
    a.add_argument("--tags", default="")
    a.add_argument("--image")
    a.add_argument("--id")

    s = sub.add_parser("search", help="按相似度检索")
    s.add_argument("--query", required=True)
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--platform")
    s.add_argument("--category")
    s.add_argument("--json", action="store_true")

    f = sub.add_parser("fewshot", help="编译成 few-shot 范例段")
    f.add_argument("--query", required=True)
    f.add_argument("-n", type=int, default=2)
    f.add_argument("--platform")
    f.add_argument("--category")

    sub.add_parser("list", help="列出全部条目")

    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.cmd == "add":
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig").strip()
        except OSError as e:
            print(f"提示词文件读取失败：{e}", file=sys.stderr)
            return 2
        if not prompt:
            print("提示词为空", file=sys.stderr)
            return 2
        entries = load()
        eid = args.id or f"c{len(entries) + 1:03d}"
        if any(e.get("id") == eid for e in entries):
            print(f"id 已存在：{eid}", file=sys.stderr)
            return 2
        entries.append({
            "id": eid,
            "title": args.title,
            "platform": args.platform,
            "category": args.category,
            "scenario": args.scenario,
            "score": args.score,
            "tags": [t for t in args.tags.split(",") if t.strip()],
            "image": args.image,
            "prompt": prompt,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        save(entries)
        print(f"已录入 {eid}，共 {len(entries)} 条")
        return 0

    entries = load()

    if args.cmd == "list":
        if not entries:
            print("语料库为空")
            return 0
        for e in entries:
            print(f"{e.get('id'):8} {e.get('title', '')[:40]:42} {e.get('platform') or '-':12} {e.get('score') or '-'}")
        return 0

    if args.cmd in ("search", "fewshot"):
        hits = search(entries, args.query, args.n, args.platform, args.category)
        if not hits:
            print("没有匹配样本；先 add 几条已验证的提示词", file=sys.stderr)
            return 1
        if args.cmd == "fewshot":
            print(to_fewshot(hits))
            return 0
        if args.json:
            print(json.dumps([{"score": round(s, 2), "entry": e} for s, e in hits], ensure_ascii=False, indent=2))
        else:
            for s, e in hits:
                print(f"[{s:.1f}] {e.get('id')} {e.get('title')}")
                print(f"      {e.get('platform') or '-'} · {e.get('category') or '-'} · 评分 {e.get('score') or '-'}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
