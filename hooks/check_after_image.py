# -*- coding: utf-8 -*-
"""PostToolUse hook：出图后自动跑平台机检，不过就把结果回注给模型。

为什么需要它：SKILL.md 写着「机检不过不交付」，但那只是文档要求，靠模型自觉。
接上 hook 之后这条变成运行时强制——只要工具调用产出了图片，机检就一定会跑。

触发方式：hooks.json 的 PostToolUse 匹配 Bash|Write|Edit（出图通常经由这三者之一
落盘）。hook 从 stdin 读 JSON，自己判断本次调用是否产生了新图片；没有则安静退出 0。

输出契约（ZCode hooks.json schema）：只在需要回注时输出
  {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
其余情况不输出，靠退出码 0 表示放行。任何异常一律 exit 0，绝不因为机检自身故障
阻断用户的正常流程。
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
TOOLS_DIR = REPO_ROOT / "tools"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
# 只有这些目录下的新图才值得自动机检，避免对仓库源码里的杂图报警
WATCH_DIRS = ("out",)


def _find_platform(text):
    """只在显式平台参数里认平台，不从文件名或路径推断。

    早先的写法把整段命令当 haystack，结果路径里的 product-amazon.png 会被误判成
    指定了 amazon 平台。平台是用户的意图，必须来自 --platform/--platform= 这类
    显式写法。
    """
    import re
    if not text:
        return None
    m = re.search(r"--platform[=\s]+([A-Za-z0-9_-]+)", text)
    if m:
        return m.group(1).lower()
    return None


def _candidate_images(payload):
    """从 hook 输入里找出本次调用落盘的图片路径。"""
    tool_input = payload.get("tool_input") or {}
    found = []

    for key in ("file_path", "path", "notebook_path"):
        v = tool_input.get(key)
        if isinstance(v, str) and Path(v).suffix.lower() in IMG_EXT:
            found.append(v)

    cmd = tool_input.get("command") or ""
    if isinstance(cmd, str):
        for tok in cmd.replace('"', " ").replace("'", " ").split():
            if Path(tok).suffix.lower() in IMG_EXT:
                found.append(tok)

    return found


def _in_watch_dir(path):
    p = Path(path)
    try:
        rel = p.resolve().relative_to(REPO_ROOT)
    except (ValueError, OSError):
        return False
    return bool(rel.parts) and rel.parts[0] in WATCH_DIRS


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    images = [p for p in _candidate_images(payload) if _in_watch_dir(p)]
    images = [p for p in images if Path(p).exists()]
    if not images:
        return 0

    cmd_text = json.dumps(payload.get("tool_input") or {}, ensure_ascii=False)
    platform = _find_platform(cmd_text)
    if not platform:
        return 0

    sys.path.insert(0, str(TOOLS_DIR))
    lines = []
    for img in images[:5]:
        res = _run_check(img, platform)
        if res is None:
            continue
        verdict = res.get("verdict")
        if verdict in ("fail", "warn", "error"):
            detail = _summarize(res, verdict)
            lines.append(detail)

    if not lines:
        return 0

    ctx = ("出图后平台机检结果如下。按 SKILL.md 的交付门禁，机检不通过的图不得交付或上架；"
           "请修正提示词后重出，或说明为何该问题不影响本平台规则。\n" + "\n".join(lines))
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ctx}
    }, ensure_ascii=False))
    sys.stdout.flush()
    return 0


def _run_check(img, platform):
    """走 CLI 而不是内部函数：CLI 的 --json 输出与退出码是稳定契约。"""
    import subprocess
    try:
        p = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "check_image.py"), img, "--platform", platform, "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=90,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    raw = (p.stdout or "").strip()
    if not raw:
        return None
    try:
        arr = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(arr, list) or not arr:
        return None
    return arr[0]


def _summarize(res, verdict):
    img = res.get("file", "?")
    platform = res.get("platform", "?")
    if verdict == "error":
        return f"{img}：机检无法执行（{res.get('detail', '未知原因')}），请人工核对"
    bad = [c for c in (res.get("checks") or []) if c.get("status") in ("fail", "warn", "skipped")]
    parts = []
    for c in bad[:4]:
        item = f"{c.get('id', '')} {c.get('detail', '')}".strip()
        if c.get("hint"):
            item += f"（{c['hint']}）"
        parts.append(item)
    label = "不通过" if verdict == "fail" else "有警告"
    return f"{img}：{platform} 机检{label} —— " + "；".join(parts)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
