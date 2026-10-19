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
| `cases.json` | 22 条用例的唯一数据源 |
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
| 触发回归 | 21/22 通过 | 唯一失败见下方已知问题 #1 |
| 文本质量抽检 | 3/3 通过 | 三条 SOP 硬规则均被保留 |

后续改动请与本表对比；通过率下降说明路由或描述出现回归。

## 已知问题

### #1 用例 20 与 SKILL.md 第一判据冲突

- 用例：「做主图，常规白底就行」，预期 `ecom-prompt-sop` → `01_通用主图详情页/02 全品类主图通用 SOP`。
- 实跑结果：模型判为 `ecom-main-image-prompts`，理由引用 `ecom-prompt-sop/SKILL.md` 使用流程第 2 步第一判据。
- 冲突点：第一判据规定「没有任何品类专项命中，不涉及反推/翻新/复刻/SKU 批量/比例转换/图内文字翻译/买家秀/场景图/模特换装/视频，也未点名本库 SOP」即为裸主图，应转交导演技能。「常规白底」不在这份排除列表里，按字面就是裸主图。
- 同一组条件在用例 17「给这个产品做主图」里预期是转交，两条用例条件相同、预期不同，说明原用例预期与现行 SKILL.md 不一致。
- 未擅自修改，待裁决的两个方向：
  1. 改 SKILL.md 第一判据，把「白底/常规主图」列为库内场景（走 02 号 SOP），再保留用例 20 原预期。属技能内容变更，需走「技能副本 → 仓库 → 镜像」三环。
  2. 认可现行第一判据，把用例 20 预期改为转交 `ecom-main-image-prompts`；若要继续覆盖 02 号 SOP，另补一条明确点名通用 SOP 的用例。
- 在此之前，触发回归会把用例 20 判红，这是预期中的信号，不是配置错误。
