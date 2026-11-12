# 变更记录

本文件记录对外可见的形态变更。内部重构细节见 git log。

## 2.1.0 — 2026-11-12

从「可读的 SOP 库」变成「装机即用的生产流程」。这一版跨了两批改动：原子化重构把散文拆成可执行零件，插件化把零件送到用户机器上。

### 架构变更

- **34 篇 SOP 拆成原子**：原文拆成模板、规则句、验收清单、占位符、步骤五类零件，每篇一个 `aNN.json`，`source_text` 保留全文。197 个模板、571 条规则句、181 条检查项、122 个占位符全部可按编号取出。此前路由指向 Markdown 文件，agent 得读整篇再自己分拣。
- **五工位结构**：主图、详情页、SKU 批量、模特与视频、反推。判工位有优先级，混合篇整篇共用、两处指向，不拆分复制。
- **ZCode 插件形态**：`.zcode-plugin/plugin.json` 声明三个技能、命令、hooks 与 MCP server，一次装齐。此前三个技能各自拷贝，而 `tools/` 在仓库根不随包走，装完 SKILL.md 里的脚本引用全部失效。

### 新增

- **MCP server**（`tools/mcp_server.py`）：四个工具，`query_atom` 定位原子、`get_template` 取模板与规则、`validate_prompt` 跑判据校验、`check_output` 平台机检。零依赖，标准库实现 JSON-RPC。把「读文档→判工位→读原子→挑模板」四步压成一次调用。
- **出图后自动机检**（`hooks/check_after_image.py`）：`PostToolUse` 命中出图调用即跑平台机检，不过则把结果回注给模型。「机检不过不交付」从文档要求变成运行时强制。
- **判据规则库**（`references/_rules/`）：平台 12 份、品类 9 份、场景 11 份 JSON，把白底阈值、占比、禁用宣称、必填槽位、画面禁项变成可校验规则。配套 `tools/rules_engine.py`。
- **正样本语料库**（`references/_corpus/`）：验证过并出过好图的提示词，按相似度检索、编译成 few-shot。配套 `tools/corpus.py`。
- **五槽位规范**（`references/_prompt-slots.md`）：保真段 → 场景 → 主体 → 细节 → 用途 → 约束。配套 `tools/compose_prompt.py`。
- **反 AI 感自查**（`tools/slop_check.py`）：查 SD 时代堆词、绝对化用语、虚假促销、功效宣称、AI 痕迹。
- **平台机检**（`tools/check_image.py`）：白底纯度、主体占比、比例、分辨率、文件大小、透明通道、图内文字。OCR 自己找 tesseract，缺依赖标 `skipped` 不假装通过。
- **视觉验收**（`tools/visual_audit.py`）：感知哈希加颜色直方图做一致性，图像统计做 AI 感嫌疑分。启发式，只提示不判定。
- **修复句统计**（`tools/fix_stats.py`）：从 manifest 算每条修复句的真实生效率。
- **斜杠命令**：`/ecom:main`、`/ecom:detail`、`/ecom:sku`、`/ecom:reverse` 四条，不用记五工位术语。
- **品牌锁规范**（`references/_brand-lock.md`）：十个必锁视觉字段与 prepend 写法，解跨图漂移。
- **AIGC 标注义务库**（`references/_rules/aigc-disclosure.json`）：FTC、加州 SB 942、纽约 SB 8420-A、EU AI Act Art.50、国内标识办法五地判据，含图类型四分类与四条红线。
- **视觉复核单生成器**（`tools/vlm_review.py`）：产出结构化复核清单，启发式分只提示，结论由人给。
- **插件清单自校验**（`tools/check_plugin.py`）：字段、资源存在性、路径越界、事件名合法性，接入 CI。
- **真实触发评测**（`evals/real_trigger.py`）：三层评测的第三层，把技能交给真实引擎看是否自行触发。只在里程碑手动跑。
- **触发用例扩到 30 条**：覆盖越界、注入与同类篇目分流，断言目标从 SOP 路径改为原子编号。
- **CI 升级**：GitHub Actions 到 v7，静态检查含十一个脚本自检，周度质量抽检。

### 修复

- `fix_stats.py` 的提示仍指向已删除的 `--generate` 闭环。改为说明 manifest 需由外部通道产出并给出字段格式。
- 原子化去掉 `source_path` 字段，索引改按编号对齐，避免原文移动后索引失效。

### 变更

- **移除命令行出图通道**：`tools/qwen_image.py`、`tools/run_loop.py` 与授权规则正本已于 2026-11-10 移除。机检与视觉验收改为对任意通道产出做后置校验，不再内置出图。
- README 改为拆解库形态，路由指向原子而非原文文件。
- 补 `.gitattributes`，文本统一 LF。

## 2.0.0 — 2026-10-13

- 产品锁定改为「参考图为主 + 保留/改动清单」，负面词改为输出边界句。
- 新增套图风格锁、证据账本四级、AI 合规节。
- 新增静态检查 `lint_skills.py` 与触发用例。

## 1.0.0 — 2026-10-04

首个公开版本：34 篇 SOP、五个工位、三个技能。
