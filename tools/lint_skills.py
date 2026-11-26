# -*- coding: utf-8 -*-
"""技能库静态检查（零依赖，Python 标准库）。

检查项：
1. frontmatter：name/description 必填，name 与目录名一致，description 长度合规
2. 引用链接：SKILL.md 中引用的 references/ 路径必须存在
3. 路由覆盖：ecom-prompt-sop 的 SOP 文件与 SKILL.md 路由表双向一致
4. 规模预算：SKILL.md 正文超预算给出警告，超硬上限判错误
5. 占位符闭合：全库 Markdown 的【】、[]、{{}} 逐行配对，不闭合判错误
6. 密钥扫描：全库文本无常见密钥模式
7. 索引覆盖：references/_index.json 与原子按编号对齐，工位名合法
8. 工具引用：SKILL.md 提到的 tools/ 脚本必须真实存在
9. 平台单源：platform.json 与 check_image 的平台集合、机检字段必须一致
10. 构建产物：可再生的 _atoms/_mech 不得留在技能目录
11. 文档计数：文档里写死的脚本/用例/原子数必须等于实际值

用法: python tools/lint_skills.py [仓库根]（默认为脚本上级目录）
0 错误退出码 0，否则 1；警告不阻断。
"""
import json
import re
import sys
from pathlib import Path

SKILLS = ["ecom-prompt-sop", "ecom-main-image-prompts", "ecom-detail-page-prompts"]
SKILLS_ROOT = "skills"  # 三个技能都在仓库根的 skills/ 下

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
    skill_dir = root / SKILLS_ROOT / name
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
    """拆解原子：结构与索引一一对应。内容自洽性由 `python tools/atomize.py check` 负责。"""
    skill_dir = root / SKILLS_ROOT / "ecom-prompt-sop"
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
    ref_nos = {it.get("no") for it in ref_items}
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
        if atom.get("no") not in ref_nos:
            problems.append(f"[atoms] {aid} 的编号不在篇目索引里：{atom.get('no')}")
        if not atom.get("templates") and not atom.get("checklists"):
            problems.append(f"[atoms] {aid} 既无模板也无清单")
        if not atom.get("source", {}).get("sha"):
            problems.append(f"[atoms] {aid} 缺 source.sha，无法判断内容是否被改过")


ATOM_REF = re.compile(r"_atoms/(a\d{2})\.json")


def check_atom_refs(root: Path, problems: list, warnings: list) -> None:
    """SKILL.md 必须指向真实存在的原子，且每个原子都要被路由表覆盖到。

    这是「每个原子都能被找到」的唯一保证。
    """
    skill_dir = root / SKILLS_ROOT / "ecom-prompt-sop"
    f = skill_dir / "SKILL.md"
    if not f.exists():
        return
    text = read(f)
    atoms_dir = skill_dir / "references" / "_atoms"
    referenced = set(ATOM_REF.findall(text))
    existing = {p.stem for p in atoms_dir.glob("a*.json")} if atoms_dir.exists() else set()

    for aid in sorted(referenced - existing):
        problems.append(f"[atoms] SKILL.md 引用了不存在的原子 {aid}")
    for aid in sorted(existing - referenced):
        warnings.append(f"[atoms] 原子 {aid} 未被 SKILL.md 路由表引用")


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
    """索引与原子按编号对齐：漏收、重复、工位名拼错都算错误。

    索引是路由表的机器可读镜像，两边漂移会让检索与评测同时跑偏，所以卡在静态检查里。
    """
    skill_dir = root / SKILLS_ROOT / "ecom-prompt-sop"
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

    atom_by_no = {}
    for f in (skill_dir / "references" / "_atoms").glob("a*.json"):
        try:
            a = json.loads(read(f))
        except json.JSONDecodeError:
            problems.append(f"[atoms] {f.name} 解析失败")
            continue
        if not a.get("source_text"):
            problems.append(f"[atoms] {f.stem} 缺 source_text，原子不自包含")
        atom_by_no[a.get("no")] = a

    nos = [it.get("no") for it in items if isinstance(it, dict)]
    for no in sorted({n for n in nos if nos.count(n) > 1}):
        problems.append(f"[index] 编号重复: {no}")
    for no in sorted(set(nos) - set(atom_by_no)):
        problems.append(f"[index] 条目 {no} 没有对应原子")
    for no in sorted(set(atom_by_no) - set(nos)):
        problems.append(f"[atoms] 原子 {no} 未进索引")
    if len(items) != len(atom_by_no):
        problems.append(f"[index] 条目数 {len(items)} 与原子数 {len(atom_by_no)} 不一致")

    for it in items:
        if not isinstance(it, dict):
            continue
        label = it.get("no")
        for st in it.get("stations", []):
            if st not in STATIONS:
                problems.append(f"[index] 未知工位「{st}」: {label}")
        for slot in it.get("slots", []):
            if slot not in SLOTS:
                problems.append(f"[index] 未知槽位「{slot}」: {label}")
        if not it.get("triggers"):
            warnings.append(f"[index] 缺触发词: {label}")


