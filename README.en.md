# Ecom-Prompt-Studio

Prompt engineering for e-commerce visuals: turning "how to write a prompt" into a searchable, checkable, regression-tested production process.

Models can already write prompts. What's missing is three things — **criteria, examples, feedback** — and this repo is built around exactly those:

- **Criteria**: 34 SOPs decomposed into 197 prompt templates, 571 rule clauses, 22 checklists, and 122 placeholders. Every rule carries a stable ID so it can be cited and traced on its own.
- **Examples**: a positive-sample corpus, retrieved by similarity, so you can borrow wording that has already produced good images.
- **Feedback**: platform machine checks after generation. What fails doesn't ship; the checks themselves are guarded by failure fixtures so they can't be quietly relaxed.

Each directory under `skills/` is a complete skill: copy it into your local skills directory and it works. `tools/` holds the companion toolchain, runnable from any agent platform or a plain terminal.

## Quick start

### Option 1: just the prompts

No Python, no agent needed. Browse [`skills/ecom-prompt-sop/references/_atoms/`](skills/ecom-prompt-sop/references/_atoms/). Each of the 34 atoms is one JSON file — `source_text` holds the full original text, `templates` holds copy-ready prompt templates.

### Option 2: install as skills

```bash
git clone https://github.com/ADC1920/Ecom-Prompt-Studio.git

# Install all three: they hand off to each other, so a missing one breaks the routing
cp -r Ecom-Prompt-Studio/skills/* ~/.agents/skills/     # ZCode
cp -r Ecom-Prompt-Studio/skills/* ~/.claude/skills/     # Claude Code
```

Or use the installer — the `skills/<name>/SKILL.md` layout matches what vercel-labs/skills scans:

```bash
npx skills add ADC1920/Ecom-Prompt-Studio --all
```

Skills trigger on natural language after a session restart — no need to say "SOP":

| Studio | Example request |
|---|---|
| Main image | "give me a main-image prompt set for this hoodie" |
| Detail page | "detail-page prompts for this thermos" |
| SKU batch | "batch SKU images for a 5-piece set" / "convert these 3:4 images to 1:1" |
| Model & video | "three poses for the model swap" / "a video prompt for this product" |
| Reverse engineering | "reverse this competitor image into our prompt" / "break down this video's shots" |

### Option 3: skills + tooling

Keep the whole repo locally on top of Option 2; the scripts under `tools/` run directly:

```bash
python tools/cli.py query-atom --category 杯壶 --output 主图        # locate atoms, returns IDs + rationale
python tools/cli.py get-template --atom a21                        # fetch that atom's templates, rules, checklists
python tools/cli.py find-rule --query 白底                          # search rules by keyword or ID
python tools/cli.py validate-prompt --file p.txt --platform amazon # anti-slop and compliance self-check
python tools/cli.py check-output out/main-01.png --platform amazon # platform machine check on a generated image
```

When only the skill directories are copied without `tools/`, the scripts mentioned in SKILL.md can be done by hand against the checklists given there — every reference site states the fallback.

## Three skills

| Skill | Takes |
|---|---|
| `ecom-prompt-sop` | Five-studio SOP atom library: main image, detail page, SKU batch, model & video, reverse engineering — plus category-specific rules and the criteria rule set |
| `ecom-main-image-prompts` | Main-image director: takes bare main-image requests with no category cue, plans the whole set along the buyer decision path |
| `ecom-detail-page-prompts` | Detail-page director: takes bare detail-page requests, plans page structure and per-page prompts by category |

The only routing rule: **category, action, or scenario cue present → SOP atom library; bare main image or bare detail page → hand off to the director skill.** This rule lives in `skills/ecom-prompt-sop/SKILL.md` and the eval suite watches it. The three skills hand off to each other, so install all three or none.

## Five studios

The SOP library is organized into five stations. Pick the station first, then locate the single matching atom:

| Studio | Takes | Produces | Gate |
|---|---|---|---|
| **AI main image** | full sets, single images, buyer shows, scene shots, white-background shots | main-image plan + per-image prompts + compliance check | retention list reused per image · claims evidenced · first-image spec verified · boundary sentence present |
| **AI detail page** | full sets, long pages, per-screen planning | page plan + per-page prompts | lock before design · no repeated themes · anti-template self-check |
| **SKU batch & cross-platform** | multi-color/multi-piece batches, product swaps, 3:4 → 1:1, in-image text translation | SKU variant plan + per-image prompts + spec conversion | variant attribution stated · only count/color/layout changed · no cropping after conversion · text translated not rewritten |
| **Model & video** | model swaps, multi-pose sets, e-commerce video generation | model series or video prompts with a timeline | faces don't drift · garment style consistent · face-exposure rules followed · video has a timeline |
| **Image reverse engineering** | competitor images and videos, legacy image refreshes, SKU layout replication | teardown table + rewritten prompts + do-not-inherit list | brand names replaced · product traits not inherited · own product assets reused · video must produce a shot list |

Station priority runs top-down: reverse engineering / refresh → reverse-engineering studio; batch variants → SKU studio; live model or video → model & video studio; deliverable is a detail page → detail-page studio; everything else → main-image studio. Buyer shows are named "batch" but are one product in one scene, so they stay in the main-image studio.

