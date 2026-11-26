# Plan: Default-output baselines across project types

## Context

The artifact directory project needs a way to tell customized work from a model's default output. A search found no shared resource that does this. The closest are WebDev Arena's dataset (dated, multi-model, but uncontrolled user prompts and websites only), the Single-File Test (small) and UI-Bench (commercial builders, not raw models). None covers non-website work, and none varies how much direction the prompt gives.

This project builds that missing baseline: **what each model produces, on each date, for a standard set of tasks, when the prompt asks for a solution and gives little or no direction.** The styling, methods and choices that keep recurring are the model's default. A real artifact can then be scored by how much of it matches that default.

It covers four project types: a website, a pipeline, a math or science problem, and an engineering or mechanical problem.

## The core idea

A "default" is whatever a model chooses when the prompt leaves the choice open. So for each task:

1. Ask for the same thing many times, at increasing levels of direction.
2. Record every choice the model made that the prompt did not dictate.
3. The choices that repeat across runs are the default. How often they repeat is how strong the default is.

Three measurements come out of this:

| Measurement | Question it answers |
|---|---|
| **Default fingerprint** | For this model, type and date, what are the usual choices and how often does each appear? |
| **Convergence** | How alike are repeated runs of the same prompt? High convergence means a strong house style. Also measured across models: do they all make the same choice? |
| **Prompt sensitivity** | How far do the choices move as the prompt adds direction? Shows which defaults are easy to override and which persist. |

A real-world artifact's **default score** is then the share of its open choices that match the fingerprint for its model and date, reported per dimension, not as one number.

## Project types and what "default" means for each

For a website, default is mostly visual. For the other types it is about method, structure and assumptions. Each type has its own list of open choices to record.

| Type | Example tasks | Open choices recorded |
|---|---|---|
| **Website** | Bakery landing page, pricing page, personal portfolio, restaurant menu, event page, to-do app, small dashboard, blog home | Palette, fonts, layout pattern, component set, corner and shadow style, gradients, icons and emoji, copy tone and stock phrases, placeholder content, libraries and framework, file structure, responsiveness, dark mode, accessibility basics |
| **Pipeline** | CSV to cleaned table to database; fetch an API daily and store results; parse logs and aggregate; batch-resize images; CI workflow for a small package; data validation step | Language, libraries, single script versus modules, naming, config handling, error handling, logging, retries, tests present or not, scheduling choice, storage choice, comment and docstring style, README shape, sample data invented |
| **Math or science** | Projectile with drag; loan amortization; titration pH curve; hypothesis test on a small sample; pendulum equation; least-squares fit; explain entropy to a student | Method (closed-form versus numeric), order of steps, assumptions stated or silent, units and significant figures, notation, whether the answer is checked, explanation structure and headings, analogies used, plot choice and plot styling, code offered or not |
| **Engineering or mechanical** | Size a cantilever beam; pick bolts for a flange; gear ratio for a conveyor; heat-sink sizing; shelf bracket with a CAD file; pipe pressure drop and pump choice; compression spring design | Unit system, material assumed, safety factor, load assumptions, standards cited, formula source, checks performed (stress, deflection, buckling, fatigue), tolerances and manufacturability mentioned or not, drawing or CAD format, default dimensions, caveats and disclaimers |

Start with six tasks per type. Tasks are everyday requests with no single right design, so the model has real choices to make. Math and engineering tasks also have checkable answers, which lets correctness be recorded alongside style.

### Further types, drawn from existing project catalogues

Three private project catalogues kept by the author already hold large, varied sets of tasks that people actually ask agents to do, which makes them a better source for new types than guessing. They are not published, and this plan refers to them only by kind:

- **Catalogue A, product plans**: several hundred plans for small software products: web apps, games, add-ons for office and team platforms, on-device phone apps and AI services.
- **Catalogue B, public-good tasks**: a few hundred task records, each tagged by type (writing, data, code, research) and deliverable (document, dataset, pull request): plain-language guides, dataset documentation, schemas, translations and benchmark specs.
- **Catalogue C, teardown notes**: field-by-field notes for teardown and reinvention work, from mechanical parts, electronics and technical drawings to food, textiles, business models and service operations. Early trials there found that plain prompts converge on the same answer for analysis tasks, which is the effect this project measures.

