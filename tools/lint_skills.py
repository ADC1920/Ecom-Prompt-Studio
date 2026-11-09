# -*- coding: utf-8 -*-
"""技能库静态检查（零依赖，Python 标准库）。

检查项：
1. frontmatter：name/description 必填，name 与目录名一致，description 长度合规
2. 引用链接：SKILL.md 中引用的 references/ 路径必须存在
3. 路由覆盖：ecom-prompt-sop 的 SOP 文件与 SKILL.md 路由表双向一致
4. 规模预算：SKILL.md 正文超预算给出警告，超硬上限判错误
5. 占位符闭合：全库 Markdown 的【】、[]、{{}} 逐行配对，不闭合判错误
6. 密钥扫描：全库文本无常见密钥模式
7. 索引覆盖：references/_index.json 与 34 篇原文双向一致，工位名合法
8. 工具引用：SKILL.md 提到的 tools/ 脚本必须真实存在

用法: python tools/lint_skills.py [仓库根]（默认为脚本上级目录）
0 错误退出码 0，否则 1；警告不阻断。
"""
import json
import re
import sys
from pathlib import Path

SKILLS = ["ecom-prompt-sop", "ecom-main-image-prompts", "ecom-detail-page-prompts"]

SECRETS = [
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|password|access[_-]?token)['\"]?\s*[:=]\s*['\"][A-Za-z0-9/+_=-]{16,}['\"]"
    ),
]

REF_RE = re.compile(r"references/[^`|\]\n]+?\.md")

# 五工位名，与 SKILL.md 工位表一致；索引里的 stations 必须是这五个之一
STATIONS = {"主图台", "详情页台", "SKU台", "模特与视频台", "反推台"}

# 五槽位名，与 references/_prompt-slots.md 一致；索引里的 slots 必须是这五个之一
SLOTS = {"scene", "subject", "details", "usecase", "constraints"}

# SKILL.md 里点名的工具文件，用于校验脚本是否真实存在
TOOL_REF = re.compile(r"tools/([A-Za-z0-9_.\-]+\.(?:py|md|json))")

# SKILL.md 正文（不含 frontmatter）预算：超软线提醒，超硬线阻断。
# 硬线对齐 Agent Skills 生态惯例（SKILL.md 不超过 500 行），软线留出提前拆分的余量。
SKILL_LINE_WARN = 300
SKILL_LINE_MAX = 500
SKILL_CHAR_WARN = 12000
SKILL_CHAR_MAX = 20000


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def check_skill(root: Path, name: str, problems: list, warnings: list) -> None:
    skill_dir = root / name
    f = skill_dir / "SKILL.md"
    if not f.exists():
        problems.append(f"[{name}] SKILL.md 缺失")
        return
    text = read(f)

    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        problems.append(f"[{name}] frontmatter 缺失或格式错误")
    else:
        fm = m.group(1)
        fm_name = re.search(r"^name:\s*(\S+)", fm, re.M)
        desc_m = re.search(r"^description:\s*(.+)$", fm, re.M)
        desc = desc_m.group(1).strip().strip("\"'") if desc_m else ""
        if not fm_name:
            problems.append(f"[{name}] frontmatter 缺 name")
        elif fm_name.group(1) != name:
            problems.append(f"[{name}] frontmatter name={fm_name.group(1)} 与目录名不一致")
        if len(desc) < 20:
            problems.append(f"[{name}] description 缺失或过短（{len(desc)} 字符）")
        elif len(desc) > 1024:
            warnings.append(f"[{name}] description 长度 {len(desc)} 超 1024")

    for ref in sorted(set(REF_RE.findall(text))):
        if not (skill_dir / ref).exists():
            problems.append(f"[{name}] 引用不存在: {ref}")

    body = text[m.end():] if m else text
    lines = body.count("\n") + 1
    chars = len(body)
    if lines > SKILL_LINE_MAX or chars > SKILL_CHAR_MAX:
        problems.append(
            f"[{name}] SKILL.md 正文超硬上限：{lines} 行 / {chars} 字符"
            f"（上限 {SKILL_LINE_MAX} 行 / {SKILL_CHAR_MAX} 字符），必须拆到 references/"
        )
    elif lines > SKILL_LINE_WARN or chars > SKILL_CHAR_WARN:
        warnings.append(
            f"[{name}] SKILL.md 正文接近上限：{lines} 行 / {chars} 字符"
            f"（软线 {SKILL_LINE_WARN} 行 / {SKILL_CHAR_WARN} 字符），建议拆分"
        )