Mixed documents (category-specific, general-purpose, multi-SKU) are shared across two studios — used whole, pointed at from both places, never split or duplicated, so the same prompt never exists in two versions.

## Why atoms

SOP content mixes five things: explanation, prompt templates, rule clauses, checklists, and placeholders. Dropped into context raw, the model has to pick them out of prose.

`tools/atomize.py` separates them, and keeps the full original text in the atom (`source_text`), so one file is enough:

| Field | Content | Use |
|---|---|---|
| `templates` | prompt templates, both fenced-code and bare-paragraph, with line numbers | take `text` and feed it directly |
| `rules` | rule clauses from the body, with stable IDs and line numbers | self-check compliance, cite by ID |
| `checklists` | acceptance checklists and section requirements | go through before delivery |
| `placeholders` | placeholders to replace | prevent outputting them verbatim |
| `source_text` | full original text | read when context or examples are needed |

Totals: **197 templates · 571 rules · 22 checklists · 122 placeholders (deduplicated)**, all retrievable by ID.

```bash
python tools/atomize.py check     # self-containment: source_text, templates, rules, checklists agree
python tools/atomize.py merge     # rebuild atoms, indexes and the rule index after editing the semantic layer
python tools/atomize.py restore   # export readable text from atom contents
```

### Rules carry stable IDs

Each rule looks like `a21.re5d4b02d34f3`: atom number plus a text fingerprint. Line numbers are **deliberately avoided** — any insertion above shifts them, breaking every document and eval that cites them. Change the text and the ID changes, which is the intent: a rewritten rule is a different rule.

`atomize.py check` does two things: recompute the ID and compare it against the record, and confirm the rule text actually appears in `source_text`. The latter guards against editing an atom's `rules` field while bypassing `merge` — that would leave the atom and the source text out of sync.

The rule index lives at `references/_atoms/rules.json` and holds locator fields only (ID → atom / studio / category). Full rule text stays in the atoms alone, avoiding two copies that can drift.

## Output contracts

`skills/ecom-prompt-sop/references/_output-contracts.md` specifies, for each of the five studios, **which sections a deliverable must contain**: a 7-column main-image plan, 5 sections per image prompt, a 6-column detail-page plan, 5 columns per SKU variant, and so on.

Templates determine content; contracts determine structure. A missing section means unfinished, not "simplified".

## Toolchain

Not a pile of loose scripts — a chain:

```
decompose ──→ assemble ──→ self-check ──→ machine check ──→ audit ──→ stats
atomize      compose        slop           check_image      visual     fix_stats
             _prompt        _check                          _audit
```

| Tool | What it does |
|---|---|
| `tools/cli.py` | single entry point: `query-atom` locates atoms, `get-template` fetches templates, `find-rule` searches rules, `validate-prompt` validates, `check-output` machine-checks |
| `tools/atomize.py` | decomposition and self-containment checks: stable rule IDs, rule index generation, recompute verification |
| `tools/compose_prompt.py` | five-slot assembly: fidelity → scene → subject → details → use case → constraints, adds platform constraints and runs required-field checks |
| `tools/slop_check.py` | pre-final check for SD-era filler words, absolutes, fake promotions, efficacy claims, AI tells |
| `tools/rules_engine.py` | validates slots against platform, category, and scenario rule files; `--inject` adds default constraints |
| `tools/check_image.py` | platform machine check after generation: white background, subject occupancy, ratio, resolution, file size, alpha channel, in-image text |
| `tools/gen_fixtures.py` | negative fixtures: builds deliberately non-compliant images and asserts the checker still flags them, so rules can't be quietly relaxed |
| `tools/visual_audit.py` | consistency (perceptual hash + color histogram) and AI-feel heuristics — hints only, never a verdict |
| `tools/vlm_review.py` | generates a structured human review sheet; conclusions are always human |
| `tools/fix_stats.py` | repair-sentence effectiveness computed from manifests |
| `tools/corpus.py` | positive-sample corpus: add, similarity search, compile few-shot blocks |
| `tools/lint_skills.py` | full static check, the first CI gate |

Everything is stdlib except `check_image.py`, `visual_audit.py`, and `vlm_review.py` (Pillow). Scripts with `--selftest` verify offline, no keys or network.

## Criteria rules and corpus

The SOPs give the "how". These give the "what counts":

