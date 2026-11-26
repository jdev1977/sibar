# Tasks: Default-output baselines across project types

This file breaks [plan.md](plan.md) into tasks, and names the Claude model that should carry out each one. Task IDs follow the plan's phases.

## Who runs what

The models below are the **workers** that build and analyse. They are separate from the **models under test**, which are every provider's models fixed in T0.2. A worker model can also be a model under test; where that creates a bias risk, the task says so.

| Worker | Model ID | Price per 1M tokens (in / out) | Use it for | Default effort |
|---|---|---|---|---|
| **Fable 5.2** | `claude-fable-5-2` | $8 / $40 | Method design, where a wrong choice spoils every later result: metrics, rubrics, scoring design, reference answers, the findings report | `high` |
| **Opus 5.5** | `claude-opus-5-5` | $4 / $20 | Most of the building: the runner, the sandbox, extractors that need judgment, scoring code, prompt sets, code review | `high` (`xhigh` for the sandbox and runner) |
| **Sonnet 5.5** | `claude-sonnet-5-5` | $2 / $10 | Routine code and documents: rendering, simple extractors, packaging, the viewer, reports drafted from tables | `medium` |
| **Haiku 5.5** | `claude-haiku-5-5` | $0.10 / $0.50 | High-volume, low-judgment passes: bulk rubric tagging if it passes calibration (T2.5), sorting and labelling files | `low` |
| **Human** | | | API keys, spend approvals, review of fingerprints, pairwise judgments, hand-typed product-surface runs, publishing decisions | |
| **Script** | | | Runs that need no model to drive them, such as the generation runs themselves | |

Prices and IDs are as of 2026-11-25. T0.2 rechecks them before any spend.

**Rules that apply to every task**

- **This repository is public.** No API keys, tokens, `.env` files, personal details or private-catalogue text are committed. Keys are read from environment variables only. Generated outputs stay out of git until T6.3 clears provider terms.
- Each model in this file is the cheapest one expected to do the task well. Move a task up one tier if its "done when" check fails twice; move it down only after a measured comparison.
- Code written by one session is reviewed by a different session (X2) before a run that spends money.

## Cross-cutting

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| X1 | Secret hygiene: `.gitignore` for keys, `.env`, raw outputs and private notes; pre-commit secret scan (for example gitleaks); `.env.example` with names only | Sonnet 5.5 | none | A test commit containing a fake key is blocked |
| X2 | Review gate: independent code review of the runner, sandbox, tagger and scoring function before their first paid run | Opus 5.5 | each reviewed task | Findings fixed or accepted in writing |
| X3 | Cost ledger: each run appends tokens and cost by model to a local file; a hard budget cap stops a run | Sonnet 5.5 | T0.5 | A run stops at a deliberately low cap |

## Phase 0: Setup

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T0.1 | Repository layout: `prompts/`, `runner/`, `extractors/`, `rubrics/`, `data/` (gitignored), `viewer/`, `docs/` | Sonnet 5.5 | X1 | Layout committed with a README |
| T0.2 | Fix the list of models under test from each provider's current documentation: main and small model per provider, exact IDs, prices, default settings, retirement dates | Sonnet 5.5 | none | `models.yaml` lists every model with a source link and date checked; Human confirms |
| T0.3 | Provider access: decide direct APIs versus one multi-provider gateway; set up keys | Human | T0.2 | Each provider answers a test call from the local machine |
| T0.4 | Run record format: JSON Lines schema for prompt, level, wording, model ID, surface, settings, date, tokens, raw response, file list, extractor versions; with a validator | Opus 5.5 | T0.1 | Validator accepts a hand-made good record and rejects five bad ones |
| T0.5 | Generation runner: one call per (prompt, model, run); no system prompt; default settings; retries; rate limits; resumes after a crash; writes complete records | Opus 5.5 (`xhigh`) | T0.3, T0.4, X3 | One prompt runs against every listed model and saves a valid record for each |
| T0.6 | Cost estimate for the pilot and the full grid from measured tokens on the T0.5 test | Sonnet 5.5 | T0.5 | Estimate table in `docs/cost.md`; Human has read it |
| T0.7 | Provider terms: what each provider allows for storing, sharing and publishing outputs | Opus 5.5, then Human | T0.2 | One-page summary per provider with links; Human decides what may enter this public repository |