def check_atoms(root: Path, problems: list, warnings: list) -> None:
    """拆解原子：结构与索引一一对应。内容是否与原文同步由 `python tools/atomize.py check` 负责。"""
    skill_dir = root / "ecom-prompt-sop"
    idx_p = skill_dir / "references" / "_atoms" / "index.json"
    if not idx_p.exists():
        warnings.append("[ecom-prompt-sop] 缺少 _atoms/index.json（跑 python tools/atomize.py merge 生成）")
        return
    try:
        atoms = json.loads(read(idx_p))
        ref_items = json.loads(read(skill_dir / "references" / "_index.json"))["items"]
    except json.JSONDecodeError as e:
        problems.append(f"[atoms] 索引解析失败: {e}")
        return

    items = atoms.get("items") or []
    if len(items) != len(ref_items):
        problems.append(f"[atoms] 原子数 {len(items)} 与篇目索引 {len(ref_items)} 不一致")
    ref_paths = {it["path"] for it in ref_items}
    for it in items:
        aid = it.get("id") or "?"
        p = skill_dir / "references" / "_atoms" / f"{aid}.json"
        if not p.exists():
            problems.append(f"[atoms] 缺少原子文件 {aid}.json")
            continue
        try:
            atom = json.loads(read(p))
        except json.JSONDecodeError:
            problems.append(f"[atoms] {aid}.json 解析失败")
            continue
        if atom.get("path") not in ref_paths:
            problems.append(f"[atoms] {aid} 的 path 不在篇目索引里：{atom.get('path')}")
        if not atom.get("templates") and not atom.get("checklists"):
            problems.append(f"[atoms] {aid} 既无模板也无清单")
        if not atom.get("source", {}).get("sha"):
            problems.append(f"[atoms] {aid} 缺 source.sha，无法判断是否与原文同步")


def check_placeholders(root: Path, problems: list) -> None:
    """逐行检查占位符是否闭合。

    覆盖本库实际使用的三种占位形态：【中文占位】、[中文占位]、{{模板变量}}。
    先剥离行内代码与转义括号，避免把代码示例里的方括号算进来。
    """
    for p in sorted(root.rglob("*.md")):
        if ".git" in p.parts:
            continue
        for lineno, line in enumerate(read(p).splitlines(), 1):
            s = re.sub(r"`[^`]*`", "", line)
            s = s.replace("\\[", "").replace("\\]", "")
            where = f"{p.relative_to(root).as_posix()}:{lineno}"
            if s.count("【") != s.count("】"):
                problems.append(f"[placeholder] {where}: 【】不闭合")
            if s.count("{{") != s.count("}}"):
                problems.append(f"[placeholder] {where}: {{{{}}}}不闭合")
            depth = 0
            for ch in s:
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth = max(0, depth - 1)
            if depth:
                problems.append(f"[placeholder] {where}: []不闭合")


def sop_files(skill_dir: Path) -> set:
    """SOP 原文文件集合。

    `_` 开头的是索引、规范、规则与语料（_index.json / _prompt-slots.md / _rules/ / _corpus/），
    不算原文。判断看整条路径——目录名带下划线时，里面的 README 也不能当 SOP。
    """
    ref_root = skill_dir / "references"
    out = set()
    for p in ref_root.rglob("*.md"):
        parts = p.relative_to(ref_root).parts
        if any(part.startswith("_") for part in parts):
            continue
        out.add(p.relative_to(skill_dir).as_posix())
    return out


def check_route_coverage(root: Path, problems: list, warnings: list) -> None:
    skill_dir = root / "ecom-prompt-sop"
    if not (skill_dir / "SKILL.md").exists():
        return
    text = read(skill_dir / "SKILL.md")
    on_disk = sop_files(skill_dir)
    in_route = {p for p in set(REF_RE.findall(text)) if not Path(p).name.startswith("_")}
    for p in sorted(on_disk - in_route):
        warnings.append(f"[ecom-prompt-sop] SOP 未进路由表: {p}")
    for p in sorted(in_route - on_disk):
        problems.append(f"[ecom-prompt-sop] 路由表指向不存在的文件: {p}")


def check_secrets(root: Path, problems: list) -> None:
    for p in root.rglob("*.md"):
        if ".git" in p.parts:
            continue
        text = read(p)
        for pat in SECRETS:
            for hit in set(pat.findall(text)):
                if isinstance(hit, tuple):
                    hit = hit[-1]
                problems.append(f"[secrets] {p.relative_to(root).as_posix()}: 疑似密钥 {str(hit)[:12]}...")