- `references/_rules/`: three JSON files — platforms (12), categories (9), scenarios (11) — turning hard criteria into checkable rules: white-background and occupancy thresholds, prohibited claims, required slots, forbidden visual elements, AI disclosure duties
- `references/_rules/aigc-disclosure.json`: AIGC disclosure duties and legal basis across five jurisdictions (FTC, California SB 942, New York SB 8420-A, EU AI Act Art.50, China's labelling rules), with four image-type classes and four red lines
- `references/_brand-lock.md`: ten brand-lock fields and the prepend pattern, solving cross-image drift
- `references/_corpus/`: prompts verified to have produced good images, retrieved by similarity and compiled into few-shot blocks

Rules govern "what not to write"; the corpus governs "what good looks like"; the brand lock governs "does the set look like one brand".

## Generation boundary

> **Authorization before generation (hard rule)**: before invoking any image-generation model (Qwen-Image family, wan, Seedream, Gemini, GPT-Image, FLUX, z-image, etc., including tool calls and web UIs driven on the user's behalf), obtain explicit authorization stating the purpose, model, and image count. Without authorization, deliver prompt text only.

The repo deliberately ships no command-line generation channel: prompts are fed as content, never model-rewritten, so hard rules aren't diluted; machine checks and visual audits validate output from any channel after the fact. Image-to-image is used for product locking and refresh: a real photo serves as reference, and the prompt states what to keep and what to change.

## Evaluation and CI

Picking the wrong skill is the most visible failure mode, so routing regression is the main line. CI runs three layers:

1. **Static checks** (every push / PR): `lint_skills.py` + `check_cases.py` + `atomize.py check` + machine-check failure fixtures + twelve script self-tests + promptfoo config validation — no keys needed
2. **Routing regression** (every push / PR): promptfoo runs 34 prompts and asserts the matched skill name and **atom ID**; eval input reads the three `SKILL.md` files directly, so a routing-table edit takes effect immediately
3. **Text quality sampling** (weekly + manual): generates prompts by atom ID from `source_text` and scores them with `llm-rubric` against that SOP's hard rules

Beyond the three layers there's **real trigger evaluation** (`evals/real_trigger.py`), run manually at milestones: hand the skills to a real engine and see whether it loads them unprompted and reaches the right atom. The first two layers can't catch "installed but never triggered"; this one can, at the cost of being slow and potentially billable.

The case set has 34 entries including 4 English inputs — all three skills declare `English keywords` in their description, and these cases verify it actually works. There are also 7 **machine-check failure fixtures**: deliberately non-compliant images (grey background, undersized subject, low resolution, wrong aspect ratio) with assertions that the checker flags them, plus reverse controls confirming it doesn't over-flag. The fixture expectations are the acceptance criteria — when adding a platform rule, add the fixture first, change the checker second. Reversed order means treating the implementation as the spec.

Each skill ships an `EVAL.md` answer key; `lint_skills.py` verifies it exists and is not referenced by `SKILL.md` — so the agent under evaluation can't read the answers. The eval model goes through DeepSeek's official provider with the key stored as a repo secret and never written to any file; when absent, routing regression fails loudly instead of quietly passing.

```bash
python tools/lint_skills.py
python evals/check_cases.py
python tools/gen_fixtures.py --verify                          # machine-check failure fixtures
python evals/real_trigger.py --dry-run                         # preview which cases a real run would use
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.yaml
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.quality.yaml   # needs a key
```

Requires Node.js 22+. Selection rationale and real score baselines are in [`evals/README.md`](evals/README.md).

## Repository layout

```text
.
├─ skills/
│  ├─ ecom-prompt-sop/
│  │  ├─ SKILL.md                   # five-studio entry: pick studio → locate atom → take templates and rules
│  │  ├─ EVAL.md                    # eval answer key (for graders, not referenced by SKILL.md)
│  │  └─ references/
│  │     ├─ _atoms/                 # 34 atoms + document index + rule index
│  │     ├─ _rules/                 # platform / category / scenario criteria + AIGC disclosure duties
│  │     ├─ _corpus/                # positive-sample corpus
│  │     ├─ _brand-lock.md          # ten brand-lock fields
│  │     ├─ _output-contracts.md    # required sections per studio deliverable
│  │     └─ _prompt-slots.md        # five-slot spec
│  ├─ ecom-main-image-prompts/      # main-image director skill
│  └─ ecom-detail-page-prompts/     # detail-page director skill
├─ tools/                           # unified CLI, decompose, assemble, machine-check, fixtures, audit, stats
├─ evals/                           # promptfoo configs, 34 cases, real trigger eval
├─ CHANGELOG.md
├─ README.en.md
└─ .github/workflows/skill-eval.yml # CI (static / routing regression / quality sampling)
```

## Known limitations

- **The corpus has only 2 seeds**: retrieval quality depends on sample size and must come from real generations — it can't be fabricated. Usable today, not yet accurate.
- **AI-feel thresholds are empirical**: `visual_audit.py`'s saturation, smoothness, dead-white and edge-density criteria haven't been calibrated against batches of real good images vs AI images. Treat as hints, not verdicts.
- **VLM review doesn't judge images**: `vlm_review.py` only generates a review sheet; VLMs are unreliable on fine-grained questions like "are the retention constraints satisfied", so scores are not pass criteria.
- **OCR needs local tesseract**: missing dependencies yield `skipped`, never a fake pass; CI doesn't have it installed, so in-image text isn't checked in the cloud.
- **Template extraction has minor noise**: documents without fenced code blocks go through bare-paragraph rules, so a few fragments may be broad and haven't been manually reviewed line by line.
- **Real trigger evaluation needs your own engine**: `evals/real_trigger.py` provides only the framework and judging logic; engine command and credentials come from the user.