From these, the types below each have open choices that differ from the first four. They are split into two waves by how much evidence the catalogues give and how cheaply the output can be checked.

**Wave 2: add after the Phase 2 types pass the stability check**

| Type | Source | Example tasks | Open choices recorded | Checked by |
|---|---|---|---|---|
| **Web app with accounts and data** | A | Invoice sender with payment link; club dues and documents portal; appointment reminders to cut no-shows; link-in-bio page with click stats; paste-a-messy-spreadsheet cleaner | Framework, database and ORM, auth provider and sign-in methods, payment provider, folder layout, state handling, env and secrets handling, seed data, pricing tiers invented, email provider, test setup, deploy target named | Installs and type-checks in the sandbox; starts and serves its pages; screenshots as for websites |
| **Game** | A | One-button arcade game; daily word puzzle; idle or tending game on real-world time; small physics stacker; card-drafting game | Library or plain canvas, genre framing, controls, art approach (shapes, emoji, sprites), palette, HUD layout, scoring and lives, difficulty curve, sound, start and game-over screens, names and theme invented, save method | Runs in a headless browser; screenshots at start and after scripted input; console errors |
| **AI feature or agent** | A, C | Summarize support tickets; extract fields from invoices into JSON; a chatbot over a document set; tag photos; a small tool-using agent | Provider and model chosen (and whether the model ID is current or stale), SDK versus raw HTTP, prompt structure, structured-output method, retries, cost or token limits, caching, evaluation present or not, guardrails and refusal handling, where keys are read from | Static checks on model IDs and SDK calls against current docs; runs against a stub server in the sandbox |
| **Plain-language guide or explainer** | B | Composting guide for smallholders; what a flood-risk map means; how to read a payslip; explaining a vaccine schedule to parents; a one-page safety checklist | Structure and headings, length, reading level, tone, stock phrases, bullets versus prose, disclaimers, number and kind of sources, whether sources exist, analogies, callouts, licence line, call to action | Readability scores; link check on every cited source; rubric for structure and tone |
| **Business or product plan** | A | One-page plan for a mobile dog-grooming app; pricing for a scheduling tool; go-to-market for a local bakery's subscriptions; a product spec for an expense tracker | Sections included, market-size figures and their sources, competitors named, pricing tiers and price points, channels, MVP scope, metrics and targets, risks listed, timeline shape, invented personas and quotes | Rubric; count of figures given without a source; competitor names checked as real |
| **Dataset with documentation** | B | Datasheet for a public star catalogue; schema and data dictionary for clinic visit counts; cleaning rules for a crop-yield table; caveats section for a poverty dataset | Datasheet template followed, fields covered, schema format, units and missing-value codes, licence stated, provenance recorded, caveats and known biases, sample rows invented, citation style | Schema validates; sample rows match schema; links and dataset names checked as real |

**Wave 3: smaller samples, or later releases**

| Type | Source | Example tasks | Open choices recorded |
|---|---|---|---|
| **Platform add-on or integration** | A | Outlook add-in that files emails; Teams bot posting build status; Shopify bundle app; GitHub Action that checks licences; browser extension that saves highlights | Manifest format and version, SDK versus raw API, sign-in flow, permissions requested (and how many more than needed), UI kit, hosting, polling versus webhooks, where settings are stored |
| **Phone app** | A | Habit tracker; camera-based exercise counter; offline flashcards; plant-watering reminders | Framework (native, React Native, Flutter), navigation pattern, on-device model library, permission prompts and their wording, offline storage, onboarding screens, paywall shape |
| **Data dashboard** | A, B | Sales dashboard from a CSV; maternal-health indicators by region; website traffic summary | Chart library, chart types per question, palette, KPI tiles, layout grid, filters offered, invented data, number formats, dark mode |
| **Electronics or embedded** | C | Battery-powered temperature logger; LED driver for a 12 V strip; soil-moisture sensor with alerts | Microcontroller chosen, stock parts (common transistors, regulators, sensors), power budget stated or not, schematic format, pin choices, safety notes, firmware framework |
| **Research synthesis or method spec** | B | Summarize evidence on a teaching method; write a benchmark spec for document question answering; a reproducibility checklist | Evidence-grading scheme, search method stated, number of sources, invented citations, metrics chosen, limitations section, reporting standard named |
| **Teardown or reinvention** | C | How a ballpoint pen works and three ways to reinvent it; why a restaurant's ordering process is slow; redesign a bicycle lock | Framework named (first principles, TRIZ, SCAMPER and so on), stock analogies and examples reused, number of ideas, ranking method, which constraints are questioned |
| **Translation** | B | Translate a medication leaflet into Spanish plain language; bilingual glossary of farming terms | Literal versus adapted, register, technical terms kept or translated, units and dates localized, translator's notes added |