def check_tool_refs(root: Path, problems: list) -> None:
    """SKILL.md 里点名的 tools/ 文件必须存在，避免文档指向已删除的脚本。"""
    for name in SKILLS:
        f = root / SKILLS_ROOT / name / "SKILL.md"
        if not f.exists():
            continue
        for ref in sorted(set(TOOL_REF.findall(read(f)))):
            if not (root / "tools" / ref).exists():
                problems.append(f"[{name}] 引用了不存在的工具: tools/{ref}")


def check_eval(root: Path, problems: list, warnings: list) -> None:
    """EVAL.md 是评测答案键：必须存在，且不得被 SKILL.md 引用（否则被评 agent 直接看到答案）。"""
    for name in SKILLS:
        skill_dir = root / SKILLS_ROOT / name
        if not (skill_dir / "SKILL.md").exists():
            continue
        if not (skill_dir / "EVAL.md").exists():
            warnings.append(f"[{name}] 缺少 EVAL.md 答案键")
            continue
        if "EVAL.md" in read(skill_dir / "SKILL.md"):
            problems.append(f"[{name}] SKILL.md 引用了 EVAL.md：答案键不能出现在被评 agent 的入口里")


def check_rules(root: Path, problems: list, warnings: list) -> None:
    """判据规则与语料库：规则文件必须可解析且非空，语料每行必须是带 id/title/prompt 的合法 JSON。"""
    skill_dir = root / SKILLS_ROOT / "ecom-prompt-sop"
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


