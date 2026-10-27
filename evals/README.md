# 评测目录说明

这里放触发回归与文本质量抽检的配置。人类可读的用例说明仍在 `tools/trigger-cases.md`，机器读取的源是 `cases.json`。

## 为什么不直接用真实 Agent 跑

真实技能触发要装进 Claude Code / Codex / ZCode 再发消息，依赖各引擎 CLI、登录态和图形界面，不适合每次 PR 都跑。这里改用「模型只看描述与路由表、只输出路由结论」的方式近似触发判断：

- 输入就是三个 `SKILL.md` 的 description 与 `ecom-prompt-sop` 路由表全文，没有别的上下文。
- 模型只输出 `{"skill": ..., "doc": ..., "reason": ...}`，断言比对技能名与 SOP 路径。
- 路由表或 description 改动会实时反映到评测输入，不需要维护副本。

这层能稳定抓住「选错技能」「选错品类专项」「裸主图/裸详情页没转交」这类回归，但不检验模型最终生成的提示词质量，那部分由 `promptfooconfig.quality.yaml` 抽检。

## 文件

| 文件 | 作用 |
|---|---|
| `cases.json` | 23 条用例的唯一数据源 |
| `router.js` | 从仓库读取三个 SKILL.md，拼装路由提示词 |
| `assert_route.js` | 解析模型输出，比对技能与 SOP；兼容 JSON 与纯文本两种返回 |
| `gen_tests.js` | 把 cases.json 展开为 promptfoo 测试 |
| `promptfooconfig.yaml` | 触发回归配置 |
| `quality-cases.json` | 3 条文本质量抽检用例，含 SOP 路径与评分规则 |
| `quality-prompt.js` / `quality-tests.js` / `promptfooconfig.quality.yaml` | 质量抽检的提示词、测试与配置 |
| `check_cases.py` | 一致性校验，CI 每次运行 |

## 新增用例

1. 在 `cases.json` 加一条，`id` 递增，写清 `input` 与 `expect`。
2. 在 `tools/trigger-cases.md` 对应分组加同编号同文本的一行。
3. 跑 `python evals/check_cases.py`，它会同时检查两边是否一致、预期 SOP 路径是否存在。

`expect.doc_contains` 用路径片段即可，例如 `03_品类专项/百货杯壶类`；比较语义是包含，重命名文件名后缀不会误报，但选错分类目录一定会失败。

## 关于 skill-up

`alibaba/skill-up`（约 1.2k star，Go，Apache-2.0）做的是同一件事的另一种形态：声明式 `eval.yaml`，真实启动 Claude Code / Codex / Qoder / Qwen Code 引擎跑技能，支持 `rule_based`、`script`、`agent_judge` 三种判分，导出 `grading.json`、`benchmark.json`、JUnit XML，官方提供 GitHub Action。

结论是本仓库**暂不接入**，原因是：

- 官方 Action 是 Docker 容器动作，只能跑 Linux runner，本机日常验证要另装 Go 工具链。
- 一次评测只装一个技能，而本仓库的核心回归恰恰是三个技能之间的分流（裸主图转导演、裸详情页转导演），需要同场景下三个技能同时在场才能判断。
- 真实引擎调用成本高、耗时长，适合里程碑验收，不适合每次 PR 都跑。

如果以后需要验证「安装后在真实 Agent 里的触发率」，skill-up 是合适的工具，可作为独立的手动验收环节接入；届时可以先用 `skill-up import` 把 `cases.json` 转成它认识的格式，不需要重写用例内容。

## 基线记录

2026-10-19 用 DeepSeek `deepseek-flash`（thinking 关闭）实跑：

| 套件 | 结果 | 说明 |
|---|---|---|
| 触发回归 | 23/23 通过 | 含新增用例 23；用例 20 已按现行判据改为转交 |
| 文本质量抽检 | 3/3 通过 | 三条 SOP 硬规则均被保留 |

后续改动请与本表对比；通过率下降说明路由或描述出现回归。

## 已裁决问题

### #1 用例 20 与 SKILL.md 第一判据冲突（已按方案二解决）

- 原用例「做主图，常规白底就行」预期走 `01_通用主图详情页/02 全品类主图通用 SOP`，与 SKILL.md 使用流程的裸需求第一判据矛盾：判据的排除列表不含「白底/常规主图」，按字面应转交导演技能。
- 裁决：认可现行判据，用例 20 预期改为转交 `ecom-main-image-prompts`；另补用例 23「用 02 号 SOP 出一套常规白底主图」，用点名篇号的方式覆盖 02 号 SOP。
- 两条用例互补：不点名时转交导演，点名篇号时走库内 SOP。真实 DeepSeek 跑分 23/23 通过。
- 未改动任何 SOP 内容与 SKILL.md。
- 2026-10-27 三工作室重构后，该判据位置从使用流程第 2 步移到第 3 步（第 2 步改为判工位），判据内容未变，用例预期不受影响。
- 2026-10-27 后续把 SKU 批量、模特与视频从主图台拆出成为独立工位，五工位顺序为：主图 → 详情页 → SKU → 模特与视频 → 反推。判据文字与用例预期均未变，仅工位归属变化。
