# -*- coding: utf-8 -*-
"""把仓库打成自包含技能包：解压即用，SKILL.md 里的脚本命令全都还能跑。

为什么需要它：技能安装是「拷目录」，而 tools/ 在仓库根、不在技能目录内，
所以按 README 方式二装完，SKILL.md 里 15 处 tools/ 引用全部失效，只剩人工降级。
竞品（feichanggege/ecommerce-visual-copywriting-skill）用同一招解决：白名单打 zip。

本脚本出包时保持仓库结构——tools/ 与 skills/ 同级。这不是随便定的：
check_image.py 用「脚本父目录/../skills/ecom-prompt-sop/references/_rules/platform.json」
解析平台规则，两者同级路径才成立，所以工具链与技能必须一起走。

不打进包的内容：.cache/（可从原子 source_text 重建）、memory/、docs/、AGENTS.md、
tests、__pycache__、以及所有本机专属文件。白名单制，不在列表里的一律不进。

用法：
  python tools/package_skill.py                      # 输出 dist/Ecom-Prompt-Studio.zip
  python tools/package_skill.py --output out.zip
  python tools/package_skill.py --verify             # 出包后立即解压校验工具链可跑
  python tools/package_skill.py --selftest           # 离线自检，不出包

退出码：0 成功；1 失败。
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOP = "Ecom-Prompt-Studio"

# 打包白名单：只进这些路径。技能目录整树递归，其余按文件/目录精确匹配。
RUNTIME_GLOBS = [
    "skills/ecom-prompt-sop",
    "skills/ecom-main-image-prompts",
    "skills/ecom-detail-page-prompts",
    "tools",
    "evals/cases.json",
    "evals/check_cases.py",
    "evals/README.md",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
]

# 无论如何都不进包（白名单内也可能出现的噪音）
EXCLUDE_PARTS = {"__pycache__", ".cache", "memory", "docs", ".git", ".tmp", "dist", "out"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

# 打完之后必须存在的文件：少一个就说明白名单配错了
REQUIRED_IN_ZIP = [
    "skills/ecom-prompt-sop/SKILL.md",
    "skills/ecom-prompt-sop/references/_rules/platform.json",
    "skills/ecom-prompt-sop/references/_atoms/a01.json",
    "skills/ecom-main-image-prompts/SKILL.md",
    "skills/ecom-detail-page-prompts/SKILL.md",
    "tools/cli.py",
    "tools/check_image.py",
    "tools/slop_check.py",
    "tools/rules_engine.py",
]


def collect(root: Path) -> list:
    """按白名单收集文件，返回相对仓库根的 posix 路径列表。"""
    files = []
    for pattern in RUNTIME_GLOBS:
        target = root / pattern
        if not target.exists():
            raise ValueError(f"白名单路径不存在：{pattern}")
        if target.is_dir():
            candidates = sorted(target.rglob("*"))
        else:
            candidates = [target]
        for path in candidates:
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if EXCLUDE_PARTS & set(rel.parts):
                continue
            if path.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(rel.as_posix())
    return sorted(set(files))


def build(output: Path, root: Path = ROOT) -> dict:
    files = collect(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            archive.write(root / rel, f"{TOP}/{rel}")
    return {"output": str(output), "files": len(files),
            "bytes": output.stat().st_size}


def _run(script: Path, argv: list, timeout: int = 180) -> subprocess.CompletedProcess:
    """跑子脚本，强制子进程也走 UTF-8。

    Windows 下子进程默认用 GBK 输出，父进程按 UTF-8 解会抛 UnicodeDecodeError，
    而这异常发生在读线程里，主流程拿不到、只会在 stderr 打栈——于是「检查失败」
    变成「静默跳过」，最后还打印通过。用 -X utf8 从源头统一编码。
    """
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(script)] + argv,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def verify(output: Path) -> list:
    """解压到临时目录，实跑工具链。这是「装完能跑」的唯一硬证据。"""
    problems = []
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        with zipfile.ZipFile(output) as archive:
            archive.extractall(dest)
        base = dest / TOP

        for rel in REQUIRED_IN_ZIP:
            if not (base / rel).exists():
                problems.append(f"包内缺必需文件：{rel}")
        if problems:
            return problems

        # 1) 不带参数跑一次静态检查（技能目录与索引必须自洽）
        checks = [
            ("lint_skills.py", [str(base)]),
            ("atomize.py", ["check"]),
            ("cli.py", ["--selftest"]),
            ("check_image.py", ["--selftest"]),
            ("slop_check.py", ["--selftest"]),
            ("rules_engine.py", ["--selftest"]),
        ]
        for script, argv in checks:
            proc = _run(base / "tools" / script, argv)
            if proc.returncode != 0:
                tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-3:]
                problems.append(f"包内 {script} {' '.join(argv)} 退出码 {proc.returncode}：{' / '.join(tail)}")
            elif (proc.stderr or "").strip():
                # 退出码 0 但 stderr 有内容，说明检查链路有没跑通的环节
                problems.append(f"包内 {script} 退出码 0 但 stderr 非空（疑静默跳过）："
                                f"{(proc.stderr or '').strip()[:200]}")

        # 2) 关键路径解析：check_image 必须能从包内读到 platform.json，而不是退回内置表
        probe = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c",
             "import sys;sys.path.insert(0,r'%s');import check_image as c;"
             "print(len(c.PLATFORMS));print(c.PLATFORM_SOURCE)" % (base / "tools")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if probe.returncode != 0:
            problems.append(f"包内无法导入 check_image：{(probe.stderr or '').strip()[:200]}")
        else:
            lines = (probe.stdout or "").strip().splitlines()
            if len(lines) < 2:
                problems.append("包内 check_image 探测输出异常")
            elif lines[1].strip() == "builtin":
                problems.append("包内 check_image 退回了内置兜底表，未读到 platform.json（路径解析断了）")
            elif lines[0].strip() != "12":
                problems.append(f"包内平台数应为 12，实际 {lines[0].strip()}")

        # 3) 可再生缓存不得进包（靠 atomic 的 source_text 重建）
        if list(base.rglob("_mech")):
            problems.append("包内不应包含 _atoms/_mech（可再生缓存）")
    return problems


def selftest() -> int:
    """不落正式包，用临时 zip 验一遍打包 + 解压校验链路。"""
    fails = []
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "probe.zip"
        try:
            info = build(out)
        except (OSError, ValueError) as exc:
            print(f"FAIL 打包失败：{exc}")
            return 1
        if info["files"] < 60:
            fails.append(f"包内文件数异常偏少：{info['files']}")
        problems = verify(out)
        fails.extend(problems)

        # 负向：白名单路径写错时必须报错，不能静默出个空包
        with zipfile.ZipFile(out) as archive:
            names = archive.namelist()
        if any("memory/" in n or "docs/" in n or ".cache" in n for n in names):
            fails.append("包内混入了本机专属或可再生内容")

    if fails:
        for f in fails:
            print(f"FAIL {f}")
        return 1
    print("selftest: 打包、解压、包内工具链、路径解析、排他 全部通过")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="把仓库打成自包含技能包")
    ap.add_argument("--output", default=str(ROOT / "dist" / f"{TOP}.zip"))
    ap.add_argument("--verify", action="store_true", help="出包后解压实跑工具链校验")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    out = Path(args.output)
    try:
        info = build(out)
    except (OSError, ValueError) as exc:
        print(f"FAIL 打包失败：{exc}")
        return 1
    print(f"PASS 打包 {info['files']} 个文件（{info['bytes']:,} 字节）→ {info['output']}")

    if args.verify:
        problems = verify(out)
        if problems:
            for p in problems:
                print(f"FAIL {p}")
            return 1
        print("PASS 解压校验：包内工具链全部可跑，platform.json 路径解析正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
