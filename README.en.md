# Ecom-Prompt-Studio

Prompt engineering for e-commerce visuals: turning "how to write a prompt" into a searchable, checkable, regression-tested production process.

Models can already write prompts. What's missing is three things — **criteria, examples, feedback** — and this repo is built around exactly those:

- **Criteria**: the whole SOP decomposed into 197 prompt templates, 571 rule clauses, 181 checklist items, and 122 placeholders. Every one is machine-readable.
- **Examples**: a positive-sample corpus, retrieved by similarity, so you can borrow wording that has already produced good images.
- **Feedback**: platform machine checks after generation. What fails doesn't ship; the fix sentence goes back into the prompt and the loop runs again.

Each directory under `skills/` is a complete skill: copy it into your local skills directory and it works. `tools/` holds the companion atom search, rule checks, and post-generation image checks — runnable from any agent platform or a plain terminal.

## Quick start

### Option 1: just the prompts (no skill install)

No Python, no agent needed: browse [`skills/ecom-prompt-sop/references/_atoms/`](skills/ecom-prompt-sop/references/_atoms/). Each of the 34 atoms is one JSON file — `source_text` holds the full original text, `templates` holds copy-ready prompt templates.

### Option 2: install as skills (ZCode / Claude Code / Cursor, etc.)

```bash
git clone https://github.com/ADC1920/Ecom-Prompt-Studio.git

# Install all three: they hand off to each other, so a missing one breaks the routing
cp -r Ecom-Prompt-Studio/skills/* ~/.agents/skills/     # ZCode
cp -r Ecom-Prompt-Studio/skills/* ~/.claude/skills/     # Claude Code
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
python tools/cli.py validate-prompt --file p.txt --platform amazon # anti-slop and compliance self-check
python tools/cli.py check-output out/main-01.png --platform amazon # platform machine check on a generated image
```

