# -*- coding: utf-8 -*-
"""品牌锁渲染：把 brand-lock JSON 编译成可逐字复用的提示词前缀。

为什么要有它：`_brand-lock.md` 讲了十个必锁字段和「逐字相同地出现在每张提示词里」，
但那是给人读的规范。真到出图时，agent 每次重新描述一遍「左上 45 度、5500K」，
措辞必然微调，模型每次解读也就跟着变——锁就失效了。

这个脚本把锁编译成一段固定文本，每条提示词开头原样贴上，措辞不再由模型现编。
校验规则见 `_brand-lock.schema.json`：色值必须是十六进制、色温必须是数值 K，
因为形容词无法锁住。

用法：
  python tools/brand_lock.py --template > brand.json      # 出空白锁
  python tools/brand_lock.py brand.json                    # 渲染成前缀段
  python tools/brand_lock.py brand.json --json             # 输出结构化结果
  python tools/brand_lock.py --selftest

退出码：0 正常；1 校验失败；2 输入错误。
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = (HERE.parent / "skills" / "ecom-prompt-sop" / "references" / "_brand-lock.schema.json")

# 十个必锁字段，顺序即渲染顺序。与 _brand-lock.md 的表格逐项对应。
FIELDS = [
    ("light_direction", "主光"),
    ("light_temp", "色温"),
    ("shadow_type", "投影"),
    ("bg_color", "背景色"),
    ("bg_material", "背景材质"),
    ("camera_height", "机位"),
    ("lens", "镜头"),
    ("color_grading", "调色"),
    ("typography", "字体"),
]

TEMPLATE = {k: "" for k, _ in FIELDS}
TEMPLATE["negative"] = []
TEMPLATE["name"] = ""
TEMPLATE["notes"] = ""


def validate(lock):
    """按 schema 的实质约束校验。不引第三方库，只查真正会导致锁失效的项。"""
    problems = []
    if not isinstance(lock, dict):
        return ["品牌锁必须是 JSON 对象"]

    for key, label in FIELDS:
        value = lock.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{label}（{key}）必填且必须是非空字符串")

    # 色值必须是十六进制：写「纯白」锁不住，写 #FFFFFF 才锁得住
    bg = lock.get("bg_color")
    if isinstance(bg, str) and bg.strip() and not re.match(r"^#[0-9A-Fa-f]{6}$", bg.strip()):
        problems.append(f"背景色必须是十六进制色值（如 #FFFFFF），实际 {bg!r}")

    # 色温必须带数值 K：写「暖白」锁不住
    temp = lock.get("light_temp")
    if isinstance(temp, str) and temp.strip() and not re.match(r"^\s*\d{4,5}\s*K", temp.strip()):
        problems.append(f"色温必须写成数值 K（如 5500K 冷白），实际 {temp!r}")

    # 禁止项必须是非空数组：空数组等于没锁边界
    neg = lock.get("negative")
    if not isinstance(neg, list) or not neg:
        problems.append("negative 必须是至少一项的数组（输出边界不能空）")
    elif any(not isinstance(x, str) or not x.strip() for x in neg):
        problems.append("negative 每一项都必须是非空字符串")

    allowed = set(TEMPLATE)
    unknown = set(lock) - allowed
    if unknown:
        problems.append(f"未知字段：{sorted(unknown)}（schema 不允许额外字段，避免拼错键被静默忽略）")
    return problems


def render(lock):
    """编译成固定前缀段。措辞一旦生成就逐字复用，不再由模型现编。"""
    parts = []
    for key, _ in FIELDS:
        parts.append(f"{lock[key].strip().rstrip('；;，,。')}")
    body = "；".join(parts)
    negs = "、".join(x.strip() for x in lock["negative"])
    text = f"【品牌锁】{body}；{negs}。"
    return {"prefix": text, "fields": {k: lock[k] for k, _ in FIELDS},
            "negative": lock["negative"], "name": lock.get("name") or ""}


def selftest():
    fails = []

    def good():
        return {
            "light_direction": "左上 45 度、略高于视线",
            "light_temp": "5500K 冷白",
            "shadow_type": "自然接触影",
            "bg_color": "#FFFFFF",
            "bg_material": "无缝纸",
            "camera_height": "平视",
            "lens": "50mm 标准",
            "color_grading": "中性无滤镜",
            "typography": "无衬线粗体，标题字高占画面 7%",
            "negative": ["不出现文字", "不出现水印"],
            "name": "主图白底套",
            "notes": "",
        }

    lock = good()
    if validate(lock):
        fails.append(f"合规锁不应报错，实际 {validate(lock)}")

    r = render(lock)
    prefix = r["prefix"]
    if "【品牌锁】" not in prefix:
        fails.append("渲染结果缺【品牌锁】标记")
    for probe in ("左上 45 度", "5500K 冷白", "#FFFFFF", "不出现文字"):
        if probe not in prefix:
            fails.append(f"渲染结果漏了「{probe}」")
    if prefix.count("；") < 9:
        fails.append(f"十个字段应以「；」分隔，实际分隔符 {prefix.count('；')} 个")
    if not prefix.endswith("。"):
        fails.append("渲染结果应以句号收尾")

    # 每个必锁字段缺失都必须被抓到
    for key, label in FIELDS:
        bad = good()
        bad[key] = ""
        if not validate(bad):
            fails.append(f"缺 {label} 未被校验拦下")

    # 形容词无法锁住：色值与非数值色温必须拒绝
    bad = good()
    bad["bg_color"] = "纯白"
    if not validate(bad):
        fails.append("非十六进制背景色未被拦下")
    bad = good()
    bad["light_temp"] = "暖白"
    if not validate(bad):
        fails.append("非数值色温未被拦下")

    # 空边界等于没锁
    bad = good()
    bad["negative"] = []
    if not validate(bad):
        fails.append("空 negative 未被拦下")

    # 拼错字段名必须报错，不能静默忽略
    bad = good()
    bad["bg_colour"] = "#FFFFFF"
    if not validate(bad):
        fails.append("未知字段未被拦下")

    # 同一份锁两次渲染必须完全一致（这是「锁」的最低要求）
    if render(good())["prefix"] != render(good())["prefix"]:
        fails.append("同一份锁两次渲染结果不一致")

    if fails:
        for f in fails:
            print(f"FAIL {f}")
        return 1
    print("selftest: 校验、渲染、字段缺失、形容词拒绝、未知字段、渲染稳定性 全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="品牌锁：校验并渲染成固定提示词前缀")
    ap.add_argument("lock", nargs="?", help="brand-lock JSON 路径")
    ap.add_argument("--template", action="store_true", help="输出空白锁模板")
    ap.add_argument("--json", action="store_true", help="输出结构化结果")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.template or not args.lock:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    path = Path(args.lock)
    if not path.exists():
        print(f"品牌锁文件不存在：{path}", file=sys.stderr)
        return 2
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    problems = validate(lock)
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1

    result = render(lock)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["prefix"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
