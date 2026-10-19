# ecom-prompt-sop

电商 AI 生图提示词技能合集（ZCode / Claude Code 兼容）：34 篇品类 SOP 全库 + 主图导演 + 详情页导演。仓库内每个子目录即一个独立技能，可直接拷入本地技能目录使用。

> **版权与传播声明**：本仓库内容归仓库所有者所有，为私有存档用途。在版权归属确认并发布公开许可之前，请勿克隆、转载或公开传播本仓库内容。

## 技能清单

| 技能 | 内容 | 规模 |
|---|---|---|
| `ecom-prompt-sop` | 电商生图提示词 SOP 全库：34 篇按品类与场景分类的中文提示词模板，含全平台主图/详情页（含跨境）、白底图、买家秀、爆款反推与风格拆解、品类专项（服饰/3C/美妆/美食/家具/包包/海产/杯壶/檀木）、SKU 批量与图内文字翻译、模特换装与电商视频生成/视频反推 | 1 SKILL.md + 34 篇 |
| `ecom-main-image-prompts` | 全平台电商主图生图提示词导演：基于产品图动态规划整套主图方案，内置参考图产品锁定（保留/改动清单）、套图风格锁、平台合规与 AI 标注、模特人脸、图内文字、证据账本、工具适配等硬规则 | 1 SKILL.md + 2 参考文件 |
| `ecom-detail-page-prompts` | 全平台电商详情页生图提示词导演：按品类与决策链路规划详情页页面结构与逐页提示词（默认淘宝，其他平台可在输入中指定），内置参考图产品锁定、套图风格锁、证据账本、AI 合规与输出边界等硬规则 | 1 SKILL.md + 1 参考文件 |

## 仓库结构

```text
ecom-prompt-sop/
├─ SKILL.md                     # 路由：按「品类 / 产物 / 动作」定位到对应 SOP
└─ references/
   ├─ 01_通用主图详情页/          # 8 篇：整套主图/详情页、跨境、五点卖点、买家秀、场景图、白底图
   ├─ 02_爆款反推与风格拆解/      # 6 篇：主图/详情页反推、对标场景、旧图翻新、SKU 复刻、风格拆解
   ├─ 03_品类专项/               # 10 篇：服饰、3C 数码、美妆日化、美食、家具、包包、海产、杯壶、檀木
   ├─ 04_SKU批量与跨平台处理/     # 5 篇：多数量/多 SKU 批量、多产品替换、比例转换、图内文字翻译
   └─ 05_模特与视频生成/          # 5 篇：电商视频生成、模特换头换装、视频反推（含故事板）

ecom-main-image-prompts/         # 主图导演：SKILL.md + references/（平台规则、工具适配）
ecom-detail-page-prompts/        # 详情页导演：SKILL.md + references/（工具适配）
tools/                           # 仓库辅助：静态检查脚本与触发回归用例（人类可读视图）
evals/                           # 触发回归与质量抽检：promptfoo 配置、机器可读用例、断言脚本
.github/workflows/skill-eval.yml # CI：静态检查 + 触发回归 + 周度文本质量抽检
```

`ecom-prompt-sop` 的 SKILL.md 只做路由，提示词原文均在 references 各文档中；不含品类的裸主图/裸详情页需求，分别转交两个导演技能承接。

## 2026-10 升级要点

- 两个导演技能产品锁定升级为「参考图为主 + 保留/改动清单」，文字锁定降为兜底（新一代生图工具普遍支持多图参考）
- 新增套图风格锁：整套图的色板、光影、字体、版式原样复用，防套图风格漂移
- 新增证据账本：卖点按「已确认 / 有依据 / 待补证 / 禁止」四级分类，防编造宣称
- 新增平台 AI 标注合规：Amazon `contains-synthetic-performer` 元数据、TikTok Shop AI 披露、国内双标识等义务写入检查项
- 新增生图工具适配指引 `references/tool-adaptation.md`：各工具写法变体、中文文字渲染技巧、多轮编辑脚本
- 负面词堆砌改为「输出边界」自然语言句；34 篇 SOP 保持原文，包包类（994 行）新增目录导航

