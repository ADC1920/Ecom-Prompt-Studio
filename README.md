# ecom-prompt-studio

面向电商 AI 视觉生产的技能合集，兼容 ZCode 与 Claude Code。一个 SOP 全库按五个工作室组织，配两个导演技能补位。仓库里每个子目录就是一个完整技能，拷入本地技能目录即可使用：

- `ecom-prompt-sop`：34 篇 SOP 原文库，内部按 AI 主图台 / AI 详情页台 / SKU 批量台 / 模特与视频台 / 图片反推台五个工位路由
- `ecom-main-image-prompts`：主图导演，接无品类线索的裸主图方案
- `ecom-detail-page-prompts`：详情页导演，接无品类线索的裸详情页方案

## 五工作室

SOP 全库按五个工位组织，先判工位再定位篇目，34 篇原文一篇未改、结构未拆：

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
| `ecom-prompt-sop` | 电商视觉五工作室（主图台 / 详情页台 / SKU 台 / 模特与视频台 / 反推台）的 SOP 原文库，覆盖全平台主图与详情页（含跨境）、白底图、买家秀、爆款图与视频反推、服饰/3C/美妆/美食/家具/包包/海产/杯壶/檀木等品类、SKU 批量处理、图内文字翻译、模特换装和电商视频生成 | 1 个 `SKILL.md` + 34 篇 SOP |
| `ecom-main-image-prompts` | 主图导演。根据产品图规划整套主图方案，内置参考图产品锁定（保留/改动清单）、套图风格锁、平台合规与 AI 标注、模特人脸、图内文字、证据账本和工具适配规则 | 1 个 `SKILL.md` + 2 个参考文件 |
| `ecom-detail-page-prompts` | 详情页导演。按品类和决策链路规划详情页结构及逐页提示词，默认淘宝，可在输入中指定其他平台，内置参考图产品锁定、套图风格锁、证据账本、AI 合规和输出边界规则 | 1 个 `SKILL.md` + 1 个参考文件 |

裸主图、裸详情页这类没有品类线索的需求，仍转交两个导演技能；五工作室承接的是有品类、动作或细分场景线索的请求。

## 仓库结构

```text
.
├─ ecom-prompt-sop/
│  ├─ SKILL.md                      # 五工作室入口：判工位 → 定位唯一一篇 → 读原文
│  └─ references/                   # 34 篇原文，按内容分类存放，未被拆分或改写
│     ├─ 01_通用主图详情页/          # 8 篇
│     ├─ 02_爆款反推与风格拆解/      # 6 篇（反推台主力）
│     ├─ 03_品类专项/               # 10 篇（主图台与详情页台共用）
│     ├─ 04_SKU批量与跨平台处理/     # 5 篇（SKU 台）
│     └─ 05_模特与视频生成/          # 5 篇（模特与视频台 2 篇 + 反推台视频反推 3 篇）
├─ ecom-main-image-prompts/
├─ ecom-detail-page-prompts/
├─ tools/                           # 静态检查脚本与触发用例的人类可读视图
├─ evals/                           # promptfoo 配置、用例与断言脚本
└─ .github/workflows/skill-eval.yml # CI
```

`ecom-prompt-sop/SKILL.md` 只负责分台与路由，提示词原文都在 `references/` 下，目录名保持原有内容分类，没有按工位搬动文件。没有指定品类的裸主图、裸详情页需求，会分别转交 `ecom-main-image-prompts` 和 `ecom-detail-page-prompts`。

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

以 `ecom-prompt-sop` 这个技能为例（仓库名是 `ecom-prompt-studio`）：

```bash
git clone https://github.com/ADC1920/ecom-prompt-studio.git
cp -r ecom-prompt-studio/ecom-prompt-sop ~/.agents/skills/
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
| `tools/lint_skills.py` | 静态检查：frontmatter 合规、引用文件存在性、路由表与 34 篇 SOP 双向覆盖、`SKILL.md` 长度预算、占位符闭合（【】/[]/{{}}）和密钥扫描。零第三方依赖 |
| `tools/trigger-cases.md` | 23 条触发与路由回归用例的人类可读视图，便于改版前后对照 |
| `evals/cases.json` | 23 条用例的机器可读源 |
| `evals/check_cases.py` | 校验 `cases.json` 与 `trigger-cases.md` 一致，并确认预期 SOP 路径存在 |
| `evals/promptfooconfig.yaml` | 触发回归：断言每条提示命中的技能名与 SOP 路径 |
| `evals/promptfooconfig.quality.yaml` | 文本质量抽检：读取 SOP 原文生成提示词，按硬规则评分；图片输出仍由人工检查 |
| `tools/qwen_image.py` | 命令行出图通道：提示词直接投喂 Qwen-Image 2.1 Pro，支持文生图与最多 10 张参考图的图生图 |

## 云端出图（Qwen-Image 2.1 Pro）

`tools/qwen_image.py` 走阿里云百炼 DashScope 同步接口，把 SOP 产出的提示词直接变成图片，省去手工复制到网页端。密钥只从环境变量 `DASHSCOPE_API_KEY` 或 `--key-file` 读取，不写入仓库任何文件：

```bash
export DASHSCOPE_API_KEY="sk-..."
python tools/qwen_image.py -p "提示词" --size 1024*1024 -o out
python tools/qwen_image.py -f prompt.txt -i front.jpg -i detail.jpg -n 2 --seed 42
```

图生图用于产品锁定和翻新：把产品实拍图作为参考图，提示词里写清保留清单与改动清单。提示词默认按原文投喂、不做模型改写，SOP 里的硬规则不会被稀释；只有提示词很短、希望模型自行扩写时才加 `--prompt-extend`。`-n` 最多 6 张，`--size` 支持 `auto` 或 `宽*高`，输出落在 `out/`（已在 `.gitignore` 中忽略）。`python tools/qwen_image.py --selftest` 可离线校验参数与响应解析。

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
