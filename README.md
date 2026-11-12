# Ecom-Prompt-Studio

电商 AI 视觉提示词工程：把「怎么写提示词」变成可检索、可校验、可回归的生产流程。

模型已经会写提示词。真正缺的是三样东西——**判据、范例、反馈**，这个仓库就是围着这三样长起来的：

- **判据**：整套 SOP 拆成 197 个提示词模板、571 条规则句、181 条检查项、122 个占位符，每一条都能被程序读
- **范例**：正样本语料库，按相似度检索出已经出过好图的写法
- **反馈**：出图后按平台机检，不过的不上架；修复句回写进提示词再跑一轮

仓库里每个子目录就是一个完整技能，拷进本地技能目录即可使用。

## 快速开始

### 推荐：作为 ZCode 插件安装

仓库根就是插件，三个技能、四条斜杠命令、出图后自动机检、MCP server 一次装齐：

```bash
git clone https://github.com/ADC1920/Ecom-Prompt-Studio.git
```

在 ZCode 里打开 **插件市场 → 添加 → 添加插件市场**，粘贴克隆下来的目录，然后在**个人**里安装 `ecom-prompt-studio`。

只拷单个技能目录也能用，但那会丢掉 `tools/`：机检、规则引擎、语料检索、MCP 工具都不在技能目录里，SKILL.md 提到脚本的地方只能人工代劳。要完整能力就走插件。

### 手动：只拷技能

```bash
git clone https://github.com/ADC1920/Ecom-Prompt-Studio.git

# ZCode（或项目级 .agents/skills/）
cp -r Ecom-Prompt-Studio/ecom-prompt-sop ~/.agents/skills/

# Claude Code
cp -r Ecom-Prompt-Studio/ecom-prompt-sop ~/.claude/skills/
```

重开会话后技能自动生效，直接用自然语言触发，不需要提「SOP」这个词：

| 工位 | 一句话示例 |
|---|---|
| 主图台 | 给这件卫衣出一套主图提示词 |
| 详情页台 | 保温杯的详情页提示词出一套 |
| SKU 台 | 批量出 5 件套的 SKU 图 / 这批 3:4 主图转成 1:1 |
| 模特与视频台 | 模特换装做三个姿势 / 这个产品出条视频提示词 |
| 反推台 | 把这张爆款图反推成我们自己的提示词 / 拆解这个视频的镜头提示词 |

## 三个技能

| 技能 | 接什么 | 规模 |
|---|---|---|
| `ecom-prompt-sop` | 五工作室 SOP 原子库：主图、详情页、SKU 批量、模特与视频、图片反推 | 1 个 `SKILL.md` + 原子库 |
| `ecom-main-image-prompts` | 主图导演：接无品类线索的裸主图方案，按买家决策链路动态规划整套 | 1 个 `SKILL.md` + 2 个参考文件 |
| `ecom-detail-page-prompts` | 详情页导演：接无品类线索的裸详情页方案，按品类规划页面结构与逐页提示词 | 1 个 `SKILL.md` + 1 个参考文件 |

分工判据只有一条：**有品类、动作或细分场景线索 → 走 SOP 原子库；裸主图或裸详情页 → 转交导演技能**。这条规则写死在 `ecom-prompt-sop/SKILL.md` 的使用流程里，评测会盯着它。

## 五工作室

SOP 库按五个工位组织，先判工位再定位到唯一一个原子：

