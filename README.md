# Ecom-Prompt-Studio

面向电商 AI 视觉生产的技能合集，兼容 ZCode 与 Claude Code。一个 SOP 全库按五个工作室组织，配两个导演技能补位。仓库里每个子目录就是一个完整技能，拷入本地技能目录即可使用：

- `ecom-prompt-sop`：34 篇 SOP 的**拆解库**——每篇一个原子文件，含提示词模板、规则条款、检查清单、占位符与原文全文；内部按 AI 主图台 / AI 详情页台 / SKU 批量台 / 模特与视频台 / 图片反推台五个工位路由
- `ecom-main-image-prompts`：主图导演，接无品类线索的裸主图方案
- `ecom-detail-page-prompts`：详情页导演，接无品类线索的裸详情页方案

## 五工作室

SOP 全库按五个工位组织，先判工位再定位到唯一一篇的原子，34 篇已全部拆解归档：

| 工位 | 接什么 | 产物 | 门禁 |
|---|---|---|---|
| **AI 主图台** | 主图整套、单张主图、买家秀、场景图、白底图 | 主图规划表 + 逐张提示词 + 合规检查 | 保留清单逐张复用｜卖点有依据｜首图规范已核对｜输出边界句 |
| **AI 详情页台** | 详情页整套、长图、逐页策划 | 页面规划 + 逐页提示词 | 每页先锁定后设计｜页面主题不重复｜防模板化自检 |
| **SKU 批量与跨平台台** | 多色多件套批量、多产品替换、3:4 转 1:1、图内文字批量翻译 | SKU 变体规划 + 逐张提示词 + 规格转换结果 | 变体归属标明｜只改数量颜色版式｜转换后不裁切｜文字只译不改 |
| **模特与视频台** | 模特换头换装、多姿势模特图、电商视频生成 | 模特图系列或视频提示词（含时间轴镜头） | 人脸不漂移｜服装款式一致｜露脸规则遵守｜视频有时间轴 |
| **图片反推台** | 对标图、对标视频、旧图翻新、SKU 版式复刻 | 拆解表 + 替换后提示词 + 不继承清单 | 品牌名替换｜商品特性不继承｜自有产品锁定复用｜视频必出分镜 |

混合篇（品类专项、00 号通用篇、多 SKU 篇）同时挂在两个台，整篇共用、两处指向，不拆分复制，避免同一份提示词出现两个版本。改稿按「改了什么 → 回哪台 → 下游重做什么」回流。

判工位的顺序有优先级：动作是反推翻新 → 反推台；要批量变体 → SKU 台；要真人或视频 → 模特与视频台；产物是详情页 → 详情页台；其余 → 主图台。买家秀虽名为「批量」，属同一产品同场景出图，留在主图台。

## 技能清单

| 技能 | 用途 | 规模 |
|---|---|---|
| `ecom-prompt-sop` | 电商视觉五工作室（主图台 / 详情页台 / SKU 台 / 模特与视频台 / 反推台）的 SOP 拆解库，覆盖全平台主图与详情页（含跨境）、白底图、买家秀、爆款图与视频反推、服饰/3C/美妆/美食/家具/包包/海产/杯壶/檀木等品类、SKU 批量处理、图内文字翻译、模特换装和电商视频生成 | 1 个 `SKILL.md` + 34 个原子 |
| `ecom-main-image-prompts` | 主图导演。根据产品图规划整套主图方案，内置参考图产品锁定（保留/改动清单）、套图风格锁、平台合规与 AI 标注、模特人脸、图内文字、证据账本和工具适配规则 | 1 个 `SKILL.md` + 2 个参考文件 |
| `ecom-detail-page-prompts` | 详情页导演。按品类和决策链路规划详情页结构及逐页提示词，默认淘宝，可在输入中指定其他平台，内置参考图产品锁定、套图风格锁、证据账本、AI 合规和输出边界规则 | 1 个 `SKILL.md` + 1 个参考文件 |

裸主图、裸详情页这类没有品类线索的需求，仍转交两个导演技能；五工作室承接的是有品类、动作或细分场景线索的请求。

## 仓库结构