def check_platform_single_source(root: Path, problems: list) -> None:
    """平台阈值只能有一个数据源：platform.json。

    check_image 从该文件读阈值，自己只留机检兜底默认值。若 Python 侧又长出
    一份完整平台表，两边迟早漂移，所以这里断言两边平台集合一致、机检字段齐全。
    """
    sys.path.insert(0, str(root / "tools"))
    try:
        import check_image
    except ImportError as exc:
        problems.append(f"[platform] 无法导入 check_image 校验单源: {exc}")
        return

    p = root / SKILLS_ROOT / "ecom-prompt-sop" / "references" / "_rules" / "platform.json"
    try:
        rules = json.loads(read(p))["platforms"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        problems.append(f"[platform] 读 platform.json 失败: {exc}")
        return

    mech_fields = ("ratio", "ratio_tol", "white_bg", "white_tol", "border_white_min",
                   "occupancy_min", "long_side_min", "max_bytes", "text_allowed")
    for name, spec in rules.items():
        # ratio 允许显式为 null（表示该平台不限比例），其余字段缺失即为配置漏洞
        missing = [f for f in mech_fields if f not in spec or (spec[f] is None and f != "ratio")]
        if missing:
            problems.append(f"[platform] {name} 缺机检字段: {', '.join(missing)}")

    only_json = set(rules) - set(check_image.PLATFORMS)
    only_py = set(check_image.PLATFORMS) - set(rules)
    if only_json:
        problems.append(f"[platform] platform.json 有而 check_image 未加载: {sorted(only_json)}")
    if only_py:
        problems.append(f"[platform] check_image 有而 platform.json 没有: {sorted(only_py)}")


def check_no_build_artifacts(root: Path, problems: list) -> None:
    """可再生的构建产物不得留在技能目录里随包分发。

    _atoms/_mech 曾是 merge 的中间产物：占 _atoms 目录约 47% 体积、无任何消费方、
    也无校验，但能从原子的 source_text 完整重建。它现在放仓库根 .cache/，不进技能版图。
    """
    stale = root / SKILLS_ROOT / "ecom-prompt-sop" / "references" / "_atoms" / "_mech"
    if stale.exists():
        problems.append("[atoms] references/_atoms/_mech 是可再生缓存，不应留在技能目录"
                        "（atomize.py 现在写仓库根 .cache/）")


def check_doc_counts(root: Path, problems: list) -> None:
    """文档里写死的计数必须等于实际文件数。

    历史上 README 写 34 条用例、project-info 与 AGENTS.md 写 30 条，三处并存无校验，
    改代码时没人跟，于是长期不一致。这里把能自动数出来的都验一遍。
    """
    cases = 0
    cases_file = root / "evals" / "cases.json"
    if cases_file.exists():
        try:
            cases = len(json.loads(read(cases_file)).get("cases") or [])
        except json.JSONDecodeError:
            problems.append("[docs] evals/cases.json 解析失败，无法核对用例数")
            return

    atoms_dir = root / SKILLS_ROOT / "ecom-prompt-sop" / "references" / "_atoms"
    atoms = len(list(atoms_dir.glob("a[0-9][0-9].json"))) if atoms_dir.exists() else 0

    expectations = [
        # 脚本数已改为「全部脚本」的不写数字表述，不再校验；
        # 保留仍写死数字的三项，能自动数出来就该自动验。
        (root / "docs" / "project-info.md", "用例", cases, r"cases\.json\s*(\d+)\s*条"),
        (root / "AGENTS.md", "用例", cases, r"(\d+)\s*条触发回归"),
        (root / "README.md", "用例", cases, r"(\d+)\s*条用例"),
        (root / "README.md", "原子", atoms, r"(\d+)\s*篇"),
    ]
    for path, label, actual, pattern in expectations:
        if not path.exists():
            continue
        for found in sorted(set(re.findall(pattern, read(path)))):
            if int(found) != actual:
                problems.append(f"[docs] {path.name} 写{label} {found}，实际 {actual}")


def check_interface(root: Path, problems: list) -> None:
    """interface.json 是给 agent 看的接口层：引用的路径必须真实存在，工位名必须合法。

    它的价值在于「不读全文就能判断该不该接」，所以一旦引用了不存在的文件，
    比缺这个文件更糟——agent 会照着它去找，然后找不到。
    """
    skill_dir = root / SKILLS_ROOT / "ecom-prompt-sop"
    path = skill_dir / "interface.json"
    if not path.exists():
        problems.append("[interface] 缺少 interface.json（agent 接口层）")
        return
    try:
        data = json.loads(read(path))
    except json.JSONDecodeError as exc:
        problems.append(f"[interface] interface.json 解析失败: {exc}")
        return

    for key in ("intent", "routing", "tools", "gates", "degradation", "references"):
        if not data.get(key):
            problems.append(f"[interface] 缺字段 {key}")

    intent = data.get("intent") or {}
    for key in ("job_to_be_done", "inputs", "outputs", "exclusions"):
        if not intent.get(key):
            problems.append(f"[interface] intent 缺 {key}")

    # 引用的参考文件必须存在（相对技能目录）
    refs = data.get("references") or {}
    for key, rel in refs.items():
        if "{" in str(rel):
            continue  # 花括号是并列写法，下面单独展开校验
        if not (skill_dir / rel).exists() and not (root / rel).exists():
            problems.append(f"[interface] references.{key} 指向不存在的路径: {rel}")
    rules = str(refs.get("rules") or "")
    for name in re.findall(r"\{([^}]+)\}", rules):
        base = rules.split("{")[0]
        for item in name.split(","):
            target = (skill_dir / f"{base}{item}.json")
            if not target.exists():
                problems.append(f"[interface] references.rules 指向不存在的文件: {base}{item}.json")

    # 工位名必须是五个之一，且与索引保持一致
    order = (data.get("routing") or {}).get("station_order") or []
    unknown = [s for s in order if s not in STATIONS]
    if unknown:
        problems.append(f"[interface] station_order 含非法工位: {unknown}")
    if len(order) != len(STATIONS):
        problems.append(f"[interface] station_order 应覆盖 {len(STATIONS)} 个工位，实际 {len(order)}")

    # 工具命令里点名的脚本必须存在
    for tool in data.get("tools") or []:
        cmd = str(tool.get("command") or "")
        for script in re.findall(r"tools/([A-Za-z0-9_]+\.py)", cmd):
            if not (root / "tools" / script).exists():
                problems.append(f"[interface] 工具命令引用了不存在的脚本: tools/{script}")


def check_shared_tool_refs(root: Path, problems: list) -> None:
    """两个技能各带一份 references/tools/，内容必须逐字节一致。

    技能是独立安装单元，同一批模型写法不能只放一处（另一个技能装完就缺），
    但又不能各改各的——复制两份必然漂移。折中：两边都带，用断言锁住相等。
    """
    main_dir = root / SKILLS_ROOT / "ecom-main-image-prompts" / "references" / "tools"
    detail_dir = root / SKILLS_ROOT / "ecom-detail-page-prompts" / "references" / "tools"
    if not main_dir.exists() and not detail_dir.exists():
        problems.append("[tools] 两个技能都缺 references/tools/（模型写法库）")
        return
    if not main_dir.exists() or not detail_dir.exists():
        problems.append("[tools] references/tools/ 只存在于一个技能，另一个装完会缺")
        return

    main_files = {p.name for p in main_dir.glob("*.md")}
    detail_files = {p.name for p in detail_dir.glob("*.md")}
    if main_files != detail_files:
        problems.append(f"[tools] 两处模型库文件不一致：仅主图 {sorted(main_files - detail_files)}，"
                        f"仅详情页 {sorted(detail_files - main_files)}")
    for name in sorted(main_files & detail_files):
        a = (main_dir / name).read_bytes()
        b = (detail_dir / name).read_bytes()
        if a != b:
            problems.append(f"[tools] {name} 两处内容不同（复制后漂移）")

    if "README.md" not in main_files:
        problems.append("[tools] 模型库缺 README.md 索引")


def main() -> int:
    # 本脚本的「自检」就是拿仓库根跑一遍完整检查。显式收下 --selftest，
    # 避免它被当成路径参数——否则会去 --selftest 这个不存在的目录里找技能。
    args = [a for a in sys.argv[1:] if a != "--selftest"]
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parent.parent
    problems: list = []
    warnings: list = []
    for name in SKILLS:
        check_skill(root, name, problems, warnings)
    check_index(root, problems, warnings)
    check_tool_refs(root, problems)
    check_eval(root, problems, warnings)
    check_rules(root, problems, warnings)
    check_atoms(root, problems, warnings)
    check_atom_refs(root, problems, warnings)
    check_placeholders(root, problems)
    check_secrets(root, problems)
    check_platform_single_source(root, problems)
    check_no_build_artifacts(root, problems)
    check_doc_counts(root, problems)
    check_interface(root, problems)
    check_shared_tool_refs(root, problems)
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