The remaining scripts (atom decomposition, rule engine, corpus search, visual audit) are listed under [Toolchain](#toolchain). When only the skill directories are copied without `tools/`, the scripts mentioned in SKILL.md can be done by hand against the checklists given there.

## Three skills

| Skill | Takes |
|---|---|
| `ecom-prompt-sop` | five-studio SOP atom library: main image, detail page, SKU batch, model & video, reverse engineering, with category specials and criteria rule files |
| `ecom-main-image-prompts` | main-image director: bare main-image requests with no category cue, plans the whole set around the buyer decision path |
| `ecom-detail-page-prompts` | detail-page director: bare detail-page requests with no category cue, plans page structure and per-page prompts by category |

The only routing rule: **category, action, or scenario cue present → SOP atom library; bare main image or bare detail page → hand off to the director skill.** This rule lives in `skills/ecom-prompt-sop/SKILL.md` and the eval suite watches it. The three skills hand off to each other, so install all three or none.

## The five studios

The SOP library is organized by studio. Decide the studio first, then locate exactly one atom:

| Studio | Takes | Produces | Gate |
|---|---|---|---|
| **Main image** | full main-image set, single main image, buyer show, scene shot, white background | main-image plan + per-shot prompts + compliance check | retention list reused in every shot｜claims sourced｜first-image rules verified｜output boundary sentence |
| **Detail page** | full detail page set, long image, page-by-page planning | page plan + per-page prompts | product lock before design｜adjacent pages differ｜anti-templating self-check |
| **SKU batch & cross-platform** | multi-color/multi-pack batches, multi-product swaps, 3:4 to 1:1, in-image text translation | variant plan + per-image prompts + conversion results | variant ownership stated｜only count/color/layout change｜no cropping after conversion｜text translated not rewritten |
| **Model & video** | model head/clothing swaps, multi-pose shots, e-commerce video generation | model set or video prompts with timeline shots | faces don't drift｜garment stays consistent｜face-exposure rules met｜video has a timeline |
| **Reverse engineering** | competitor images and videos, old-image refresh, SKU layout replication | breakdown table + replaced prompts + do-not-inherit list | brand names replaced｜product traits not inherited｜own product locked｜video always gets a storyboard |

Studio priority: reverse/refresh → reverse studio; batch variants → SKU studio; real people or video → model & video studio; detail-page output → detail studio; everything else → main-image studio. Buyer shows stay in the main-image studio despite the word "batch".

Mixed entries (category specials, the general outline, multi-SKU) are attached to two studios at once — shared in full, pointed at from both places, never split or duplicated. Revisions flow back by "what changed → which studio → what downstream work to redo".

## Why atoms

SOP content mixes five kinds of things: explanations, prompt templates, rule clauses, checklists, placeholders. Feeding it all into context means the model picks its way through prose.

`tools/atomize.py` splits them apart, keeping the full text inside each atom (`source_text`), so one file is enough:

| Field | Content | Use |
|---|---|---|
| `templates` | prompt templates, fenced and bare-paragraph, with line numbers | take `text` and feed it directly |
| `rules` | rule clauses from the prose, with line numbers | self-check before delivery |
| `checklists` | acceptance checklists, required sections | walk through one by one before delivery |
| `placeholders` | placeholders to replace | make sure none is echoed verbatim |
| `source_text` | full original text | read when context or examples are needed |

The ledger: **197 templates · 571 rule clauses · 181 checklist items · 122 placeholders**, all retrievable by id.

```bash
python tools/atomize.py check     # self-containment check: source_text, templates, rules, checklists
python tools/atomize.py merge     # rebuild atoms and indexes after editing semantic.json
python tools/atomize.py restore   # export readable text from atom source_text
```

## Tooling

Not a pile of loose scripts — a chain:

```
decompose ──→ assemble ──→ precheck ──→ machine ──→ visual ──→ stats
atomize     compose     slop        check      visual    fix_stats
            prompt      _check     _image     _audit
```

| Script | What it does |
|---|---|
| `tools/atomize.py` | decompose SOPs into self-contained atoms, with export |
| `tools/compose_prompt.py` | five-slot assembly: fidelity → scene → subject → details → purpose → constraints, adds platform constraints and checks required fields |
| `tools/slop_check.py` | catches SD-era filler words, absolute claims, fake promotions, efficacy claims, AI tells before finalizing |
| `tools/rules_engine.py` | validates slots against platform, category, and scenario rule files; `--inject` adds default constraints |
| `tools/check_image.py` | platform machine check after generation: white background, subject occupancy, ratio, resolution, file size, alpha channel, in-image text |
| `tools/visual_audit.py` | consistency (perceptual hash + color histogram) and AI-feel heuristics — hints only, never a verdict |
| `tools/vlm_review.py` | generates a structured human review sheet; conclusions are always human |
| `tools/fix_stats.py` | repair-sentence effectiveness computed from manifests |
| `tools/corpus.py` | positive-sample corpus: add, similarity search, compile few-shot blocks |
| `tools/cli.py` | single entry point: `query-atom` locates atoms, `get-template` fetches templates, `validate-prompt` validates, `check-output` machine-checks |
| `tools/lint_skills.py` | full static check, the first CI gate |

Everything is stdlib except `check_image.py`, `visual_audit.py`, and `vlm_review.py` (Pillow). Scripts with `--selftest` verify offline, no keys or network.

## Criteria rules and corpus

The SOP gives the method; these give the criteria and the examples:

- `references/_rules/`: three JSON files — platform (12), category (9), scenario (11) — turning hard criteria into checkable rules: white-background and occupancy thresholds, banned claims, required slots, forbidden visuals, AI disclosure duties
- `references/_rules/aigc-disclosure.json`: AIGC disclosure duties with legal grounds across FTC, California SB 942, New York SB 8420-A, EU AI Act Art. 50, and China's labeling measures, with a four-way image taxonomy and four red lines
- `references/_brand-lock.md`: ten must-lock visual fields and the prepend pattern, against cross-image drift
- `references/_corpus/`: prompts verified to have produced good images, retrieved by similarity and compiled into few-shot blocks

Rules say what you cannot write; the corpus says what good looks like; the brand lock says whether a set of images reads as one store.

## Image generation boundary

> **Authorization before generation (hard rule)**: before invoking any image-generation model (Qwen-Image family, wan, Seedream, Gemini, GPT-Image, FLUX, z-image, etc., including tool calls and web UIs driven on the user's behalf), obtain explicit authorization stating the purpose, model, and image count. Without authorization, deliver prompt text only.

This repo deliberately ships no image-generation CLI: prompts are fed as written, never rewritten by a model, so hard rules stay intact. Machine checks and visual audits verify output from any channel. Image-to-image is used for product locking and refresh: the real photo is the reference image, with keep/change lists stated in the prompt.

## Evals and CI

Skill mis-routing is the most user-visible failure, so routing regression is the eval backbone. Three CI layers:

1. **Static checks** (every push / PR): `lint_skills.py` + `check_cases.py` + `atomize.py check` + script self-tests + promptfoo config validation — no keys needed
2. **Routing regression** (every push / PR): promptfoo runs 30 prompts, asserting the hit skill name and **atom id**; eval inputs read the three live `SKILL.md` files, so routing changes take effect immediately
3. **Quality sampling** (weekly Monday + manual): generates prompts from atom `source_text` and scores them with `llm-rubric` against that SOP's hard rules

Beyond the three layers, **real trigger evaluation** (`evals/real_trigger.py`) runs manually at milestones: hands the skills to a real engine and watches whether it loads them unprompted and lands on the right atom. The first two layers cannot catch "installed but never triggers"; this one can, at the cost of being slow and possibly billed.

Each skill ships an `EVAL.md` answer key; `lint_skills.py` verifies it exists and is not referenced from `SKILL.md` — the agent under evaluation must not read the answers. The eval model connects through the official DeepSeek provider with the key in a repo Secret, never in files. Without the secret, routing regression fails explicitly — no "all green because nothing ran".

```bash
python tools/lint_skills.py
python evals/check_cases.py
python evals/real_trigger.py --dry-run                        # list what the real eval would run
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.yaml
npx promptfoo@0.124.1 eval -c evals/promptfooconfig.quality.yaml   # needs the API key
```

Requires Node.js 22+. Rationale and real baseline scores: [`evals/README.md`](evals/README.md).

## Repository layout

```text
.
├─ skills/
│  ├─ ecom-prompt-sop/
│  │  ├─ SKILL.md                   # five-studio entry: pick studio → locate atom → take templates and rules
│  │  ├─ EVAL.md                    # eval answer key (for graders, not referenced by SKILL.md)
│  │  └─ references/
│  │     ├─ _atoms/                 # 34 atoms + indexes
│  │     ├─ _rules/                 # platform / category / scenario criteria + AIGC disclosure duties
│  │     ├─ _corpus/                # positive-sample corpus
│  │     ├─ _brand-lock.md          # ten brand-lock fields
│  │     └─ _prompt-slots.md        # five-slot spec
│  ├─ ecom-main-image-prompts/      # main-image director skill
│  └─ ecom-detail-page-prompts/     # detail-page director skill
├─ tools/                           # unified CLI, decompose, assemble, machine-check, audit, stats
├─ evals/                           # promptfoo configs, cases, real trigger eval
├─ CHANGELOG.md
├─ README.en.md
└─ .github/workflows/skill-eval.yml # CI (static / routing regression / quality sampling)
```

## Known limitations

- **AI-feel thresholds are experience values**: `visual_audit.py`'s saturation, smoothness, dead-white, and edge-density heuristics are not calibrated against real good/AI image batches yet — treat them as hints, not verdicts
- **Corpus has 2 seed entries**: retrieval quality depends on sample size, which can only grow from real generations, never fabricated — "usable but not sharp" for now
- **VLM review never auto-judges**: `vlm_review.py` only produces a review sheet; VLMs are unreliable on fine-grained "was the retention constraint met" questions, so scores are never used as a pass
- **OCR needs local tesseract**: missing dependencies become `skipped`, not a false pass; CI has no tesseract, so in-image text is not checked in the cloud
- **Template extraction has some noise**: entries without fenced code blocks use the bare-paragraph rule; a few fragments may over-match, not yet reviewed per entry
- **Real trigger eval brings your own engine**: `evals/real_trigger.py` provides framework and verdicts only; engine command and credentials are the runner's

## License

MIT
