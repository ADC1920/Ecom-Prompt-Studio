# -*- coding: utf-8 -*-
"""技能库静态检查（零依赖，Python 标准库）。

检查项：
1. frontmatter：name/description 必填，name 与目录名一致，description 长度合规
2. 引用链接：SKILL.md 中引用的 references/ 路径必须存在
3. 路由覆盖：ecom-prompt-sop 的 SOP 文件与 SKILL.md 路由表双向一致
4. 规模预算：SKILL.md 超过 500 行给出警告
5. 密钥扫描：全库文本无常见密钥模式

用法: python tools/lint_skills.py [仓库根]（默认为脚本上级目录）
0 错误退出码 0，否则 1；警告不阻断。
"""
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

    n = text.count("\n") + 1
    if n > 500:
        warnings.append(f"[{name}] SKILL.md {n} 行超 500，建议拆到 references/")


def check_route_coverage(root: Path, problems: list, warnings: list) -> None:
    skill_dir = root / "ecom-prompt-sop"
    if not (skill_dir / "SKILL.md").exists():
        return
    text = read(skill_dir / "SKILL.md")
    on_disk = {p.relative_to(skill_dir).as_posix() for p in (skill_dir / "references").rglob("*.md")}
    in_route = set(REF_RE.findall(text))
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


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    problems: list = []
    warnings: list = []
    for name in SKILLS:
        check_skill(root, name, problems, warnings)
    check_route_coverage(root, problems, warnings)
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
