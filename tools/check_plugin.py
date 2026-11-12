# -*- coding: utf-8 -*-
"""插件清单自校验：字段合法、声明的资源真实存在、路径不越界。

为什么需要它：插件是「一次装齐」的承载，清单写错一个路径，用户装完就是缺件，
但本地直接跑脚本时感觉不到——因为脚本是相对仓库根跑的。这个检查把装配问题
提前到 CI。

检查项：
1. `.zcode-plugin/plugin.json` 可解析，name 与目录名一致，version 是语义化版本
2. skills / commands / hooks / mcpServers 声明的路径全部存在
3. 所有声明路径都在插件根内，不含 ../ 越界
4. 每个 skill 目录有 SKILL.md，frontmatter 含 name 与 description
5. hooks.json 的事件名在 ZCode 支持的七个之内
6. .mcp.json 的 server 配置含 command

用法：
  python tools/check_plugin.py
  python tools/check_plugin.py --selftest
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = ROOT / ".zcode-plugin" / "plugin.json"

VALID_EVENTS = {
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
    "PostToolUse", "PostToolUseFailure", "Stop",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _load(path, problems):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        problems.append(f"{path.name} 无法解析：{e}")
        return None


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _in_root(p):
    try:
        Path(p).resolve().relative_to(ROOT)
        return True
    except (ValueError, OSError):
        return False


def check_manifest(problems):
    if not MANIFEST.exists():
        problems.append("缺少 .zcode-plugin/plugin.json")
        return None
    m = _load(MANIFEST, problems)
    if m is None:
        return None

    if m.get("name") != "ecom-prompt-studio":
        problems.append(f"清单 name 应为 ecom-prompt-studio，实际 {m.get('name')!r}")
    if not SEMVER.match(str(m.get("version", ""))):
        problems.append(f"version 不是语义化版本：{m.get('version')!r}")
    if not m.get("description"):
        problems.append("清单缺 description")

    for key in ("skills", "commands", "hooks"):
        for rel in _as_list(m.get(key)):
            target = (ROOT / rel).resolve() if not str(rel).startswith("/") else Path(rel)
            if not _in_root(target):
                problems.append(f"{key} 路径越出插件根：{rel}")
            elif not target.exists():
                problems.append(f"{key} 指向的路径不存在：{rel}")

    mcps = m.get("mcpServers")
    if isinstance(mcps, str):
        target = (ROOT / mcps).resolve()
        if not target.exists():
            problems.append(f"mcpServers 指向的文件不存在：{mcps}")
    return m


def check_skills(manifest, problems):
    for rel in _as_list((manifest or {}).get("skills")):
        skill_dir = ROOT / rel
        md = skill_dir / "SKILL.md"
        if not md.exists():
            problems.append(f"{rel} 缺 SKILL.md")
            continue
        head = md.read_text(encoding="utf-8")[:800]
        if not re.search(r"^name:\s*\S", head, re.M):
            problems.append(f"{rel}/SKILL.md 缺 name 字段")
        if not re.search(r"^description:\s*\S", head, re.M):
            problems.append(f"{rel}/SKILL.md 缺 description 字段")


def check_hooks(manifest, problems):
    for rel in _as_list((manifest or {}).get("hooks")):
        p = ROOT / rel
        if not p.exists():
            continue
        data = _load(p, problems)
        if not data:
            continue
        events = data.get("hooks") or data
        if not isinstance(events, dict):
            problems.append(f"{rel} 的 hooks 结构不是对象")
            continue
        for name in events:
            if name not in VALID_EVENTS:
                problems.append(f"{rel} 含不支持的事件名：{name}（只支持七个）")


def check_mcp(manifest, problems):
    mcps = (manifest or {}).get("mcpServers")
    if isinstance(mcps, dict):
        for name, cfg in mcps.items():
            if not isinstance(cfg, dict) or not cfg.get("command"):
                problems.append(f"mcpServers.{name} 缺 command")
        return
    if isinstance(mcps, str):
        p = ROOT / mcps
        if not p.exists():
            return
        data = _load(p, problems)
        for name, cfg in ((data or {}).get("mcpServers") or {}).items():
            if not isinstance(cfg, dict) or not cfg.get("command"):
                problems.append(f"mcpServers.{name} 缺 command")


def run_checks():
    problems = []
    manifest = check_manifest(problems)
    check_skills(manifest, problems)
    check_hooks(manifest, problems)
    check_mcp(manifest, problems)
    return problems


def selftest():
    """自检不打桩：直接对真实仓库跑，并确认能造出可识别的错误。"""
    fails = []
    problems = run_checks()
    if problems:
        fails.append(f"真实仓库清单应无问题，实际：{problems}")

    # 负向：事件名写错必须被抓到
    tmp = ROOT / ".tmp" / "plugin-check-probe.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"hooks": {"PostToolUseTypo": []}}), encoding="utf-8")
    fake = []
    check_hooks({"hooks": [".tmp/plugin-check-probe.json"]}, fake)
    if not fake:
        fails.append("非法事件名未被识别")
    tmp.unlink(missing_ok=True)

    fake2 = []
    check_skills({"skills": ["./no-such-skill"]}, fake2)
    if not fake2:
        fails.append("不存在的技能目录未被识别")

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("selftest: 真实清单通过、非法事件名拦截、缺失技能目录拦截")
    return 0


def main():
    ap = argparse.ArgumentParser(description="插件清单自校验")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    problems = run_checks()
    for p in problems:
        print(f"错误: {p}")
    if problems:
        print(f"结果: {len(problems)} 个问题（不通过）")
        return 1
    print("结果: 插件清单与声明的资源全部有效（通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