## Phase 1: Website pilot

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T1.1 | Write six website tasks at three levels and two wordings (36 prompts). L0 must not hint at style | Opus 5.5 | T0.1 | Prompts in `prompts/website/`, versioned |
| T1.2 | Check the prompts for leaks: no L0 or L1 prompt names a style, colour, library or layout | Fable 5.2 | T1.1 | Each prompt passes or is rewritten; reasons logged |
| T1.3 | Local renderer: screenshots at desktop and phone width, light and dark, in a headless browser with no network | Sonnet 5.5 | T0.1 | Renders three hand-made pages into the expected four images each |
| T1.4 | Deterministic website extractors: palette, fonts, libraries, layout pattern, corners and shadows, gradients, icons and emoji, stock phrases, file structure, responsiveness, dark mode, accessibility basics. Seed rules from public slop-pattern lists | Opus 5.5 | T0.4 | Unit tests on hand-made fixtures with known values all pass |
| T1.5 | Define the metrics: fingerprint frequency tables, convergence within and across models, prompt sensitivity from L0 to L2, and the stability rule (top choices unchanged when runs double) | Fable 5.2 | T1.4 | `docs/metrics.md` with formulas, worked examples and thresholds |
| T1.6 | Implement the metrics and the stability check | Opus 5.5 | T1.5 | Tests reproduce the worked examples in `docs/metrics.md` |
| T1.7 | Run the pilot: 540 generations on three models | Script; Human approves spend | T0.6, T1.2, T1.3, X2 | All records valid; failures retried or logged |
| T1.8 | Double the runs on a sample of cells and run the stability check | Script | T1.6, T1.7 | Stability result per model recorded |
| T1.9 | Pilot report: cost, stability, top defaults per model, recommended run count for the full grid | Sonnet 5.5 | T1.8 | Report in `docs/pilot.md` |
| T1.10 | Review the pilot fingerprints against the screenshots | Human | T1.9 | Agreement recorded, or extractor fixes listed |

## Phase 2: Pipeline, math or science, engineering

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T2.1 | Write six tasks per type at three levels and two wordings (108 prompts) | Opus 5.5 | T1.2 (method) | Prompts in `prompts/<type>/` |
| T2.2 | Leak check, as T1.2 | Fable 5.2 | T2.1 | As T1.2 |
| T2.3 | Worked reference solutions for the math and engineering tasks, with stated assumptions and tolerances | Fable 5.2 | T2.1 | Each solution independently re-solved by Opus 5.5; any disagreement resolved; Human spot-checks two |
| T2.4 | Rubrics per type: multiple-choice items for method, assumptions, checks, structure and tone, versioned | Fable 5.2 | T2.1 | `rubrics/<type>.v1.yaml`; every item has an example of each answer |
| T2.5 | Calibrate the tagger: tag 100 outputs per type with Haiku 5.5, Sonnet 5.5 and Opus 5.5; compare with Human tags on a 30-output subset; pick the cheapest model that meets the agreement bar. Also tag a sample with one non-Claude model to check for bias when Claude tags Claude output | Opus 5.5 runs it; Human tags the subset | T2.4, T2.9 | Choice and agreement figures in `docs/tagger.md` |
| T2.6 | Tagger implementation: batch API, versioned rubric, same output tagged twice gives the same tags | Opus 5.5 | T2.4 | Repeat-tagging test passes |
| T2.7 | Sandbox for generated code: no network, no files outside its folder, time and memory limits, records ran or failed and test results | Opus 5.5 (`xhigh`) | T0.1 | Escape tests (network call, file write outside, fork bomb) all blocked; X2 review done |
| T2.8 | Deterministic extractors: pipeline (language, libraries, modules, tests, logging, retries, config); math (units, significant figures, method keywords, plots); engineering (unit system, safety factor, standards cited, checks named) | Sonnet 5.5 | T0.4 | Fixture tests pass |
| T2.9 | Run the three types on the pilot models | Script; Human approves spend | T2.2, T2.7, T2.8, X2 | All records valid |
| T2.10 | Answer checker: final answers against reference solutions with stated tolerances | Sonnet 5.5 | T2.3 | Known right and wrong answers classified correctly |
| T2.11 | Stability check per type, and Human review of a sample of tags | Script, then Human | T2.5, T2.6, T2.9, T2.10 | Each type passes the T1.5 stability rule |

## Phase 3: Full run

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T3.1 | Full grid: all models, four types, run count from T1.9 | Script; Human approves spend | T1.10, T2.11 | Every cell complete or its failure logged |
| T3.2 | Bulk tagging of the full run | Model chosen in T2.5 (expected Haiku 5.5 or Sonnet 5.5) | T3.1 | Every output tagged with the rubric version recorded |
| T3.3 | Dataset v1: JSON Lines plus files, organised by date, model, type, task and level; checksums; release notes | Sonnet 5.5 | T3.2 | Validator passes on the whole set; stored locally, not in git |
| T3.4 | Fingerprint tables per model and type, with the L0 to L2 shift | Sonnet 5.5 | T3.2, T1.6 | Tables generated by one command |
| T3.5 | Viewer: local page with the model-by-level grid for any task, outputs or screenshots side by side, fingerprint beside it | Sonnet 5.5 | T3.3, T3.4 | Opens offline and shows every task |

