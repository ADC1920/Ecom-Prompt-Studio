# -*- coding: utf-8 -*-
"""把仓库打成干净的插件包，供本地市场安装。

为什么需要它：ZCode 插件安装是整目录拷贝，不问 .gitignore。以仓库根直接作插件源时，
AGENTS.md、docs/、memory/、.v2c 这些本机专属文件会一起进安装缓存，含本机路径的
project-info.md 也会被带走。

做法：用 git ls-files 取已跟踪文件——本机专属内容本来就不在版本控制里，过滤天然成立，
不需要维护白名单，仓库演进时也不会失准。

输出结构（市场根与插件根分开，与真实分发一致）：

  dist/
    marketplace.json          source 指向 ./ecom-prompt-studio
    ecom-prompt-studio/       全部已跟踪的分发内容

用法：
  python tools/pack_plugin.py                # 打包到 dist/
  python tools/pack_plugin.py --out <目录>   # 指定输出目录
  python tools/pack_plugin.py --selftest
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLUGIN_NAME = "ecom-prompt-studio"
DEFAULT_OUT = ROOT / "dist"

# 仓库元数据，不是插件内容：CI 配置、git 自身的忽略与换行规则
REPO_ONLY = {".github", ".gitignore", ".gitattributes"}

# 打包后必须不存在的顶层项。命中就是过滤失效
FORBIDDEN = {"docs", "memory", "AGENTS.md", ".v2c", ".tmp", "out", "dist", "marketplace.json"}


def tracked_files():
    p = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
    )
    if p.returncode != 0:
        raise RuntimeError(f"git ls-files 失败：{(p.stderr or '').strip()}")
    return [f for f in p.stdout.split("\0") if f]


def top_of(rel):
    return rel.split("/")[0]


def pack(out_dir):
    out_dir = Path(out_dir).resolve()
    plugin_dir = out_dir / PLUGIN_NAME

    if out_dir.exists():
        shutil.rmtree(out_dir)
    plugin_dir.mkdir(parents=True)

    copied, skipped = 0, []
    for rel in tracked_files():
        if top_of(rel) in REPO_ONLY:
            skipped.append(rel)
            continue
        src = ROOT / rel
        dst = plugin_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    manifest = json.loads((plugin_dir / ".zcode-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = {
        "name": "dev-ecom-prompt-studio",
        "plugins": [{
            "name": manifest["name"],
            "source": f"./{PLUGIN_NAME}",
            "version": manifest["version"],
            "description": manifest["description"],
            "displayName": "Ecom Prompt Studio",
            "displayName_i18n": {"zh-CN": "电商提示词五工作室"},
            "description_i18n": {"zh-CN": "电商视觉五工作室提示词 SOP，含原子库、判据引擎、出图后机检与 MCP 工具"},
            "category": "productivity",
        }],
    }
    (out_dir / "marketplace.json").write_text(
        json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"out": str(out_dir), "plugin": str(plugin_dir),
            "copied": copied, "skipped": len(skipped), "version": manifest["version"]}


def verify(out_dir):
    """打包结果自校验：本机内容不得进包，关键资源必须齐。"""
    out_dir = Path(out_dir).resolve()
    plugin_dir = out_dir / PLUGIN_NAME
    fails = []

    if not plugin_dir.is_dir():
        return [f"插件目录不存在：{plugin_dir}"]

    tops = {p.name for p in plugin_dir.iterdir()}
    leaked = tops & FORBIDDEN
    if leaked:
        fails.append(f"本机专属内容进了包：{sorted(leaked)}")

    for need in (".zcode-plugin/plugin.json", "tools/mcp_server.py", "hooks/hooks.json",
                 "ecom-prompt-sop/SKILL.md", "commands", "README.md"):
        if not (plugin_dir / need).exists():
            fails.append(f"缺少必需内容：{need}")

    mc = out_dir / "marketplace.json"
    if not mc.exists():
        fails.append("缺少 marketplace.json")
    else:
        data = json.loads(mc.read_text(encoding="utf-8"))
        src = (data.get("plugins") or [{}])[0].get("source", "")
        if src != f"./{PLUGIN_NAME}":
            fails.append(f"市场 source 应为 ./{PLUGIN_NAME}，实际 {src!r}")

    # 本机路径检测：取当前用户主目录动态比对，不硬编码盘符与用户名。
    # 只检主目录而非盘符根，避免任何提到该盘符的文本被误判。
    home = str(Path.home())
    # 同时检反斜杠形式，仓库文本可能是 Windows 路径
    markers = {home, home.replace("\\", "/"), home.replace("/", "\\")}

    for p in plugin_dir.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".py", ".json", ".yaml", ".yml"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            if any(m and m in text for m in markers):
                fails.append(f"含本机路径：{p.relative_to(plugin_dir)}")

    return fails


def main():
    ap = argparse.ArgumentParser(description="打干净的插件包供本地市场安装")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出目录，默认 {DEFAULT_OUT}")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        got = pack(ROOT / ".tmp" / "pack-selftest")
        fails = verify(got["out"])
        shutil.rmtree(ROOT / ".tmp" / "pack-selftest", ignore_errors=True)
        if fails:
            for f in fails:
                print("FAIL", f)
            return 1
        print(f"selftest: 打包 {got['copied']} 文件、排除 {got['skipped']} 个仓库元数据，"
              f"本机内容零泄漏，关键资源齐全")
        return 0

    got = pack(args.out)
    fails = verify(got["out"])
    print(f"打包完成：{got['copied']} 个文件，跳过 {got['skipped']} 个仓库元数据")
    print(f"市场根：{got['out']}")
    print(f"插件根：{got['plugin']}")
    if fails:
        for f in fails:
            print(f"错误: {f}")
        return 1
    print("校验通过：无本机内容、关键资源齐全、市场清单正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