```text
.
├─ ecom-prompt-sop/
│  ├─ SKILL.md                      # 五工作室入口：判工位 → 定位原子 → 取模板与规则
│  ├─ EVAL.md                       # 评测答案键（评测者用，不进 SKILL.md）
│  └─ references/
│     ├─ _atoms/                    # 34 个原子：模板/规则/清单/占位符 + 原文全文
│     │  ├─ a01.json … a34.json
│     │  ├─ index.json              # 原子索引（编号、任务、工位、数量）
│     │  ├─ semantic.json           # 语义层（每篇一句话任务与标签）
│     │  └─ _mech/                  # 机械层（提取中间产物）
│     ├─ _rules/                    # 平台 / 品类 / 场景判据
│     ├─ _corpus/                   # 正样本语料（已验证提示词）
│     ├─ _index.json                # 篇目索引（含槽位映射与原文历史路径）
│     └─ _prompt-slots.md           # 五槽位规范
├─ ecom-main-image-prompts/
├─ ecom-detail-page-prompts/
├─ tools/                           # 检查、组装、机检、闭环、拆解脚本
├─ evals/                           # promptfoo 配置、用例与断言脚本
└─ .github/workflows/skill-eval.yml # CI
```

`ecom-prompt-sop/SKILL.md` 只负责分台与路由，每个工位的篇目表直接给出原子编号；执行时读 `_atoms/aNN.json`，取模板、规则、验收项。34 篇原文已拆解进原子（`source_text` 保留全文），`references/` 下不再有散落的 SOP 文件。没有指定品类的裸主图、裸详情页需求，会分别转交 `ecom-main-image-prompts` 和 `ecom-detail-page-prompts`。

## 主要能力

- 参考图产品锁定：以产品图为主，输出保留/改动清单，文字锁定作为兜底
- 套图风格锁（10 字段）：色板、光影、背景系统、镜头、构图、文字层级、材质处理、道具白名单、品牌调性、通用边界，整套图原样复用，交付前做漂移自检
- 证据账本：卖点按「已确认 / 有依据 / 待补证 / 禁止」分级，避免编造宣称
- 资料不足先出卖点信息大纲：只给产品图或零散规格时，先交付卖点池与四态准入（可直接用/需核实/仅类目教育/禁用），用户确认后再写提示词
- 平台 AI 标注合规：覆盖 Amazon `contains-synthetic-performer` 元数据、TikTok Shop AI 披露和国内双标识等要求
- 工具适配：为不同生图工具提供写法变体、中文文字渲染技巧和多轮编辑脚本
- 输出边界：用自然语言描述禁止项，替代简单堆砌负面词
- 反 AI 感双层过滤：文字层清掉 8k / masterpiece 这类堆词，视觉层避开过度光滑、塑料高光、完美对称、悬浮无投影等八类 AI 痕迹
- 生成后机检：出图后按目标平台检查白底纯度、主体占比、比例、分辨率与图内文字，机检不过的不上架

## 拆解原子（唯一载体）

34 篇原文里混着五样东西：解释、提示词模板、规则条款、检查清单、占位符。`tools/atomize.py` 把它们分开，**原文全文也一并存进原子**，所以 `references/` 下不再需要散落的 SOP 文件：