def check_index(root: Path, problems: list, warnings: list) -> None:
    """索引与原文双向覆盖：漏收、指向不存在、重复、工位名拼错都算错误。

    索引是路由表的机器可读镜像，两边漂移会让检索与评测同时跑偏，所以卡在静态检查里。
    """
    skill_dir = root / "ecom-prompt-sop"
    if not (skill_dir / "SKILL.md").exists():
        return
    idx = skill_dir / "references" / "_index.json"
    if not idx.exists():
        warnings.append("[ecom-prompt-sop] 缺少机器可读索引 references/_index.json")
        return
    try:
        data = json.loads(read(idx))
    except json.JSONDecodeError as e:
        problems.append(f"[index] JSON 解析失败: {e}")
        return

    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        problems.append("[index] items 为空或不是数组")
        return

    disk = sop_files(skill_dir)
    paths = [it.get("path", "") for it in items if isinstance(it, dict)]

    for p in sorted(disk - set(paths)):
        problems.append(f"[index] 原文未收录: {p}")
    for p in sorted(set(paths) - disk):
        problems.append(f"[index] 指向不存在的文件: {p}")
    for p in sorted({p for p in paths if paths.count(p) > 1}):
        problems.append(f"[index] 重复条目: {p}")
    if len(items) != len(disk):
        problems.append(f"[index] 条目数 {len(items)} 与原文数 {len(disk)} 不一致")

    for it in items:
        if not isinstance(it, dict):
            continue
        for st in it.get("stations", []):
            if st not in STATIONS:
                problems.append(f"[index] 未知工位「{st}」: {it.get('path')}")
        for slot in it.get("slots", []):
            if slot not in SLOTS:
                problems.append(f"[index] 未知槽位「{slot}」: {it.get('path')}")
        if not it.get("triggers"):
            warnings.append(f"[index] 缺触发词: {it.get('path')}")


def check_tool_refs(root: Path, problems: list) -> None:
    """SKILL.md 里点名的 tools/ 文件必须存在，避免文档指向已删除的脚本。"""
    for name in SKILLS:
        f = root / name / "SKILL.md"
        if not f.exists():
            continue
        for ref in sorted(set(TOOL_REF.findall(read(f)))):
            if not (root / "tools" / ref).exists():
                problems.append(f"[{name}] 引用了不存在的工具: tools/{ref}")


def check_eval(root: Path, problems: list, warnings: list) -> None:
    """EVAL.md 是评测答案键：必须存在，且不得被 SKILL.md 引用（否则被评 agent 直接看到答案）。"""
    for name in SKILLS:
        skill_dir = root / name
        if not (skill_dir / "SKILL.md").exists():
            continue
        if not (skill_dir / "EVAL.md").exists():
            warnings.append(f"[{name}] 缺少 EVAL.md 答案键")
            continue
        if "EVAL.md" in read(skill_dir / "SKILL.md"):
            problems.append(f"[{name}] SKILL.md 引用了 EVAL.md：答案键不能出现在被评 agent 的入口里")


def check_rules(root: Path, problems: list, warnings: list) -> None:
    """判据规则与语料库：规则文件必须可解析且非空，语料每行必须是带 id/title/prompt 的合法 JSON。"""
    skill_dir = root / "ecom-prompt-sop"
    rdir = skill_dir / "references" / "_rules"
    if not rdir.exists():
        warnings.append("[ecom-prompt-sop] 缺少判据规则目录 _rules/")
    else:
        for name, key in [("platform", "platforms"), ("category", "categories"), ("scenario", "scenarios")]:
            p = rdir / f"{name}.json"
            if not p.exists():
                problems.append(f"[rules] 缺少 {name}.json")
                continue
            try:
                data = json.loads(read(p))
            except json.JSONDecodeError as e:
                problems.append(f"[rules] {name}.json 解析失败: {e}")
                continue
            if not (data.get(key) or {}):
                problems.append(f"[rules] {name}.json 的 {key} 为空")

    cpath = skill_dir / "references" / "_corpus" / "entries.jsonl"
    if not cpath.exists():
        warnings.append("[ecom-prompt-sop] 语料库为空（_corpus/entries.jsonl 不存在）")
        return
    for i, line in enumerate(read(cpath).splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"[corpus] 第 {i} 行不是合法 JSON")
            continue
        for field in ("id", "title", "prompt"):
            if not entry.get(field):
                problems.append(f"[corpus] 第 {i} 行缺字段 {field}")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    problems: list = []
    warnings: list = []
    for name in SKILLS:
        check_skill(root, name, problems, warnings)
    check_route_coverage(root, problems, warnings)
    check_index(root, problems, warnings)
    check_tool_refs(root, problems)
    check_eval(root, problems, warnings)
    check_rules(root, problems, warnings)
    check_atoms(root, problems, warnings)
    check_placeholders(root, problems)
    check_secrets(root, problems)
    for w in warnings:
        print(f"警告: {w}")
    for p in problems:
        print(f"错误: {p}")
    if problems:
        print(f"结果: 错误 {len(problems)}，警告 {len(warnings)}（不通过）")
        return 1
    print(f"结果: 错误 0，警告 {len(warnings)}（通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