## 仓库辅助工具

| 工具 | 用途 |
|---|---|
| `tools/lint_skills.py` | 技能库静态检查：frontmatter 合规、引用文件存在性、路由表与 34 篇 SOP 双向覆盖、SKILL.md 长度预算、占位符闭合（【】/[]/{{}}）、密钥扫描。零依赖，`python tools/lint_skills.py` 全绿通过 |
| `tools/trigger-cases.md` | 22 条触发与路由回归用例的人类可读视图，改版前后对照 |
| `evals/cases.json` | 同一批用例的机器可读源，promptfoo 从这里生成测试 |
| `evals/check_cases.py` | 校验 cases.json 与 trigger-cases.md 一致，并确认预期 SOP 路径真实存在 |
| `evals/promptfooconfig.yaml` | 触发回归：断言每条提示命中的技能名与 SOP 路径 |
| `evals/promptfooconfig.quality.yaml` | 文本质量抽检：真实读 SOP 原文生成提示词，模型按硬规则评分（图片输出仍人工看） |

## 评测与 CI

触发回归的主判据是「技能选得对不对」，因为技能选错是用户最先感知的问题。CI 分三层：

1. **静态检查**（每次 push / PR）：`tools/lint_skills.py` + `evals/check_cases.py` + promptfoo 配置结构校验。无需密钥。
2. **触发回归**（每次 push / PR）：promptfoo 跑 22 条提示，断言返回的技能名和 SOP 路径。提示词从三个 `SKILL.md` 实时读取，路由表改了评测输入立刻跟着变。
3. **文本质量抽检**（每周一 + 手动触发）：读取指定 SOP 原文生成提示词，用 `llm-rubric` 按该 SOP 的硬规则评分。图片输出不自动评分，仍人工看。

模型通过标准 OpenAI 兼容环境变量接入，密钥不写进仓库或评测配置：

| 名称 | 类型 | 说明 |
|---|---|---|
| `EVAL_API_KEY` 或 `OPENAI_API_KEY` | Secret | 必填。未配置时触发回归任务直接失败并给出提示，不会出现「没跑测试却全绿」 |
| `EVAL_BASE_URL` | Variable | 可选，兼容 OpenAI 协议的第三方端点 |
| `EVAL_MODEL` | Variable | 可选，默认 `gpt-4o-mini` |
| `EVAL_JUDGE_MODEL` | Variable | 可选，质量抽检的评分模型，默认同 `EVAL_MODEL` |

本地跑法：

```bash
python tools/lint_skills.py
python evals/check_cases.py
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.yaml
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.quality.yaml
```

`evals/README.md` 记录了为什么选 promptfoo、以及 skill-up 的评估结论。

## 安装

把想要的技能目录整体拷入本地技能目录即可，路径形如 `<技能目录>/<技能名>/SKILL.md`：

- ZCode：`~/.agents/skills/<技能名>/`（或项目级 `<项目>/.agents/skills/<技能名>/`）
- Claude Code：`~/.claude/skills/<技能名>/`

以 `ecom-prompt-sop` 为例：

```bash
git clone https://github.com/ADC1920/ecom-prompt-sop.git ecom-prompt-sop-repo
cp -r ecom-prompt-sop-repo/ecom-prompt-sop ~/.agents/skills/
```

新开会话后技能自动被发现；触发方式为自然语言命中（如「给这件卫衣出详情页提示词」「把这批 3:4 主图转 1:1」）。

## 与本地技能目录的同步

本地在用副本位于 `C:\Users\ADC\.agents\skills\`，本仓库是其存档镜像。技能更新后，把对应技能目录重新拷入本仓库并提交推送：

```bash
cp -r ~/.agents/skills/ecom-prompt-sop .
git add ecom-prompt-sop && git commit -m "feat(ecom-prompt-sop): 更新说明" && git push
```

仓库根目录与本地技能目录为单向同步（本地 → 仓库），不要在仓库内直接改技能再拷回。