## Phase 4: Scoring and link-up

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T4.1 | Design the scoring function: share of open choices matching the fingerprint, per dimension, with reasons; rules for an unknown model or date and for features not seen in the baseline | Fable 5.2 | T3.4 | `docs/scoring.md` with worked examples |
| T4.2 | Implement the scoring function | Opus 5.5 | T4.1 | Tests reproduce the worked examples; X2 review done |
| T4.3 | Extract features from the artifact directory's checked artifacts | Opus 5.5 | T1.4, T2.8 | Features stored for every checked artifact |
| T4.4 | Sanity checks: L0 outputs score high, L2 lower, hand-built examples lowest | Script | T4.2 | Ordering holds per type, or the failure is explained |
| T4.5 | Pairwise validation: build pairs ("which is more generic?"); Human judges them | Sonnet 5.5 builds the tool; Human judges | T4.2, T4.3 | Enough judgments for the agreement bar set in T4.1 |
| T4.6 | Agreement analysis between scores and pairwise judgments | Opus 5.5 | T4.5 | Agreement reported; Human accepts or asks for changes |

## Phase 5: Product surface and history

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T5.1 | Type the L0 prompts by hand into the consumer products for a subset of tasks; save outputs with date and product | Human (no automation of consumer sites) | T3.1 | Subset complete and recorded in the run format |
| T5.2 | Import WebDev Arena's dated dataset as the historical website baseline, marked as uncontrolled prompts; check its licence first | Sonnet 5.5 | T1.4 | Imported records validate and carry the source flag |
| T5.3 | Report on the gap between API defaults and product defaults | Opus 5.5 | T5.1, T3.4 | Gap quantified per dimension |

## Phase 6: Upkeep

| ID | Task | Worker | Depends on | Done when |
|---|---|---|---|---|
| T6.1 | One command re-runs the full grid for a new model and produces a dated fingerprint | Opus 5.5 | T3.4 | Tested with a model added to `models.yaml` |
| T6.2 | Monthly canary: small fixed set per model; alert when its fingerprint moves past a threshold | Sonnet 5.5 | T6.1 | Schedule set; a fake drift triggers the alert |
| T6.3 | Public-release decision: which records, under what terms, with the engineering disclaimer | Human, with T0.7 | T3.3 | Written decision; only then do outputs enter the public repository |
| T6.4 | Findings report per release: strongest defaults per model, shared defaults, defaults that survive a detailed brief | Fable 5.2 | T3.4, T4.6 | Report drafted; Human edits and approves |

## Wave 2 types

For each Wave 2 type in plan.md (web app with accounts and data, game, AI feature or agent, plain-language guide, business or product plan, dataset with documentation), repeat the Phase 2 pattern:

| ID | Task | Worker | Done when |
|---|---|---|---|
| W2.x.1 | Six tasks at three levels and two wordings, shaped from the private catalogues but reworded with no names or catalogue text | Opus 5.5 | Prompts committed; X1 scan clean |
| W2.x.2 | Leak check, and a check that no prompt contains catalogue wording | Fable 5.2 | Each prompt passes or is rewritten |
| W2.x.3 | Rubric for the type's open choices | Fable 5.2 | Versioned rubric with examples |
| W2.x.4 | Extractors and checker for the type (see notes) | Sonnet 5.5, or Opus 5.5 where marked | Fixture tests pass |
| W2.x.5 | Pilot-model run, tagging and stability check | Script, tagger from T2.5, Human review | Stability rule passes |

Notes per type:

- **Web app**: install and type-check need packages, so the sandbox gets a local package mirror rather than network access. Mirror setup: Opus 5.5.
- **Game**: headless-browser run with scripted input; screenshot at start and after input; console errors. Prompts name a genre or mechanic, never an existing game.
- **AI feature or agent**: a checker that flags model IDs and SDK calls that are out of date against current provider documentation, rebuilt on each release. Runs against a stub server, never a live API. Opus 5.5.
- **Guide**: readability scores and a link check on every cited source (script); whether each source supports its claim (Sonnet 5.5).
- **Business plan**: count of figures given without a source; competitor names checked as real (Sonnet 5.5).
- **Dataset**: schema validation; sample rows checked against the schema; dataset names and links checked as real.

## Wave 3 types

Platform add-on, phone app, data dashboard, electronics or embedded, research synthesis, teardown or reinvention, translation. Same pattern as Wave 2, at one wording and three runs (54 generations per model per type) until a type shows it is worth the full grid. Prompt writing, rubrics and checkers use the same workers as Wave 2.

| ID | Task | Worker | Done when |
|---|---|---|---|
| W3.0 | Pick the order of Wave 3 types from Wave 2 results and cost | Human, with a Sonnet 5.5 summary | Order recorded in plan.md |
| W3.x | Small-sample run per type, then the decision to promote it to the full grid or drop it | As Wave 2 | Decision recorded per type |