- `ecom-prompt-sop/references/_atoms/index.json`：34 个原子的索引（编号、一句话任务、工位、模板/规则/清单数量）
- `ecom-prompt-sop/references/_atoms/aNN.json`：每篇一个原子，含
  - `templates`：提示词模板，代码块型（```）与裸段落型（跟在提示词小标题下的纯文本）都收，带原文行号
  - `rules`：正文里的规则条款（带「必须 / 禁止 / 不得」等，带行号），模板内的不重复抽
  - `checklists`：验收清单、板块要求这类编号条目
  - `placeholders`：需要替换的占位符清单
  - `source_text`：原文全文——原子自包含的关键，脱离外部文件也能读到上下文与示例
  - `source`：原文行数与 sha，用于校验 `source_text` 是否被改过

拆完之后：路由读索引，取提示词读 `templates`，查合规判据读 `rules`，验收读 `checklists`，需要上下文与示例读 `source_text`。

```bash
python tools/atomize.py check     # 自包含校验：source_text、模板、规则、清单是否自洽（不读磁盘原文）
python tools/atomize.py merge     # 合并语义层，重新生成原子与索引
python tools/atomize.py restore   # 应急：从原子的 source_text 还原出 34 篇原文
python tools/atomize.py extract   # 仅当原文还在时可用：重新提取机械层
```

改原子的正确姿势：直接改 `_atoms/aNN.json` 里的 `templates` / `rules`（改完 `check` 会重新算 sha 并提示是否一致），或者在 `semantic.json` 里改任务与标签后 `merge`。

## 判据规则与语料

34 篇 SOP 给的是「方法」，`_rules/` 与 `_corpus/` 给的是「判据与范例」——两者都不依赖散落的原文文件：

- `ecom-prompt-sop/references/_rules/`：平台、品类、场景三份 JSON，把原文里的硬判据变成可校验规则（白底与占比阈值、禁用宣称、必填槽位、画面禁项、AI 标注义务）。`tools/rules_engine.py` 读它做校验与约束注入。
- `ecom-prompt-sop/references/_corpus/`：验证过并出过好图的提示词样本，`tools/corpus.py` 按相似度检索并编译成 few-shot 范例段。

规则管「不能写什么」，语料管「写成什么样才算够」。原文删掉之后，这两样仍然成立。

## 安装

把需要的技能目录整体复制到本地技能目录，保持 `<技能目录>/<技能名>/SKILL.md` 的层级：

- ZCode：`~/.agents/skills/<技能名>/`，或项目级 `<项目>/.agents/skills/<技能名>/`
- Claude Code：`~/.claude/skills/<技能名>/`

以 `ecom-prompt-sop` 这个技能为例（仓库名是 `Ecom-Prompt-Studio`）：

```bash
git clone https://github.com/ADC1920/Ecom-Prompt-Studio.git
cp -r Ecom-Prompt-Studio/ecom-prompt-sop ~/.agents/skills/
```

重开会话后技能会被自动发现。直接用自然语言触发即可，按工位举例：

- 主图台：「给这件卫衣出一套主图提示词」
- 详情页台：「保温杯的详情页提示词出一套」
- SKU 台：「批量出 5 件套的 SKU 图」「这批 3:4 主图转成 1:1」
- 模特与视频台：「模特换装做三个姿势」「这个产品出条视频提示词」
- 反推台：「把这张爆款图反推成我们自己的提示词」「拆解这个视频的镜头提示词」

## 仓库辅助工具

| 工具 | 用途 |
|---|---|
| `tools/lint_skills.py` | 静态检查：frontmatter 合规、引用文件存在性、路由表与 34 篇 SOP 双向覆盖、34 篇机器可读索引一致、SKILL.md 点名的工具脚本存在、`SKILL.md` 长度预算、占位符闭合（【】/[]/{{}}）和密钥扫描。零第三方依赖 |
| `tools/atomize.py` | 原文拆解器：把 34 篇拆成模板（代码块型与裸段落型）、正文规则句、检查清单、占位符，并把原文全文存进原子；`check` 做自包含校验（不读磁盘原文），`restore` 可从原子还原原文 |
| `tools/trigger-cases.md` | 30 条触发与路由回归用例的人类可读视图，便于改版前后对照 |
| `tools/check_image.py` | 出图后平台机检：白底纯度、主体占比、比例、分辨率、文件大小、透明通道、OCR 文字；`--fix` 自动归一白底、补比例、放大。仅依赖 Pillow，OCR 可选 |
| `tools/slop_check.py` | 提示词定稿前自查：SD 时代堆词、绝对化用语、虚假促销、功效宣称、认证背书、AI 痕迹特征。零依赖 |
| `tools/compose_prompt.py` | 五槽位组装器：槽位 JSON 编译成成品提示词（保真段 → 场景 → 主体 → 细节 → 用途 → 约束），自动补平台约束并跑必填与反 AI 感校验。零依赖 |
| `tools/run_loop.py` | 出图闭环：生成 → 平台机检 → 把修复句写回提示词 → 重跑，到轮次上限为止，每轮落盘并给 manifest；离线 `--dry-run` 不出图只推演修复句 |
| `tools/rules_engine.py` | 判据规则引擎：按平台、品类、场景三份规则校验槽位，查白底冲突、禁用宣称、必填槽位缺失，可 `--inject` 补默认约束 |
| `tools/visual_audit.py` | 视觉验收：主体一致性（感知哈希 + 颜色直方图）与 AI 感启发式（饱和度 / 平滑度 / 死白 / 边缘密度），只提示不判定 |
| `tools/corpus.py` | 正样本语料库：已验证提示词的录入、相似度检索、编译成 few-shot 范例段 |
| `tools/fix_stats.py` | 修复句效果统计：从闭环 manifest 算出每条修复句的真实生效率，用来判断措辞要不要改 |
| `evals/cases.json` | 30 条用例的机器可读源 |
| `evals/check_cases.py` | 校验 `cases.json` 与 `trigger-cases.md` 一致，并确认预期 SOP 路径存在 |
| `evals/promptfooconfig.yaml` | 触发回归：断言每条提示命中的技能名与 SOP 路径 |
| `evals/promptfooconfig.quality.yaml` | 文本质量抽检：从原子读 `source_text` 生成提示词，按硬规则评分；图片输出仍由人工检查 |
| `tools/qwen_image.py` | 命令行出图通道：提示词直接投喂 Qwen-Image 2.1 Pro，支持文生图与最多 10 张参考图的图生图 |
| `tools/IMAGE-GEN-AUTHORIZATION.md` | **出图授权规则（硬性）**：任何图片生成模型调用前须取得用户授权，说明用途与预计花费 |

## 云端出图（Qwen-Image 2.1 Pro）

> **出图先授权**：本项目限制任何图片生成模型（Qwen-Image 全系、wan/万相、Seedream、Gemini/Nano Banana、GPT-Image、FLUX、z-image 等，含 MCP 工具与网页端代操作）在调用前必须取得用户授权，并说明用途、模型、张数与预计花费。规则与记录字段见 [`tools/IMAGE-GEN-AUTHORIZATION.md`](tools/IMAGE-GEN-AUTHORIZATION.md)。`tools/qwen_image.py` 已内置闸门，缺 `--authorize` / `--purpose` / `--unit-price` 直接拒绝，不发出请求。

`tools/qwen_image.py` 走阿里云百炼 DashScope 同步接口，把 SOP 产出的提示词直接变成图片，省去手工复制到网页端。密钥只从环境变量 `DASHSCOPE_API_KEY` 或 `--key-file` 读取，不写入仓库任何文件：

```bash
export DASHSCOPE_API_KEY="sk-..."
python tools/qwen_image.py -p "提示词" --size 1024*1024 -o out \
  --authorize "用户 2026-10-29 14:20 回复：可以" --purpose "产品A 天猫主图第 2 张" --unit-price 0.25