Two of the types already on the list, a slide deck and a written report, overlap with the guide, plan and research rows above; whether they need their own rows is left to the pilot.

### Using the catalogues as prompts

The catalogues also save prompt-writing. Catalogue A plans and Catalogue B task records are already **L2 Directed** briefs (context, objective, acceptance criteria). L1 and L0 prompts are made by cutting them down to one or two sentences and then to the bare request. Two limits:

- **The catalogues are private.** They are used only to choose and shape tasks. Prompts are rewritten in neutral wording with no product or project names, so this repository and any public dataset never contain catalogue text.
- **Games stay generic.** Game prompts name a genre or mechanic ("a one-button arcade game"), never an existing game.

Catalogue C's notes are drafts not yet reviewed by practitioners, so tasks taken from them are framed as studies of default output, the same as engineering.

## Levels of direction

Every task is written at three levels, and each level in two wordings so that one phrasing does not define the result.

| Level | What the prompt contains | Example (website) |
|---|---|---|
| **L0 Bare** | The request only | "Make a website for a bakery." |
| **L1 Brief** | One or two sentences of purpose and audience | "Make a website for a neighborhood sourdough bakery that takes weekend pre-orders." |
| **L2 Directed** | A real brief: content, constraints, style direction | Names, hours, products and prices, tone, a color and type direction, required sections |

L0 defines the baseline. L1 and L2 measure prompt sensitivity. Each cell is run several times (five to start) because one run cannot show convergence.

## Models, surfaces and dates

- **Models**: the current main models from each major provider, plus one smaller model each. The exact list is fixed in Phase 0 from each provider's current documentation, not from memory.
- **API surface (primary)**: called with no system prompt and default settings. Clean, repeatable and within provider terms.
- **Product surface (secondary, small)**: the same L0 prompts typed by hand into the consumer products (Claude artifacts, ChatGPT Canvas, Gemini Canvas) for a subset of tasks. Product system prompts change the default, and this is what real shared artifacts come from. Done manually; no automation of consumer sites.
- **Dates**: every run is stamped with the date and exact model ID. The full set is re-run when a provider ships a new main model, and a small canary set monthly to catch silent changes.
- **History**: models that are already retired cannot be regenerated. WebDev Arena's dated dataset is imported as the historical website baseline, clearly marked as uncontrolled prompts.

## What gets stored per run

- The prompt, level, wording variant, model ID, surface, settings, date, and token counts.
- The raw response, unedited.
- Extracted files (HTML, code, CAD, notebooks).
- **Website**: screenshots at desktop and phone width in light and dark, rendered locally.
- **Pipeline**: result of running it in an isolated sandbox with no network (ran or failed, tests passed or not).
- **Math and engineering**: the final answer and whether it matches the reference solution.
- Extracted features (see below), each with the extractor version that produced it.

## Turning runs into fingerprints

Three layers, cheapest first:

1. **Deterministic extractors**: parse the output directly. Colors, fonts, libraries, imports, file layout, heading structure, units, presence of tests or checks. Website rules are seeded from the existing public slop pattern lists.
2. **Rubric tagging by a model**: for choices that need reading, such as "which method was used", "which assumptions were stated", "tone of the copy". Fixed rubric per type, versioned, each item multiple-choice so results can be counted.
3. **Human check**: you review a sample per type to confirm the rubric items are being tagged correctly, and compare pairs ("which is more generic?") to confirm the default score matches judgment.

