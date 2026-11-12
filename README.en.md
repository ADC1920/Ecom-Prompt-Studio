# Ecom-Prompt-Studio

Prompt engineering for e-commerce visuals: turning "how to write a prompt" into a searchable, checkable, regression-tested production process.

Models can already write prompts. What's missing is three things — **criteria, examples, feedback** — and this repo is built around exactly those:

- **Criteria**: the whole SOP decomposed into 197 prompt templates, 571 rule clauses, 181 checklist items, and 122 placeholders. Every one is machine-readable.
- **Examples**: a positive-sample corpus, retrieved by similarity, so you can borrow wording that has already produced good images.
- **Feedback**: platform machine checks after generation. What fails doesn't ship; the fix sentence goes back into the prompt and the loop runs again.

Each subdirectory is a complete skill: copy it into your local skills directory and it works.

## Quick start

### As a ZCode plugin (recommended)

The repo root is a plugin. Add the repo directory as a local marketplace, then install:

```bash
git clone https://github.com/ADC1920/Ecom-Prompt-Studio.git
```

In ZCode: **Plugin Marketplace → Add → Add Plugin Marketplace**, paste the cloned directory, then install `ecom-prompt-studio` from **Personal**.

This installs all three skills, four slash commands, the post-generation check hook, and the MCP server in one step.

### As plain skills

```bash
cp -r Ecom-Prompt-Studio/ecom-prompt-sop ~/.agents/skills/
cp -r Ecom-Prompt-Studio/ecom-main-image-prompts ~/.agents/skills/
cp -r Ecom-Prompt-Studio/ecom-detail-page-prompts ~/.agents/skills/
```

Note: copying only a skill directory ships the SOP text but not `tools/`. For machine checks and the MCP server, use the plugin install.

## The five studios

The SOP library is organized by studio. Decide the studio first, then locate exactly one atom.

| Studio | Takes | Produces | Gate |
|---|---|---|---|
| **Main image** | full main-image set, single main image, buyer show, scene shot, white background | main-image plan + per-shot prompts + compliance check | retention list reused in every shot｜claims sourced｜first-image rules verified｜output boundary sentence |
| **Detail page** | full detail page set, long image, page-by-page planning | page plan + per-page prompts | product lock before design｜adjacent pages differ｜anti-templating self-check |
| **SKU batch & cross-platform** | multi-color/multi-pack batches, multi-product swaps, 3:4 to 1:1, in-image text translation | variant plan + per-image prompts + conversion results | variant ownership stated｜only count/color/layout change｜no cropping after conversion｜text translated not rewritten |
| **Model & video** | model head/clothing swaps, multi-pose shots, e-commerce video generation | model set or video prompts with timeline shots | faces don't drift｜garment stays consistent｜face-exposure rules met｜video has a timeline |
| **Reverse engineering** | competitor images and videos, old-image refresh, SKU layout replication | breakdown table + replaced prompts + do-not-inherit list | brand names replaced｜product traits not inherited｜own product locked｜video always gets a storyboard |

Studio priority: reverse/refresh → reverse studio; batch variants → SKU studio; real people or video → model studio; detail-page output → detail studio; everything else → main-image studio. Buyer shows stay in the main-image studio despite the word "batch".

## Three skills

| Skill | Takes | Size |
|---|---|---|
| `ecom-prompt-sop` | five-studio SOP atom library: main image, detail page, SKU batch, model & video, reverse engineering | 1 `SKILL.md` + atom library |
| `ecom-main-image-prompts` | main-image director: bare main-image requests with no category cue, plans the whole set around the buyer decision path | 1 `SKILL.md` + 2 reference files |
| `ecom-detail-page-prompts` | detail-page director: bare detail-page requests with no category cue, plans page structure and per-page prompts by category | 1 `SKILL.md` + 1 reference file |

The only routing rule: **category, action, or scenario cue present → SOP atom library; bare main image or bare detail page → hand off to the director skill.** This rule lives in `ecom-prompt-sop/SKILL.md` and the eval suite watches it.

## Tooling

| Script | What it does |
|---|---|
| `tools/atomize.py` | decompose SOPs into atoms, keep them self-contained, export readable text |
| `tools/compose_prompt.py` | five-slot prompt assembly, adds platform constraints and checks required fields |
| `tools/slop_check.py` | catches SD-era filler words, absolute claims, fake promotions, efficacy claims, AI tells |
| `tools/rules_engine.py` | validates slots against platform, category, and scenario rule files |
| `tools/check_image.py` | platform machine check after generation: white background, subject occupancy, ratio, resolution, file size, alpha channel, in-image text |
| `tools/visual_audit.py` | consistency and AI-feel heuristics — hints only, never a verdict |
| `tools/vlm_review.py` | generates a structured human review sheet; conclusions are always human |
| `tools/fix_stats.py` | repair-sentence effectiveness from manifests |
| `tools/corpus.py` | positive-sample corpus: add, similarity search, compile few-shot blocks |
| `tools/lint_skills.py` | full static check, the first CI gate |
| `tools/mcp_server.py` | MCP server exposing the atom library and checks as four tools |

Machine checks run against images from **any** channel. This repo deliberately does not bundle an image-generation CLI: bring your own endpoint, then verify the output here.

## MCP tools

| Tool | Input | Output |
|---|---|---|
| `query_atom` | category, output, action | matching atom ids with evidence |
| `get_template` | atom id, optional index | template text plus that atom's rules, checklists, placeholders |
| `validate_prompt` | prompt, optional platform/scenario/category | slop check and rule-engine results |
| `check_output` | image path, platform | platform machine-check results |

## Evals and CI

- `evals/cases.json` — 30 routing cases covering out-of-scope, prompt injection, and same-family disambiguation
- `evals/router.js` — builds the routing prompt from the three live `SKILL.md` files
- `evals/check_cases.py` — keeps the machine-readable cases and the human-readable view in sync
- `.github/workflows/skill-eval.yml` — static checks, eight script self-tests, routing regression on push/PR, weekly quality sampling

Routing regression feeds only the descriptions and routing table to a model and asserts the returned skill and atom. It catches "wrong skill" and "wrong atom" regressions; it does not judge prompt quality — that's what the quality sampling is for.

## License

MIT