| 工位 | 接什么 | 产物 | 门禁 |
|---|---|---|---|
| **AI 主图台** | 主图整套、单张主图、买家秀、场景图、白底图 | 主图规划表 + 逐张提示词 + 合规检查 | 保留清单逐张复用｜卖点有依据｜首图规范已核对｜输出边界句 |
| **AI 详情页台** | 详情页整套、长图、逐页策划 | 页面规划 + 逐页提示词 | 每页先锁定后设计｜页面主题不重复｜防模板化自检 |
| **SKU 批量与跨平台台** | 多色多件套批量、多产品替换、3:4 转 1:1、图内文字批量翻译 | SKU 变体规划 + 逐张提示词 + 规格转换结果 | 变体归属标明｜只改数量颜色版式｜转换后不裁切｜文字只译不改 |
| **模特与视频台** | 模特换头换装、多姿势模特图、电商视频生成 | 模特图系列或视频提示词（含时间轴镜头） | 人脸不漂移｜服装款式一致｜露脸规则遵守｜视频有时间轴 |
| **图片反推台** | 对标图、对标视频、旧图翻新、SKU 版式复刻 | 拆解表 + 替换后提示词 + 不继承清单 | 品牌名替换｜商品特性不继承｜自有产品锁定复用｜视频必出分镜 |

判工位有优先级：动作是反推翻新 → 反推台；要批量变体 → SKU 台；要真人或视频 → 模特与视频台；产物是详情页 → 详情页台；其余 → 主图台。买家秀虽名为「批量」，但属同一产品同场景出图，留在主图台。

混合篇目（品类专项、通用总纲、多 SKU）同时挂在两个台，整份共用、两处指向，不拆分复制——避免同一份提示词出现两个版本。改稿按「改了什么 → 回哪台 → 下游重做什么」回流。

## 为什么是原子

SOP 内容里混着五样东西：解释、提示词模板、规则条款、检查清单、占位符。直接塞进上下文，等于让模型在一堆散文里自己挑。

`tools/atomize.py` 把它们拆开，并把完整内容一并存进原子（`source_text`），所以拆完之后一个文件就够用：

| 字段 | 内容 | 怎么用 |
|---|---|---|
| `templates` | 提示词模板，代码块型与裸段落型都收，带行号 | 直接取 `text` 投喂 |
| `rules` | 正文里的规则条款，带行号 | 自查合规 |
| `checklists` | 验收清单、板块要求 | 交付前逐条过 |
| `placeholders` | 需替换的占位符 | 防止原样输出 |
| `source_text` | 完整内容 | 需要上下文与示例时读 |

拆解总账：**模板 197 个 · 规则句 571 条 · 清单 181 条 · 占位符 122 个**，全部可按编号取出。

```bash
python tools/atomize.py check     # 自包含校验：source_text、模板、规则、清单是否自洽
python tools/atomize.py merge     # 改完 semantic.json 后重建原子与索引
python tools/atomize.py restore   # 从原子的完整内容导出可读文本
```

改原子的正确姿势：直接改 `_atoms/aNN.json` 的 `templates` / `rules`，或改 `semantic.json` 后 `merge`。

## 工具链

不是一堆零散脚本，是一条链路：

```
拆解 ──→ 组装 ──→ 自查 ──→ 机检 ──→ 验收 ──→ 统计
atomize  compose  slop     check    visual   fix_stats
        prompt   _check  _image   _audit
```

| 工具 | 做什么 |
|---|---|
| `tools/atomize.py` | 拆解与自包含校验，含导出 |
| `tools/compose_prompt.py` | 五槽位组装：保真段 → 场景 → 主体 → 细节 → 用途 → 约束，自动补平台约束、跑必填校验 |
| `tools/slop_check.py` | 提示词定稿前查 SD 时代堆词、绝对化用语、虚假促销、功效宣称、AI 痕迹 |
| `tools/rules_engine.py` | 按平台、品类、场景三份判据规则校验槽位，可 `--inject` 补默认约束 |
| `tools/check_image.py` | 出图后平台机检：白底纯度、主体占比、比例、分辨率、文件大小、透明通道、图内文字 |
| `tools/visual_audit.py` | 视觉验收：主体一致性（感知哈希 + 颜色直方图）与 AI 感启发式，只提示不判定 |
| `tools/fix_stats.py` | 从 manifest 统计每条修复句的真实生效率，用来判断措辞要不要改 |
| `tools/corpus.py` | 正样本语料：录入、相似度检索、编译成 few-shot 范例段 |
| `tools/vlm_review.py` | 生成视觉复核单：启发式分只提示，结论由人给 |
| `tools/mcp_server.py` | MCP server：把原子库与判据暴露成四个可调用工具 |
| `tools/lint_skills.py` | 静态检查全集，CI 的第一道门 |
| `tools/check_plugin.py` | 插件清单自校验：字段、资源存在性、路径越界、事件名合法性 |

