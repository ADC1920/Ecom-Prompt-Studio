# 变更记录

本文件记录对外可见的形态变更。内部重构细节见 git log。

## 2.1.0 — 2026-11-12

装上就能用，不再是一半能力。

### 新增

- **ZCode 插件形态**：`.zcode-plugin/plugin.json` 声明三个技能、命令、hooks 与 MCP server，一次装齐。此前三个技能各自拷贝，脚本不随包走。
- **MCP server**（`tools/mcp_server.py`）：四个工具，`query_atom` 定位原子、`get_template` 取模板与规则、`validate_prompt` 跑判据校验、`check_output` 平台机检。零依赖，标准库实现 JSON-RPC。
- **出图后自动机检**（`hooks/check_after_image.py`）：`PostToolUse` 命中出图调用即跑平台机检，不过则把结果回注给模型。「机检不过不交付」从文档要求变成运行时强制。
- **斜杠命令**：`/ecom:main`、`/ecom:detail`、`/ecom:sku`、`/ecom:reverse` 四条，不用记五工位术语。
- **品牌锁规范**（`references/_brand-lock.md`）：十个必锁视觉字段与 prepend 写法，解跨图漂移。
- **AIGC 标注义务库**（`references/_rules/aigc-disclosure.json`）：FTC、加州 SB 942、纽约 SB 8420-A、EU AI Act Art.50、国内标识办法五地判据，含图类型四分类与四条红线。
- **视觉复核单生成器**（`tools/vlm_review.py`）：产出结构化复核清单，启发式分只提示，结论由人给。

### 修复

- `fix_stats.py` 的提示仍指向已删除的 `--generate` 闭环。改为说明 manifest 需由外部通道产出并给出字段格式。

### 变更

- 出图通道维持不内置（2026-11-10 移除），机检与视觉验收改为对任意通道产出做后置校验。

## 2.0.0 — 2026-10-13

- 产品锁定改为「参考图为主 + 保留/改动清单」，负面词改为输出边界句。
- 新增套图风格锁、证据账本四级、AI 合规节。
- 新增静态检查 `lint_skills.py` 与触发用例。

## 1.0.0 — 2026-10-04

首个公开版本：34 篇 SOP、五个工位、三个技能。