python tools/qwen_image.py -f prompt.txt -i front.jpg -i detail.jpg -n 2 --seed 42 \
  --authorize "用户 2026-10-29 14:20 回复：可以" --purpose "产品A 主图组" --unit-price 0.25
```

脚本在发请求前打印「张数 × 单价 = 预计花费」并追加写入 `out/authorization.log`（已在 `.gitignore` 中忽略，只留本机）。单价按官方页面当时数值填写，拿不到确切单价就先问用户，不猜数字。

图生图用于产品锁定和翻新：把产品实拍图作为参考图，提示词里写清保留清单与改动清单。提示词默认按原文投喂、不做模型改写，SOP 里的硬规则不会被稀释；只有提示词很短、希望模型自行扩写时才加 `--prompt-extend`。`-n` 最多 6 张，`--size` 支持 `auto` 或 `宽*高`，输出落在 `out/`（已在 `.gitignore` 中忽略）。`python tools/qwen_image.py --selftest` 可离线校验参数、授权闸门与响应解析。

## 评测与 CI

触发回归主要判断「技能选得对不对」，因为选错技能是用户最容易感知的问题。CI 分三层：

1. **静态检查**（每次 push / PR）：运行 `tools/lint_skills.py`（含索引覆盖、槽位名合法性、规则与语料合法性、原子结构与路由引用、工具引用、EVAL 完整性）、`evals/check_cases.py`、`tools/atomize.py check`（原子自包含校验）、九个工具脚本的离线自检，以及 promptfoo 配置结构校验，不需要密钥。
2. **触发回归**（每次 push / PR）：用 promptfoo 跑 30 条提示，断言返回的技能名和 SOP 路径。评测输入直接读取三个 `SKILL.md`，路由表改动会立即生效。
3. **文本质量抽检**（每周一和手动触发）：按原子编号读 `source_text` 生成提示词，用 `llm-rubric` 按该 SOP 的硬规则评分，图片输出不做自动评分。

三个技能各带一份 `EVAL.md` 答案键（能力边界题 / 生产决策题 / 应用任务 + 评分口径），供人工或独立评测流程使用。答案键不链接进 `SKILL.md`，`lint_skills.py` 会校验它存在且未被入口引用，避免被评 agent 直接读到答案。

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
