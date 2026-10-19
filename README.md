# ecom-prompt-sop

面向电商 AI 生图的提示词技能合集，兼容 ZCode 与 Claude Code。仓库包含三个可独立安装的技能：34 篇品类 SOP 全库、主图导演和详情页导演。每个子目录就是一个完整技能，拷入本地技能目录即可使用。

## 技能清单

| 技能 | 用途 | 规模 |
|---|---|---|
| `ecom-prompt-sop` | 电商生图提示词 SOP 全库，覆盖全平台主图与详情页（含跨境）、白底图、买家秀、爆款反推与风格拆解、服饰/3C/美妆/美食/家具/包包/海产/杯壶/檀木等品类、SKU 批量处理、图内文字翻译、模特换装和电商视频生成 | 1 个 `SKILL.md` + 34 篇 SOP |
| `ecom-main-image-prompts` | 主图导演。根据产品图规划整套主图方案，内置参考图产品锁定（保留/改动清单）、套图风格锁、平台合规与 AI 标注、模特人脸、图内文字、证据账本和工具适配规则 | 1 个 `SKILL.md` + 2 个参考文件 |
| `ecom-detail-page-prompts` | 详情页导演。按品类和决策链路规划详情页结构及逐页提示词，默认淘宝，可在输入中指定其他平台，内置参考图产品锁定、套图风格锁、证据账本、AI 合规和输出边界规则 | 1 个 `SKILL.md` + 1 个参考文件 |

## 仓库结构

```text
.
├─ ecom-prompt-sop/
│  ├─ SKILL.md                      # 路由：按品类、产物或动作定位 SOP
│  └─ references/
│     ├─ 01_通用主图详情页/          # 8 篇
│     ├─ 02_爆款反推与风格拆解/      # 6 篇
│     ├─ 03_品类专项/               # 10 篇
│     ├─ 04_SKU批量与跨平台处理/     # 5 篇
│     └─ 05_模特与视频生成/          # 5 篇
├─ ecom-main-image-prompts/
├─ ecom-detail-page-prompts/
├─ tools/                           # 静态检查脚本与触发用例的人类可读视图
├─ evals/                           # promptfoo 配置、用例与断言脚本
└─ .github/workflows/skill-eval.yml # CI
```

`ecom-prompt-sop/SKILL.md` 只负责路由，提示词原文都在 `references/` 下。没有指定品类的裸主图、裸详情页需求，会分别转交 `ecom-main-image-prompts` 和 `ecom-detail-page-prompts`。

## 主要能力

- 参考图产品锁定：以产品图为主，输出保留/改动清单，文字锁定作为兜底
- 套图风格锁：整套图复用同一组色板、光影、字体和版式，避免风格漂移
- 证据账本：卖点按「已确认 / 有依据 / 待补证 / 禁止」分级，避免编造宣称
- 平台 AI 标注合规：覆盖 Amazon `contains-synthetic-performer` 元数据、TikTok Shop AI 披露和国内双标识等要求
- 工具适配：为不同生图工具提供写法变体、中文文字渲染技巧和多轮编辑脚本
- 输出边界：用自然语言描述禁止项，替代简单堆砌负面词

## 安装

把需要的技能目录整体复制到本地技能目录，保持 `<技能目录>/<技能名>/SKILL.md` 的层级：

- ZCode：`~/.agents/skills/<技能名>/`，或项目级 `<项目>/.agents/skills/<技能名>/`
- Claude Code：`~/.claude/skills/<技能名>/`

以 `ecom-prompt-sop` 为例：

```bash
git clone https://github.com/ADC1920/ecom-prompt-sop.git
cp -r ecom-prompt-sop/ecom-prompt-sop ~/.agents/skills/
```

重开会话后技能会被自动发现。直接用自然语言触发即可：

- 「给这件卫衣出详情页提示词」
- 「把这批 3:4 主图转成 1:1」
- 「用 02 号 SOP 出一套常规白底主图」

## 仓库辅助工具

| 工具 | 用途 |
|---|---|
| `tools/lint_skills.py` | 静态检查：frontmatter 合规、引用文件存在性、路由表与 34 篇 SOP 双向覆盖、`SKILL.md` 长度预算、占位符闭合（【】/[]/{{}}）和密钥扫描。零第三方依赖 |
| `tools/trigger-cases.md` | 23 条触发与路由回归用例的人类可读视图，便于改版前后对照 |
| `evals/cases.json` | 23 条用例的机器可读源 |
| `evals/check_cases.py` | 校验 `cases.json` 与 `trigger-cases.md` 一致，并确认预期 SOP 路径存在 |
| `evals/promptfooconfig.yaml` | 触发回归：断言每条提示命中的技能名与 SOP 路径 |
| `evals/promptfooconfig.quality.yaml` | 文本质量抽检：读取 SOP 原文生成提示词，按硬规则评分；图片输出仍由人工检查 |

## 评测与 CI

触发回归主要判断「技能选得对不对」，因为选错技能是用户最容易感知的问题。CI 分三层：

1. **静态检查**（每次 push / PR）：运行 `tools/lint_skills.py`、`evals/check_cases.py` 和 promptfoo 配置结构校验，不需要密钥。
2. **触发回归**（每次 push / PR）：用 promptfoo 跑 23 条提示，断言返回的技能名和 SOP 路径。评测输入直接读取三个 `SKILL.md`，路由表改动会立即生效。
3. **文本质量抽检**（每周一和手动触发）：读取指定 SOP 原文生成提示词，用 `llm-rubric` 按该 SOP 的硬规则评分，图片输出不做自动评分。

模型通过 DeepSeek 官方 provider 接入，密钥不写入仓库或评测配置：

| 名称 | 类型 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | Secret | 必填。未配置时触发回归任务直接失败并给出提示，不会出现「没跑测试却全绿」 |

两份配置都使用 `deepseek:deepseek-flash` 并关闭 `thinking`，让路由 JSON 和评分结果保持稳定。需要更换模型或开启思考模式时，修改 `evals/*.yaml` 中对应的一行即可。

本地运行：

```bash
python tools/lint_skills.py
python evals/check_cases.py
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.yaml
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.quality.yaml
```

需要 Node.js 22 或更高版本。`evals/README.md` 记录了 promptfoo 的选型理由、skill-up 的评估结论和真实跑分基线。

## 维护与同步

本仓库是本地技能目录的存档镜像，同步方向为本地到仓库。技能更新后，把对应技能目录重新复制到仓库并提交：

```bash
cp -r ~/.agents/skills/ecom-prompt-sop .
git add ecom-prompt-sop
git commit -m "feat(ecom-prompt-sop): 更新说明"
```

不要在仓库内直接修改技能再反向覆盖本地目录。