除 `check_image.py`、`visual_audit.py`、`vlm_review.py` 用到 Pillow 外全是标准库；带 `--selftest` 的都能离线验，不依赖密钥与网络。

## 装机后自带的能力

装成插件之后，下面这些不靠模型自觉，是运行时机制：

| 机制 | 触发 | 效果 |
|---|---|---|
| 出图后自动机检 | 任何工具调用在 `out/` 下落了图，且命令里带 `--platform` | 跑平台机检，不通过就把结果回注给模型，提示修正重出 |
| MCP 四个工具 | 模型自行调用 | `query_atom` 定位原子、`get_template` 取模板、`validate_prompt` 校验、`check_output` 机检 |
| 斜杠命令 | 用户输入 `/ecom:main` 等 | 不用记五工位术语，直接进对应工位流程 |

MCP 工具的意义在于把「读文档 → 判工位 → 读原子 → 挑模板」四步压成一次调用。不接 MCP 时这四步全靠模型自己走。

`check_image.py` 的 OCR 会自己找 tesseract：不在 PATH 时扫常见安装路径，默认语言目录缺中文时去找用户级 tessdata。缺依赖就标 `skipped`，不会假装通过。

## 判据规则与语料

SOP 给的是「方法」，下面几样给的是「判据与范例」：

- `references/_rules/`：平台（12）、品类（9）、场景（11）三份 JSON，把硬判据变成可校验规则——白底与占比阈值、禁用宣称、必填槽位、画面禁项、AI 标注义务
- `references/_rules/aigc-disclosure.json`：AIGC 标注义务与法律依据，五地法条、图类型四分类、四条红线
- `references/_brand-lock.md`：品牌锁十个必锁字段与 prepend 写法，解跨图漂移
- `references/_corpus/`：验证过并出过好图的提示词样本，按相似度检索、编译成 few-shot

规则管「不能写什么」，语料管「写成什么样才算够」，品牌锁管「一套图看着像不像同一家」。

## 出图与授权

> **出图先授权（硬性）**：任何图片生成模型（Qwen-Image 全系、wan/万相、Seedream、Gemini、GPT-Image、FLUX、z-image 等，含 MCP 工具与网页端代操作）调用前必须先取得明确授权，说明用途、模型与张数；未获授权时只交付提示词文本，不调用任何出图模型。

仓库不再内置命令行出图通道：2026-11-10 按用户指令移除 `tools/qwen_image.py`、`tools/run_loop.py` 与规则正本 `tools/IMAGE-GEN-AUTHORIZATION.md`，此后出图走用户指定的外部通道。机检与视觉验收脚本仍在 `tools/`，可对任意通道产出的图做后置校验。

图生图用于产品锁定与翻新：产品实拍图作参考图，提示词里写清保留清单与改动清单。提示词默认按内容投喂、不做模型改写，硬规则不会被稀释。

## 评测与 CI

技能选错是用户最容易感知的问题，所以触发回归是评测主线。CI 分三层：

1. **静态检查**（每次 push / PR）：`lint_skills.py` + `check_cases.py` + `atomize.py check` + `check_plugin.py` + 十一个工具自检 + promptfoo 配置结构校验，不需要密钥
2. **触发回归**（每次 push / PR）：promptfoo 跑 30 条提示，断言命中的技能名与**原子编号**。评测输入直接读三个 `SKILL.md`，路由表一改立刻生效
3. **文本质量抽检**（每周一 + 手动）：按原子编号读 `source_text` 生成提示词，用 `llm-rubric` 按该 SOP 的硬规则评分