The fingerprint for a model, type, level and date is the frequency table of every recorded choice, plus example outputs nearest the centre.

## Deliverables

- **Dataset**: one record per run in JSON Lines, with files alongside, organized by date, model, type, task and level. Versioned releases.
- **Fingerprint tables**: per model and type, the default choices and their frequencies, and how they shift from L0 to L2.
- **Viewer**: a local page showing, for any task, the grid of model by level with screenshots or outputs side by side, and the fingerprint beside it.
- **Scoring function**: takes a real artifact's extracted features, model and date, and returns a default score per dimension with the reasons.
- **Findings report** per release: strongest defaults per model, defaults all models share, defaults that persist even under a detailed brief.

## Phases

| Phase | Work | Done when |
|---|---|---|
| 0. Setup | Repo, model list from current docs, provider access (direct or through one multi-provider gateway), run record format, cost estimate | A single prompt runs against every listed model and saves a complete record |
| 1. Website pilot | Six website tasks, three levels, two wordings, five runs, three models; rendering; deterministic extractors | Fingerprints for three models are stable when the run count doubles; you agree they match what you see |
| 2. Other types | Task sets, rubrics and extractors for pipeline, math or science, and engineering; sandboxed execution; reference answers | Each type has a fingerprint that passes the same stability check |
| 3. Full run | All models, all types | Dataset v1 and fingerprint tables published locally |
| 4. Scoring and link-up | Scoring function; apply to the artifact directory's checked artifacts; pairwise validation | Default scores agree with your pairwise judgments at a level you accept |
| 5. Product surface and history | Manual product-surface sample; WebDev Arena import | Report quantifies the gap between API defaults and product defaults |
| 6. Upkeep | Monthly canary; full re-run on new models; decision on public release | A new model release produces a new dated fingerprint with one command |

## Size and cost

Full grid: 4 types × 6 tasks × 3 levels × 2 wordings × 5 runs = 720 generations per model. Eight models is 5,760 generations per full run, plus rubric tagging on each.

Each type added later costs 180 generations per model at the same settings: 1,440 across eight models. The six Wave 2 types together add 1,080 per model, or 8,640 across eight. Wave 3 types can start at one wording and three runs (54 per model) until they show they are worth the full grid.

The Phase 1 pilot is 540 generations on three models. Its measured cost and the stability check decide the run count for the full grid; no full run happens before you have seen the pilot figures.

## Verification

- **Reproducibility**: any record can be regenerated from its stored prompt, model ID and settings.
- **Stability**: doubling the runs per cell does not change the top choices in a fingerprint.
- **Extractors**: unit tests on hand-made fixtures with known colors, fonts, libraries and units.
- **Rubric**: the same output tagged twice gives the same tags; your sample review confirms accuracy.
- **Correctness**: math and engineering answers checked against worked reference solutions.
- **Sanity of the score**: L0 outputs score at the default end, L2 outputs score lower, and hand-built examples score lowest.
- **Sandbox**: generated code cannot reach the network or files outside its folder.

## Risks and open questions

- **Product versus API**: most shared artifacts come from consumer products, whose defaults differ from the API's. The manual product sample measures the gap but stays small.
- **Silent model updates**: a model can change without a new ID. The monthly canary is the only detection.
- **Task choice shapes the result**: six tasks per type is a start, not a census. Tasks are versioned so more can be added without breaking comparisons.
- **Non-website types are harder to fingerprint**: method and assumption choices need the rubric layer, which is less exact than parsing CSS.
- **Engineering answers**: outputs are collected to study defaults, not to be used as designs. Anything published carries that note.
- **Publishing outputs**: each provider's terms on sharing model outputs must be checked before any public release.
- **Needed from you**: API keys or gateway access, the meaning and scope you intend for the name "sibar", review time for the pilot fingerprints, and whether the Wave 2 and Wave 3 types under "Further types" are the right ones and in the right order.