三层之外还有一套**真实触发评测**（`evals/real_trigger.py`），只在里程碑手动跑：把技能目录交给真实引擎，看它是否自行加载并走到正确原子。前两层抓不到「装了但不触发」，这一层能，代价是慢且可能计费。

三个技能各带一份 `EVAL.md` 答案键（能力边界题 / 生产决策题 / 应用任务 + 评分口径）。答案键不链接进 `SKILL.md`，`lint_skills.py` 会校验它存在且未被入口引用——避免被评的 agent 直接读到答案。

模型经 DeepSeek 官方 provider 接入，密钥走仓库 Secret `DEEPSEEK_API_KEY`，不落任何文件。未配置时触发回归直接失败并报错，不会出现「没跑测试却全绿」。

本地跑：

```bash
python tools/lint_skills.py
python tools/check_plugin.py
python evals/check_cases.py
python evals/real_trigger.py --dry-run        # 看真实评测会跑哪些用例
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.yaml
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.quality.yaml
```

需要 Node.js 22+。选型理由与真实跑分基线见 [`evals/README.md`](evals/README.md)。

## 仓库结构

```text
.
├─ .zcode-plugin/plugin.json        # 插件清单：技能 + 命令 + hooks + MCP
├─ .mcp.json                        # MCP server 声明（四个工具）
├─ hooks/
│  ├─ hooks.json                    # PostToolUse 匹配出图调用
│  └─ check_after_image.py          # 出图后自动机检并回注结果
├─ commands/                        # /ecom:main /detail /sku /reverse
├─ ecom-prompt-sop/
│  ├─ SKILL.md                      # 五工作室入口：判工位 → 定位原子 → 取模板与规则
│  ├─ EVAL.md                       # 评测答案键（评测者用，不被 SKILL.md 引用）
│  └─ references/
│     ├─ _atoms/                    # 原子库 + 索引 + 语义层 + 机械层
│     ├─ _rules/                    # 平台 / 品类 / 场景判据 + AIGC 标注义务
│     ├─ _corpus/                   # 正样本语料
│     ├─ _index.json                # 篇目索引（槽位映射）
│     ├─ _brand-lock.md             # 品牌锁十个字段
│     └─ _prompt-slots.md           # 五槽位规范
├─ ecom-main-image-prompts/
├─ ecom-detail-page-prompts/
├─ tools/                           # 拆解、组装、机检、验收、统计、MCP、插件校验
├─ evals/                           # promptfoo 配置、用例、断言脚本、真实触发评测
├─ CHANGELOG.md
├─ README.en.md
└─ .github/workflows/skill-eval.yml # CI（三个 job：静态 / 触发回归 / 质量抽检）
```

`ecom-prompt-sop/SKILL.md` 只负责分台与路由，每个工位的篇目表直接给出原子编号；执行时读 `_atoms/aNN.json` 取模板、规则、验收项。原子自包含，取一个文件即可完成一次交付。

## 已知限制

- **AI 感阈值是经验值**：`visual_audit.py` 的饱和度、平滑度、死白、边缘密度这些判据，还没用真实的好图 / AI 图批次标定过，当提示用，不当结论
- **语料库只有 2 条种子**：检索质量取决于样本量，现在属于「能用但不够准」。它靠真实出图积累，不能人工编造，所以这一步只能等实际使用
- **VLM 复核不自动判图**：`vlm_review.py` 只生成复核单，不给结论。VLM 在「保留约束是否满足」这类细粒度判断上会失准，把它的分数当通过依据会把错误固化
- **OCR 需要本地装 tesseract**：缺 pytesseract 或 tesseract 时这项走 skipped，不会误报通过；CI 环境没装，所以云端不检查图内文字
- **模板抽取有少量噪声**：少数没有围栏代码块的篇目走裸段落规则，个别片段可能偏宽，未逐篇人工复核
- **真实触发评测需自备引擎**：`evals/real_trigger.py` 只提供框架与判定逻辑，引擎命令与凭据由使用者提供，CI 里只跑它的离线自检
