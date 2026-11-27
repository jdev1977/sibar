# Metrics

This page defines every number the project reports about a model's default
output (task T1.5 in [tasks.md](../tasks.md)): the fingerprint frequency
tables, convergence within and across models, prompt sensitivity from L0 to
L2, the intervals around them, the stability rule and the choice of
representative outputs. T1.6 implements it (in a package `analysis/`); its
tests must reproduce the [worked examples](#worked-examples) exactly.

It is written for the website type, the only type with extractors so far.
Nothing in the formulas is specific to websites: a later type needs its own
two data files and no new formula.

Two data files hold what the formulas need to know about the features and the
prompts. T1.6 reads both and decides nothing itself:

- [analysis/website/features.yaml](../analysis/website/features.yaml): every
  feature's type, role and bins, the reason it is or is not counted, and the
  variables that decide it;
- [analysis/website/dictated.yaml](../analysis/website/dictated.yaml): which
  choices each prompt takes out of the model's hands.

Metrics version: **1** (`metrics_version` in `features.yaml`). Any change to a
formula, a threshold, a role, a bin edge or a dictated entry raises it, and
tables made under different versions are never mixed.

Contents: [words](#words) · [which runs count](#which-runs-count) ·
[from features to variables](#from-features-to-variables) ·
[open choices](#open-choices) · [pooling](#pooling-and-weights) ·
[the fingerprint table](#the-fingerprint-table) ·
[agreement and shift](#agreement-and-shift) · [convergence](#convergence) ·
[sensitivity](#sensitivity) · [uncertainty](#uncertainty) ·
[the stability rule](#the-stability-rule) ·
[representative outputs](#representative-outputs) ·
[thresholds](#thresholds) · [worked examples](#worked-examples) ·
[notes for T1.6](#notes-for-t16)

## Words

| Word | Meaning |
|---|---|
| **Run** | One generation: one run record ([record-format.md](record-format.md)). |
| **Cell** | The runs of one model for one task, level and wording in one batch. The pilot plans 5 runs per cell. A model has 6 tasks x 3 levels x 2 wordings = 36 cells, 180 runs. |
| **Feature** | A value an extractor stored for a run ([extractors.md](extractors.md)). |
| **Variable** | A feature made countable: in each run it takes one **choice** (a variable with one value per run) or a set of **items** (a set variable), or it has no value for that run. |
| **Fingerprint** | For one model, project type, level and batch: the frequency table of every variable, with the outputs nearest its centre. |
| **Default** | A choice that a model makes in most runs when the prompt leaves the choice open. |

"Level" always means the level of direction (L0, L1, L2), never a value of a
variable.

## Which runs count

**One record per planned run.** Several records can share a cell key
(`runner.record.cell_key`): a failed attempt and its retry, or a refusal that
was run again. For each cell key the metrics take **the first record, by
timestamp, whose status is not `failed`**. Later records for that key are
ignored. A failure says nothing about the model; a refusal or a truncated
answer does, and taking the first real answer stops a re-run from replacing
it with a more convenient one. A cell key with only failed records has no
run.

Only records with `source: controlled`, `surface: api`, the same `settings`
and one `prompt_set_version` per task enter one table.

**Outcome.** Every selected record has one outcome:

| Outcome | Record |
|---|---|
| `artifact` | status `ok`, and `website.file-structure` found a page: `structure` has a value other than `no-html` |
| `no-artifact` | status `ok`, but there is no page: `website.file-structure` is `no-input`, or `structure` is `no-html` (the model answered in prose, asked a question, or wrote something that is not a website) |
| `unread` | status `ok`, but `website.file-structure` has status `error` |
| `truncated` | status `truncated` |
| `refused` | status `refused` |

Outcomes are tabulated like any variable (the **outcome table**, pooled as in
[Pooling and weights](#pooling-and-weights)), over all selected records.

**Usable runs.** Only `artifact` runs enter the feature tables. A truncated
page is left out because a cut-off file reads as choices nobody made (no
footer, no closing script); what is lost is recorded in the outcome table.

When more than **10%** of a fingerprint's selected runs (by weight) are not
`artifact`, the fingerprint is flagged `incomplete outcomes`: it describes
only the runs that produced a page. The reason for 10%: runs left out can
move any share by at most their own share, and at 60 runs the interval around
a share of 0.5 is already 12 points either side
([Uncertainty](#uncertainty)), so up to 10% missing stays inside the noise.

**Extractor versions.** Every usable run in a table must carry every website
extractor at the version listed in `features.yaml`. T1.6 refuses to compute
otherwise (re-run `python -m extractors` first); it never mixes versions and
never treats "extractor not run" as a value.

**Batch and date.** A fingerprint belongs to a **batch group**: the batch ids
named when it is computed (for the pilot, one: `pilot-1`). Its date is the
first and last UTC date of its records' timestamps. If its records report
more than one `model_id_returned`, it is flagged `mixed snapshots`.

## Types with a rubric

Pipeline, math and engineering records (T2.8) carry two kinds of features:
the deterministic extractors' and the tags of the model-read rubric
([rubrics.md](rubrics.md)). Their `analysis/<type>/` folders hold the same
two data files as the website's, with three additions to `features.yaml`.
Every formula on this page applies unchanged.

**Outcome** (`outcome`). These types have no page, so the rubric's gate item
`response_mode` decides:

| Outcome | Record with status `ok` |
|---|---|
| `unread` | the tagger's status is `error`, or the gate is `null` (cannot tell); or, for pipeline, `pipeline.layout` failed |
| `no-artifact` | the gate is `asks-first` or `declines`; or, for pipeline only, `pipeline.layout.structure` is `no-code` (code written outside a fenced block is not seen) |
| `artifact` | otherwise. A math or engineering answer in prose is an artifact |

`truncated` and `refused` records are as for websites. A record that has not
been tagged is refused: tag the record file before computing tables.

**Versions.** The rubric's version is written `1@*` in `features.yaml`: the
rubric version is fixed, the tagger model is not. All tags in one table must
come from one tagger model.

**Items asked of some tasks** (`tasks`). A rubric item asked only of some
tasks is `not applicable` in the others, so those runs are not counted as
undetermined.

**Open choices.** `dictated.yaml` of each type holds the entries of the
rubric's companion, copied word for word, and the entries for the extractor
features. L0 and L1 close nothing but the unit system, in the tasks whose
givens are in SI units at every level.

Every extractor feature that a keyword or pattern may misread starts
`provisional`, as every rubric variable does; T2.11 promotes or drops them.
The simulation behind [the stability rule](#the-stability-rule) was run with
the website's variable counts; it has not been repeated for these types.

## From features to variables

### Value, undetermined, not applicable

For each usable run a variable is in one of three states:

| State | When | Counted |
|---|---|---|
| **Value** | The extractor's status is `ok` or `partial` and the feature is not `null`. "Not present" values (`[]`, `0`, `false`, `"none"`, `"default"`, `"same"`) are values: the extractor looked and the page does not have it. | In every denominator |
| **Undetermined** | The extractor's status is `no-input` or `error`; or the feature is `null`; or a mask applies (below). The page may or may not have it: nobody knows. | In no denominator; counted as `undetermined` |
| **Not applicable** | The declaration says the value describes something this page does not have: an empty list with `empty: not-applicable`, or a value listed under `not_applicable`. | In no denominator; counted as `not applicable` |

An extractor's status is its feature named `status`. A `partial` status (a
limit cut the reading short) keeps the value; the share of `partial` runs is
reported per extractor. `status`, `error` and `skipped_files` are declared
once, under `common`, for every extractor.

Every share therefore has the runs that **have a value** as its denominator.
A variable's row always shows how many usable runs were undetermined and how
many not applicable. When more than **10%** of the usable runs (by weight)
are undetermined, the row is flagged `partly read`.

**Not applicable** keeps one fact from being counted several times. A page
with no gradient has an empty `gradient_types`, `gradient_directions`,
`gradient_hues` and `gradient_targets`. Counting four empty lists as four
choices would make two gradient-free pages agree five times over. The one
fact, no gradient, is carried by `gradient_count`; the other variables
describe gradients where there are some.

### Types

Every feature has a declared type. The type fixes how it becomes choices and
how it enters each metric.

| Type | Becomes | Frequency table | Agreement of two runs | Top choice |
|---|---|---|---|---|
| **categorical** | its value as text | share of each choice | 1 if equal, else 0 | the choice with the largest share |
| **boolean** | `true` or `false` | as categorical | as categorical | as categorical |
| **number** | the label of its bin | as categorical, bins in order | as categorical | as categorical |
| **set** | a set of items, each the JSON text of a list element (`768`, `tailwindcss`) | share of runs that hold each item | Jaccard: shared items over all items of the two; 1 if both are empty | the default set: every item held by an established majority of runs |
| **ordered list** | the set of its adjacent pairs, `a>b`, with `^` before the first element and `$` after the last; an empty list is `{^>$}` | as set, over pairs | as set, over pairs | as set, over pairs |
| **count-map** (an object of name to count) | the set of names whose count reaches `min_count` | as set | as set | as set |
| **coverage** (derived from two numbers, `part` of `whole`) | `none` (part is 0), `all` (part equals whole), `some`; not applicable when whole is 0; undetermined when either number is | as categorical | as categorical | as categorical |

- **Bins.** `bins` lists the lower edges in ascending order, starting at the
  smallest possible value. A bin runs from its edge to one below the next
  edge; the last has no upper end. Labels: `0` (one value), `1-2`, `6+`. So
  `[0, 1, 3, 6]` gives `0`, `1-2`, `3-5`, `6+`. Bins are fixed in advance, not
  taken from the data (no quantiles), so that tables from different models and
  dates share their choices. The edges are a first guess; after the pilot
  they may change, with a new metrics version.
- **Order in a list** enters only through adjacent pairs. `sections` (the
  page's blocks in order) gives pairs such as `hero>features`; which kinds of
  section a page has is the separate set `section_kinds`.
- **Numbers are not averaged.** No metric uses a mean of a count: counts of
  elements depend on page length, and a mean hides the split between pages
  that have none and pages that have many.
- **Booleans and bin labels are text** wherever they are written (`"false"`,
  `"0"` in `dictated.yaml`).

### Roles

| Role | Frequency table | Per-variable convergence and shift | Summaries, stability verdict, representative outputs |
|---|---|---|---|
| **primary** | yes | yes | yes |
| **provisional** | yes | yes | no |
| **secondary** | yes | no | no |
| **diagnostic** | as a health rate | no | no |

A feature is primary when it is one choice of the page, read by a rule that
does not guess, in a vocabulary small enough to count. The others are left
out of the summaries for one of these reasons (`why` in `features.yaml`):

| Reason | Meaning | Examples |
|---|---|---|
| `redundant` | A function of another feature. Counting both would count one choice twice. | `hero` (is `hero` in `section_kinds`), `base_scheme` (from `background`), `tailwind_usage` |
| `raw` | Unclassed values with a large vocabulary; a classed feature carries the choice. | `colors` (hex codes; `color_classes` counts), `common_radius` (`corner_style` counts), `cdn_hosts` |
| `detail` | A count or list behind a variable that already carries the choice. | `family_count`, `inline_svg_count`, `width_media_queries` |
| `heuristic` | Read by a heuristic that the pilot review (T1.10) has to check against screenshots first. Provisional until then. | `sections`, `section_kinds`, `section_count`, `card_groups`, `gradient_targets` |
| `thin-rules` | Depends on the stock-phrase rules, whose coverage of page copy is thin, and some of whose single-word rules (`vibrant`, `showcase`, `enhance`) match ordinary copy. A rule that never fires does not show the copy is free of stock phrases. Provisional. | `stock_phrase_counts` and the features derived from the same rules |
| `health` | Says how well the page was read. Diagnostic. | `status`, `unparsed_colors`, `unknown_color_utilities`, `unrecognised` |

Counts: 62 primary variables (45 with one value per run, 17 sets), 6
provisional, 57 secondary, 4 diagnostic, plus `status`, `error` and
`skipped_files` for every extractor.

A provisional variable becomes primary, or is dropped, after T1.10, by an
edit to `features.yaml` and a new metrics version.

### The variables

`features.yaml` is the authority; this table is a copy for reading. The
dimension is the unit of every summary and of the later default score.
Each extractor has one dimension (`dimensions`); a variable may name its own
with a `dimension` key, which overrides its extractor's. Rubric tags need
this: all of them come from one extractor, `rubric.<type>`, and each item
has its own dimension (`tagger.rubric.variable_declarations` writes it).

| Dimension | Primary variables | Provisional | Secondary (tables only) | Diagnostic |
|---|---|---|---|---|
| **palette** (`website.palette`) | `dominant_hue` (categorical)<br>`background` (categorical)<br>`color_classes` (set)<br>`color_count` (number: `0-3`, `4-7`, `8-12`, `13+`) |  | `base_scheme`, `hues`, `colors`, `background_hex`, `tailwind_colors` | `unknown_color_utilities`, `unknown_color_names`, `unparsed_colors` |
| **fonts** (`website.fonts`) | `primary_font` (categorical)<br>`heading_font` (categorical)<br>`font_sources` (set)<br>`system_stack` (boolean) |  | `primary_category`, `heading_category`, `families`, `family_count`, `generic_families`, `loaded_families`, `font_categories` |  |
| **libraries** (`website.libraries`) | `libraries` (set)<br>`framework` (categorical)<br>`css_framework` (categorical)<br>`delivery` (set; empty is not applicable) |  | `library_count`, `cdn_hosts`, `tailwind_usage`, `tailwind_evidence` | `unrecognised` |
| **layout** (`website.layout`) | `landmarks` (set)<br>`layout_systems` (set)<br>`grid_columns` (set; empty is not applicable)<br>`nav_position` (categorical) | `sections` (ordered-list; task-driven)<br>`section_kinds` (set; task-driven)<br>`section_count` (number: `0-2`, `3-4`, `5-6`, `7-8`, `9+`; task-driven)<br>`card_groups` (number: `0`, `1`, `2`, `3+`; task-driven) | `hero`, `card_group_sizes`, `mapped_card_groups`, `max_widths_px`, `container_class` |  |
| **corners-shadows** (`website.corners-shadows`) | `corner_style` (categorical)<br>`pill_shapes` (boolean)<br>`shadow_count` (number: `0`, `1-2`, `3-5`, `6+`)<br>`shadow_kinds` (set; empty is not applicable)<br>`text_shadow` (boolean)<br>`backdrop_blur` (boolean) |  | `common_radius`, `radii` |  |
| **gradients** (`website.gradients`) | `gradient_count` (number: `0`, `1-2`, `3-5`, `6+`)<br>`gradient_types` (set; empty is not applicable)<br>`gradient_directions` (set; empty is not applicable)<br>`gradient_hues` (set; empty is not applicable)<br>`gradient_text` (boolean) | `gradient_targets` (set; empty is not applicable) | `gradient_pairs` |  |
| **icons-emoji** (`website.icons-emoji`) | `icon_kinds` (set)<br>`icon_libraries` (set; empty is not applicable)<br>`emoji_count` (number: `0`, `1-3`, `4-9`, `10+`)<br>`favicon` (categorical) |  | `emoji`, `emoji_led_headings`, `inline_svg_count`, `svg_image_count`, `text_symbols` |  |
| **copy** (`website.stock-phrases`) | `em_dash_count` (number: `0`, `1-2`, `3+`)<br>`exclamation_count` (number: `0`, `1-2`, `3+`)<br>`title_case` (coverage of `title_case_headings` in `headings_checked`) | `stock_phrase_counts` (count-map) | `stock_phrases`, `stock_phrase_categories`, `stock_phrase_hits`, `stock_phrase_matches`, `copy_word_count`, `headings_checked`, `title_case_headings` |  |
| **file-structure** (`website.file-structure`) | `structure` (categorical)<br>`file_count` (number: `0`, `1`, `2-3`, `4-9`, `10+`)<br>`inline_style_blocks` (number: `0`, `1`, `2+`)<br>`inline_script_blocks` (number: `0`, `1`, `2+`)<br>`style_attributes` (number: `0`, `1-5`, `6-20`, `21+`)<br>`has_readme` (boolean)<br>`total_bytes` (number: `0-4999`, `5000-14999`, `15000-39999`, `40000+`) |  | `file_kinds`, `folders`, `max_depth`, `entry_file`, `html_files`, `external_scripts`, `external_stylesheets`, `has_package_json`, `has_build_config` |  |
| **responsiveness** (`website.responsiveness`) | `viewport_meta` (categorical)<br>`media_query_style` (categorical)<br>`breakpoints_px` (set; empty is not applicable)<br>`tailwind_breakpoints` (set; empty is not applicable)<br>`fluid_techniques` (set)<br>`responsive_images` (boolean) |  | `width_media_queries` |  |
| **dark-mode** (`website.dark-mode`) | `dark_mode` (categorical)<br>`mechanisms` (set; empty is not applicable) |  | `forced_dark`, `theme_toggle` |  |
| **accessibility** (`website.accessibility`) | `html_lang` (categorical)<br>`alt_coverage` (categorical; not applicable: `no-images`)<br>`h1_count` (number: `0`, `1`, `2+`)<br>`heading_skips` (number: `0`, `1+`)<br>`main_landmark` (boolean)<br>`skip_link` (boolean)<br>`buttons_without_name` (number: `0`, `1+`)<br>`generic_link_text` (number: `0`, `1+`)<br>`aria_attributes` (number: `0`, `1-5`, `6-20`, `21+`)<br>`focus_styles` (boolean)<br>`outline_removed` (boolean)<br>`reduced_motion` (boolean)<br>`unlabelled` (coverage of `unlabelled_controls` in `form_controls`) |  | `lang`, `images`, `images_missing_alt`, `images_empty_alt`, `heading_levels`, `form_controls`, `unlabelled_controls`, `role_attributes`, `positive_tabindex` |  |

`stock_phrase_counts` counts a rule as present from one hit, except the four
generic call-to-action rules (`cta-get-started`, `cta-learn-more`,
`cta-read-more`, `cta-try-now`), which need three hits on a page. That is the
source catalogue's condition, which the extractor leaves to the metrics
([extractors.md](extractors.md), `website.stock-phrases`).

### Blind spots of the extractors, and what the metrics do about each

| Blind spot (from T1.4 and its review) | Rule here |
|---|---|
| Stylesheets of frameworks other than Tailwind are not read (Bootstrap's blue, its radii, its system font, its grid and its fixed nav bar). What is read from such a page is only what the page adds on top. | **Mask** `unread-framework-stylesheet`: when `css_framework` is neither `none` nor `tailwindcss`, every palette, fonts and corners-shadows variable, and `layout_systems`, `grid_columns`, `nav_position`, `media_query_style` and `breakpoints_px`, are undetermined for that run. The framework itself is counted in `css_framework`. |
| Section kinds, card groups and gradient targets are heuristics (English keywords, sibling patterns). | Provisional until T1.10. |
| Stock-phrase rules are thin and some match ordinary words. | Provisional; the per-phrase table (`stock_phrase_matches`) is secondary so single phrases can be studied. |
| Text that scripts build, and strings that do not read as prose, are not copy. Component projects are affected most. | No rule. The copy dimension is read with this caveat; `copy_word_count` is shown beside it. |
| A page that spends the per-page `var()` budget (1,000,000) has its remaining `var()`s unresolved, at a point that depends on rule order. | They count in `unparsed_colors`. The share of runs with `unparsed_colors` of 1 or more is a health rate of the palette dimension; above 10% the dimension is flagged `partly read`. |
| Colour names in utilities that are in neither Tailwind's palette nor a readable theme. | Health rate `unknown_color_utilities` of 1 or more, flagged the same way. |
| A CSS number of more than 4,300 digits makes every extractor report `error`. | The run's outcome is `unread`; it is in the outcome table and in no feature table. |
| A long data URI behind a CSS variable cannot be read through `var()`. | No effect on any variable (it is not a colour, font or shadow). |
| Flat navies such as `#2c3e50` read as grey, to keep Tailwind's slate grey. | No rule. A page whose accent is such a navy shows `dominant_hue: none`. To check in T1.10. |
| Tailwind v4 colours are read with v3 values; a spread or reference in a Tailwind config is skipped. | No rule; `unknown_color_utilities` shows the second. |
| Framework components render markup the extractor does not see (accessible names, icons as components). | No rule. `buttons_without_name` and `generic_link_text` are HTML-only by design. |

A mask is declared in `features.yaml` (`masks`): a condition on one
categorical variable (`in` or `not_in` a list) and the variables it makes
undetermined. A mask never hides the variable it tests. Three details:

- `*` covers every variable of the extractor except its diagnostic ones.
  Health rates are never masked: each is over every usable run whose
  extractor has status `ok` or `partial`, masked or not. The share of masked
  runs is a health rate of its own.
- When the tested variable is itself undetermined for a run, the mask
  applies: a framework that cannot be ruled out may be there.
- A mask is about what could be read, not about what the prompt left open. It
  goes by the run's own value of the tested variable, also in a cell where
  that variable is closed.

## Open choices

A default is what a model chooses **when the prompt leaves the choice open**
([plan.md](../plan.md)). So before anything is counted, each variable in each
cell is either **open** or **closed**:

- **closed**: `dictated.yaml` lists the variable for that task and level. The
  brief named the look (`direction`), supplied or required the content that
  decides the value (`content`), or stated a technical need (`constraint`).
- **open**: everything else.

The two wordings of a cell give the same facts
([leak-check.md](leak-check.md)), so open and closed are properties of the
task and level, not of the wording. In prompt set version 1, **L0 and L1
close nothing**; every L2 closes its palette, its copy, its sections and its
page size, five of the six close the corner style, five close the heading or
body font, and the rest varies by task. A record
whose `prompt_set_version` differs from the one in `dictated.yaml` is
refused: the entries were read from one text.

**Dependent variables.** A variable is also closed when a variable that
partly or wholly decides it is closed, whether or not `dictated.yaml` lists
it. `features.yaml` names these ties under `depends_on`. There are three
kinds:

- it is **computed from** the other: `dark_mode` is `dark-only` when the page
  background is dark, so a brief that dictates a light page has decided part
  of it; `base_scheme` is read off `background`;
- it **describes a thing whose presence the other carries**: the kinds of
  shadow where `shadow_count` is closed, the mechanisms of a dark mode where
  `dark_mode` is. Where a brief removes the thing, such a variable would be
  counted on the runs that disobeyed, and on no others;
- it **draws its values from** the other: the hues of gradients from the
  page's colours, the font services from the faces they supply, the
  libraries from the icon sets among them.

One of these ties is a judgement. Where a brief dictates the icons, only
the icon sets among a page's `libraries` are decided, yet the whole set is
closed. Taking out the icon items alone would need the same removal at both
levels of every comparison and would pool tasks with and without it in one
row. Little is lost: the main choices in that set, the framework and the CSS
framework, are variables of their own and stay open, as does `delivery`.

Dependence is followed step by step (`mechanisms` depends on `dark_mode`,
which depends on `background`). Left open, such a variable would move at L2
because the brief moved its source, and the move would be read as
spill-over, as if the brief had not touched it. A dependent variable is in
the directed table, marked `dependent` with the variable that closed it. It
has compliance only where `dictated.yaml` lists it with an expected value
(as it does for `dark_mode`: anything but `dark-only`). Dependence does not
cover a variable that merely becomes applicable: a dictated form makes
`unlabelled` (how many of its controls lack a label) applicable, and leaves
it open.

What open and closed mean for each metric:

| Metric | Open variables | Closed variables |
|---|---|---|
| Fingerprint table | Counted. A fingerprint at a level uses, for each variable, only the tasks where it is open at that level. | Not in the fingerprint. Shown in the **directed table**, per task. |
| Convergence, wording sensitivity | Counted, and summarised by dimension. | Per variable in the directed table; in no summary. |
| Prompt sensitivity between two levels | A variable counts for a task when it is open at **both** levels: this is the **spill-over**, how far choices move that the brief did not mention. | A variable closed at either level is in the directed table: its shift, and where `expect` is given, **compliance** and **persistence** ([Sensitivity](#sensitivity)). |
| Stability verdict | L0 only, where everything is open. | None. |
| Representative outputs | Counted. | Not counted. |

What stays open at L2 in prompt set version 1, worked out from the two data
files:

| Dimension | Primary variables open at L2, with the number of tasks (of six) where each is open | Open in no task |
|---|---|---|
| palette | none | `dominant_hue`, `background`, `color_classes`, `color_count` |
| fonts | `primary_font` 3, `heading_font` 1, `system_stack` 1 | `font_sources` |
| libraries | `libraries` 3, `framework` 5, `css_framework` 5, `delivery` 5 |  |
| layout | `landmarks` 6, `layout_systems` 6, `grid_columns` 4, `nav_position` 6 |  |
| corners-shadows | `corner_style` 1, `pill_shapes` 1, `shadow_count` 1, `shadow_kinds` 1, `text_shadow` 2, `backdrop_blur` 3 |  |
| gradients | `gradient_count` 3, `gradient_types` 3, `gradient_directions` 3, `gradient_text` 3 | `gradient_hues` |
| icons-emoji | `icon_kinds` 3, `icon_libraries` 3, `emoji_count` 3, `favicon` 6 |  |
| copy | none | `em_dash_count`, `exclamation_count`, `title_case` |
| file-structure | `structure` 6, `file_count` 6, `inline_style_blocks` 6, `inline_script_blocks` 6, `style_attributes` 6, `has_readme` 6 | `total_bytes` |
| responsiveness | `viewport_meta` 6, `media_query_style` 6, `breakpoints_px` 6, `tailwind_breakpoints` 5, `fluid_techniques` 6, `responsive_images` 6 |  |
| dark-mode | none | `dark_mode`, `mechanisms` |
| accessibility | `html_lang` 6, `alt_coverage` 6, `h1_count` 6, `heading_skips` 6, `main_landmark` 6, `skip_link` 6, `buttons_without_name` 6, `generic_link_text` 6, `aria_attributes` 6, `focus_styles` 6, `outline_removed` 6, `reduced_motion` 6, `unlabelled` 6 |  |

Palette, copy and dark mode have no open variable at L2, and `font_sources`,
`gradient_hues` and `total_bytes` are open in no task. Their L2 fingerprint
is empty by design: there is no default to report where every brief decided
the choice. Most corner, shadow and font variables are open in one or two
tasks, too few for a pooled row (T below 3). The L2 spill-over therefore
rests mainly on layout, file structure, responsiveness and accessibility,
with libraries, gradients and icons on three to five tasks.

**Associations.** L1 content can pull an open choice without dictating it: a
sourdough bakery suggests warm colours. `dictated.yaml` lists these
(`associations`) from the leak-check log. They close nothing. The report
prints the note beside the shift into that level, so that a shift from L0 to
L1 on those variables is read as the effect of that content.

**Task-driven variables.** Some values are decided by the task's subject at
every level: a pricing page has a pricing section, a to-do app has form
controls. They are marked `task_driven: true` in `features.yaml` and are read
in the per-task tables; their pooled row is shown with the mark. Whether a
variable depends on the task is also measured for every variable (**task
spread**, below), so an unmarked one that turns out to depend on the task is
found.

## Pooling and weights

A fingerprint pools the runs of one model at one level: up to 6 tasks x 2
wordings x 5 runs = 60 runs in the pilot. The weights are fixed by the design,
not by how many runs each cell happens to have:

1. **Runs in a cell** count equally.
2. **The two wordings of a task** count equally (the T1.2 ruling: pool A and
   B with equal weight).
3. **Tasks** count equally, so no task dominates, whatever its number of
   usable runs.

For a variable v and a level, let n(t,w) be the number of runs in cell (t,w)
that have a value for v, and count(t,w,k) the number of those with choice k
(for a set: that hold item k).

    share in a cell      p(t,w,k) = count(t,w,k) / n(t,w)          needs n(t,w) >= 1
    share in a task      p(t,k)   = mean of p(t,w,k) over the wordings of t with n(t,w) >= 1
    share (fingerprint)  p(k)     = mean of p(t,k) over the tasks with at least one such wording

Tasks where v is closed at that level are left out before any of this.

- A cell with no run that has a value is dropped; its task then rests on the
  other wording alone. A task with no such run is dropped. The row shows
  **T**, the number of tasks that contributed, and **N**, the number of runs.
- **Weight of a run**: w = 1 / (T x W(t) x n(t,w)), where W(t) is the number
  of wordings of its task that contributed. The weights sum to 1.
- **Effective number of runs**: n_eff = 1 / (sum of w squared). With every
  cell complete it equals N (60 for a pilot level). Unequal cells lower it:
  a cell with one run gives that run a large weight, and the estimate is as
  uncertain as one from fewer, equal runs. n_eff is what every interval and
  every "enough evidence" rule uses.
- Shares are exact fractions. For a variable with one value per run they sum
  to 1; for a set they do not.
- A share of runs **by weight** (undetermined, not applicable, masked, an
  outcome, a health rate) is pooled by the same three lines, with every
  usable run in the denominator (for outcomes: every selected record), so a
  run counts the same there whether or not it has a value.

**Too little to report.** A fingerprint row with **T below 3** or **n_eff
below 16** is labelled `insufficient data` and reports no top choice. Both
limits are conventions, not error rates: the clear-lead condition is as valid
at 12 effective runs as at 60. They are there so that a label means the same
in every row. Below 16 effective runs no result can be shown to be a strong
default (the lower bound for 15 of 15 is 0.796, for 16 of 16 it is 0.806),
and an established majority needs 12 of 15, so `default` would mean "four
runs in five" in a thin row and "two in three" (38 of 60) in a full one.
Below 3 tasks a pooled row is a per-task table under another name, and there
is no usable interval across tasks (two tasks give a multiplier of 12.7).
The shares, the intervals and the three evidence conditions are still shown.

**Per-task tables** use the first two lines only (cell, then task), with
weights and n_eff worked out within the task. They exist for every variable,
are the place to read task-driven variables, and are descriptive: with at
most 10 runs they carry no label. The clear-lead condition can still be
evaluated on one; persistence ([Sensitivity](#sensitivity)) does so.

## The fingerprint table

One row per variable and choice (or item), for one model, project type, level
and batch group:

| Field | Meaning |
|---|---|
| share | p(k), as a fraction and a decimal |
| run interval | 95% interval for the share if the same prompts were run again ([Uncertainty](#uncertainty)) |
| task interval | 95% interval for the share over other tasks of the same kind |
| N, T, n_eff | runs with a value, tasks, effective runs |
| undetermined, not applicable | usable runs without a value, by weight and by count |

and one summary per variable:

**Top choice** (a variable with one value per run). Order the choices by
share. Let p1 be the largest share and p2 the next (0 if there is no other
choice), and x1 = p1 x n_eff, x2 = p2 x n_eff. With z = 1.96 (z squared =
3.8416):

| Evidence | Condition | Reads as |
|---|---|---|
| **clear lead** | (x1 - x2)^2 > z^2 x (x1 + x2) | the top choice is ahead of the runner-up by more than re-running would explain |
| **established majority** | x1 > n_eff / 2 and (2 x1 - n_eff)^2 > z^2 x n_eff | chosen in more than half of runs, by more than re-running would explain |
| **strong** | lower end of the run interval of p1 above 0.8 | chosen in more than four runs in five |

The first two conditions are the 95% Wilson interval in closed form: a clear
lead is "the lower end of the interval for x1 / (x1 + x2), with x1 + x2 runs,
is above one half", and an established majority is "the lower end of the run
interval of p1 is above one half". An established majority is always a clear
lead, and a strong default is always an established majority.

| Label | When | Reported top choice |
|---|---|---|
| `strong default` | strong | the choice |
| `default` | established majority, not strong | the choice |
| `leading` | clear lead, no established majority | the choice |
| `contested` | no clear lead, or a tie | none |
| `insufficient data` | T below 3 or n_eff below 16 | none |

The table always shows the choice with the largest share, whatever the label
(the **nominal top**). Only a row with a clear lead **reports** a top choice,
and only reported top choices are called defaults in any report.

**Ties.** Shares are compared as exact fractions. When two or more choices
share the largest share, the nominal top is all of them, in alphabetical
order (bins in bin order); the label is `contested`. A tie can never be a
clear lead (x1 - x2 = 0).

**Default set** (a set variable). An item is a **default item** when an
established majority of runs hold it: with x = p(item) x n_eff, x > n_eff / 2
and (2x - n_eff)^2 > z^2 x n_eff. The variable's reported top choice is the
set of its default items, which may be empty. Items are listed by share.

**Task support and task spread** (a variable with one value per run and a
single nominal top k):

- **task support**: in how many of the T tasks k is the top choice of the
  task's own table (ties included), written `5/6`;
- **task spread**: the largest minus the smallest p(t,k) over the tasks.

A spread of **0.7 or more** marks the row `task-dependent`: the pooled share
is an average of tasks that disagree, and the per-task tables are the ones to
read. With 10 runs per task and the same true share in all six tasks, a
spread that large appears by chance in at most 3.3% of cases (at a true share
of 0.5; less elsewhere), against 12% for a limit of 0.6. It finds one
deviating task in 98% of cases when five tasks are at 0.9 and one at 0.1, and
in 62% when the one is at 0.3 (simulation, 40,000 draws each).

A default is said to **hold across tasks** only when task support is T of T
and T is at least 5. If a task were as likely as not to have another top
choice, all six would agree by chance once in 64 (0.016), all five once in 32
(0.031), but five of six in 7 of 64 (0.109). Six tasks cannot show more than
this ([Uncertainty](#uncertainty)).

**Other tables.** The outcome table and the health rates (share of usable
runs with status `partial`, with `unparsed_colors` of 1 or more, with
`unknown_color_utilities` of 1 or more, and masked) are part of every
fingerprint, pooled the same way.

## Agreement and shift

Every measure of convergence and sensitivity is built from one thing: how
much two runs agree on a variable.

**Agreement** a(r, s) of two runs r and s on a variable, both with a value:

- one value per run: 1 if the two choices are equal, 0 if not;
- set: the number of items in both, over the number of items in either
  (Jaccard); 1 if both sets are empty.

A pair where either run has no value (undetermined or not applicable) is
skipped.

For two groups of runs G and H (two cells, say):

    within(G)   = mean of a(r, s) over all pairs of different runs in G      needs 2 runs with a value
    cross(G, H) = mean of a(r, s) over all r in G and s in H                 needs 1 run with a value in each
    shift(G, H) = ( within(G) + within(H) ) / 2  -  cross(G, H)             needs 2 in each

For a variable with one value per run, `within(G)` is the chance that two
different runs of G make the same choice, and with counts x(k) among n runs
it equals the sum over k of x(k)(x(k) - 1), over n(n - 1).

**Why `shift` and not a difference of shares.** With 5 runs per cell, two
cells drawn from the very same model and prompt never show the same shares,
so any distance between their tables is above zero on average and says
"different" when nothing differs. `shift` has no such bias. Its expected
value is half the squared distance between the two true distributions: for a
variable with one value per run, 1/2 x the sum over k of (p(k) - q(k))^2. So:

- it is **0 on average when nothing differs**, and noise puts single values
  on either side of 0. Negative values are kept, not clipped: clipping would
  bring the bias back;
- it is **1** when each group is unanimous and the two disagree;
- for a yes/no choice whose share moves from p to q it is **(p - q)^2**:

| shift | the same as a yes/no choice moving by |
|---|---|
| 0.01 | 10 points |
| 0.04 | 20 points |
| 0.09 | 30 points |
| 0.16 | 40 points |
| 0.25 | 50 points |
| 1.00 | a complete switch |

(`shift` is the unbiased estimate of the squared maximum mean discrepancy
with the agreement as kernel, halved. Both the equality kernel and the
Jaccard kernel are positive definite, so the true value is never negative.)

**From cells to a result.** Every measure Q below (convergence, wording
shift, level shift, excess, model shift) is first computed per variable for
one cell or one pair of cells, and then averaged in this fixed order, always
skipping what is undefined:

1. over the wordings of a task: Q(t, v);
2. per variable, over tasks: Q(v), with a task interval from the Q(t, v);
3. per dimension within a task, over the **primary** variables of the
   dimension that are open for that task: Q(t, d); then over tasks: Q(d), with
   a task interval from the Q(t, d);
4. overall within a task, over the dimensions that have a value: Q(t); then
   over tasks: Q, with a task interval from the Q(t).

Dimensions count equally in step 4, so a dimension with many variables
(accessibility has 13) does not outweigh one with few (dark mode has 2).

## Convergence

**Within a model: how alike are repeated runs of the same prompt?**

    convergence of a cell   C(t, w, v) = within(runs of the cell)

averaged as above. C is the chance that two runs of the same prompt make the
same choice (for a set: their mean overlap). 1 means every run is the same;
for a variable with K equally likely choices it is 1/K. A cell with fewer
than two runs with a value has no C.

It is reported per variable, per dimension and overall, at each level, for
each model. High convergence at L0 is the "strong house style" of the plan.
Convergence needs no top choice and is not affected by the labels above.

**Across models: do they make the same choice?** For two models m and m' and
one cell position (task, level, wording):

    cross-model agreement   X(m, m') = cross(runs of m, runs of m')
    model shift             D(m, m') = shift(runs of m, runs of m')

averaged as above, per pair of models; and averaged over the pairs for "all
models". X is the chance that two different models, given the same prompt,
make the same choice. D is how far the two models' habits are apart, with
their own run-to-run variation taken out: 0 when the two are interchangeable
on a variable, up to 1.

Two statements come out of this, each with its condition:

- **Shared default**: a choice that is the reported top choice of a variable
  in the fingerprint of **every** model at that level.
- **The models differ on a dimension**: the lower end of the task interval of
  D for the dimension is above 0.

## Sensitivity

**Wording sensitivity** is the shift between the two wordings of a cell
position:

    S_w(t, level, v) = shift(runs of wording A, runs of wording B)

It is one bundled factor (mood, verb, length and, at L2, list against prose);
it is not the effect of any one of them ([leak-check.md](leak-check.md)). It
is reported per level and not compared across levels as if it were one
treatment, because the bundle is wider at L2. When the lower end of the task
interval of S_w for a dimension is above 0, that wording pair is read again
for a hint that sits in one wording only.

**Prompt sensitivity** is the shift between two levels of the same task and
wording, A with A and B with B:

    S(t, v; L -> L') = mean over the wordings of shift(cell at L, cell at L')

for L0 to L1, L1 to L2 and L0 to L2.

**The yardstick.** A shift between levels that is no larger than the shift
between wordings at those levels is not evidence that direction moved the
choice. So the result that is read is the **excess**:

    E(t, v; L -> L') = S(t, v; L -> L')  -  ( S_w(t, L, v) + S_w(t, L', v) ) / 2

The yardstick is the mean of the two wording shifts, not the larger: the
larger of two noisy values is too large on average, the mean is not. E needs
all three shifts. E is cautious on purpose: S already compares like wording
with like, and the wording shift is taken off all the same, so a level
effect has to exceed what a change of phrasing does before it counts.

**Direction moved a dimension** between two levels when the lower end of the
task interval of E for the dimension is above 0. Per variable, E is shown
with its interval but is descriptive: there are 62 variables, and some
intervals exclude 0 by chance.

**What is printed.** For every open variable and every dimension, and each
pair of levels: S with its task interval, the yardstick, and E with its task
interval, side by side. S says how far the choice moved; E says how much of
that is beyond what rewording does. A large S beside an E near 0 is a choice
that moves with the phrasing as much as with the direction, and it takes
both numbers to see that.

**Open and closed.** For a task, a variable counts toward the dimension's
sensitivity between L and L' only if it is open at both. This is the
spill-over: what the brief moved without naming it. L0 to L1 has no closed
variable, so everything counts there.

**Closed variables** are reported one by one, per task, in the directed
table:

- the level shift S and excess E from L0, as above;
- **compliance**, where `expect` is given: the share of runs at that level
  that show an expected value (`in`: the choice is one of the list;
  `absent`: the set holds none of the items; `present`: it holds all of
  them), among the runs that have a value and a verdict. A run whose value
  is listed under `no_verdict` in `features.yaml` has none: `unknown` (a
  font that the table of font categories does not hold) or `default` (the
  page declares nothing, and what shows is the browser's or a framework's).
  Such a run is left out and counted as `no verdict`. It did not disobey; the
  extractor cannot say. An entry of `dictated.yaml` can add values for its
  own case (`no_verdict` beside `in`): a heading that is `same`, the body's
  face, gives no verdict where the brief dictates the heading face and leaves
  the body's open (bakery-landing, todo-app), and is judged where it
  dictates both;
- **persistence**, for a variable with one value per run and an `in` list:
  the share of runs at that level that still show the task's **L0 default**.
  It is read only when both hold:
  1. the task's own L0 table (both wordings, that model) has a single nominal
     top choice d with a clear lead at the task's n_eff;
  2. d is not in the `in` list and is not a `no_verdict` value. If the brief
     asks for what the model does anyway, an unchanged output is obedience,
     not persistence ([leak-check.md](leak-check.md), "Notes for other
     tasks").

  Runs with a `no_verdict` value are left out of persistence as they are out
  of compliance.

Compliance and persistence are pooled over the tasks where they can be read,
with the usual weights, and carry a run interval at their n_eff.

| Reading | Condition | With the pilot's numbers |
|---|---|---|
| the default **persists** under the brief | lower end of the run interval of persistence above 0.10 | 8 of 40 runs or more |
| the default **gave way** | upper end below 0.10 | 0 of at least 35 runs: four tasks |
| undecided | otherwise | everything read on fewer than four tasks |

0.10 is one run in ten, and it is a convention: a default that still shows in
more than one run in ten, against a brief that asks for something else, is
worth reporting. Its consequence is fixed by the interval: none in 34 runs
leaves an upper end of 0.1015, none in 35 gives 0.0989. So "gave way" cannot
be said of one task (10 runs: 0 of 10 leaves 0.28).

## Uncertainty

Five runs per cell are few. Every reported number carries an interval, and
every statement ("default", "differs", "moved") is tied to one.

### Two intervals

**The run interval: what if the same prompts were run again?** The tasks and
wordings are held fixed; the chance is in the runs. For a share p at n_eff
effective runs it is the **Wilson score interval**, with z = 1.96:

    centre = ( p + z^2 / (2 n) ) / ( 1 + z^2 / n )
    half   = z x sqrt( p (1 - p) / n + z^2 / (4 n^2) ) / ( 1 + z^2 / n )
    interval = centre - half  to  centre + half                    n = n_eff

It never leaves 0 to 1, it does not collapse when a share is 0 or 1 (which a
plain "p plus or minus" interval does, and with 5 runs a cell is often
unanimous), and it has a closed form. It treats the pooled runs as n_eff
independent draws. With complete cells the real variance is no larger than
that, because the pooling is stratified by cell, and the interval errs on the
wide side. With unequal cells this is not guaranteed (a small cell that is
split, while the full cells agree, adds more variance than n_eff allows
for), and the interval is an approximation.

**The task interval: what about tasks other than these six?** The six tasks
are a sample of the things people ask for, and runs of the same task are
alike. Runs are **clustered by task**: the task is the unit, and each task
gives one number, the value of the measure for that task (its share p(t,k),
its convergence, its shift, its excess). With T tasks, mean m and standard
deviation s (divisor T - 1):

    interval = m - t x s / sqrt(T)  to  m + t x s / sqrt(T)

where t is the 0.975 point of Student's t with T - 1 degrees of freedom:

| T | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| t | 12.706 | 4.303 | 3.182 | 2.776 | 2.571 | 2.447 | 2.365 | 2.306 | 2.262 | 2.228 | 2.201 |

It needs T of at least 2. Run-to-run noise is inside each task's number, so
this interval covers both sources. For a share it is cut to the range 0 to 1
and then widened, where needed, to contain the run interval: knowing less
about other tasks cannot mean knowing more about these. When every task gives
the same number the interval has no width; that says the tasks agreed, not
that the value is known exactly.

Which is used where:

| Statement | Interval |
|---|---|
| labels of the fingerprint (`leading`, `default`, `strong default`), default items, the stability rule | run interval (through the closed-form conditions) |
| compliance, persistence | run interval |
| convergence, wording shift, level shift, excess, model shift: every value | task interval |
| "holds across tasks" | task support T of T |

### What the pilot can and cannot detect

All figures are for the planned pilot: 5 runs per cell, 10 per task and
level, 60 per model and level, 180 per level over three models.

**About a share (run interval).**

| Runs | Interval around 0.5 | Interval for "all runs" | "None seen" means below | Established majority from | Strong default from |
|---|---|---|---|---|---|
| 10 (one task) | 0.24 to 0.76 | 0.72 to 1 | 0.28 | 9 of 10 | never |
| 30 (three tasks open) | 0.33 to 0.67 | 0.89 to 1 | 0.11 | 21 of 30 | 29 of 30 |
| 60 (a model at a level) | 0.38 to 0.62 | 0.94 to 1 | 0.06 | 38 of 60 | 55 of 60 |
| 180 (three models) | 0.43 to 0.57 | 0.98 to 1 | 0.02 | 104 of 180 | 155 of 180 |

- A clear lead at 60 runs needs, for example, 28 against 15 (27 against 15 is
  not enough). Unanimous runs give a clear lead from 4 runs and a strong
  default from 16.
- When two choices are truly level, the clear-lead rule still names one of
  them in about 5% of cases (simulated: 5.1% for two choices at 60 runs, 4.5%
  with a third choice present). With 62 variables, three models and three
  levels, a few `leading` labels near the limit are wrong. The stability rule
  exists to catch them.

**About two models.** "The models differ" is read from the task interval of
the model shift D. For two models whose shares of a yes/no choice lie d
apart, at 0.5 - d/2 and 0.5 + d/2 in every task, it is declared this often
(simulation, 2,000 to 6,000 draws):

| True difference d | 0 | 10 points | 20 | 26 | 30 | 34 | 40 | 50 | 55 | 60 |
|---|---|---|---|---|---|---|---|---|---|---|
| one variable | under 1% | 1% | 2% | 6% | 11% | 18% | 34% | 66% | 82% | 92% |
| a dimension of five such variables | 1% | 4% | 22% | 50% | 73% | 88% | 98% | 100% | 100% | 100% |

On a single variable two models must differ by about **55 points** to be
told apart four times in five; on a dimension by about **32 points**, if all
its variables differ. A plain comparison of two shares from 60 runs each
would find 26 points four times in five, but that is not the rule used here:
it takes the 60 runs as independent, and runs of one task are alike.

**About tasks.** With six tasks the task interval is the mean plus or minus
1.05 standard deviations of the six task values (2.571 / sqrt(6)). A measure
is shown to be above zero only if its mean exceeds its own task-to-task
standard deviation. And a default holds across tasks only if all six agree.

**About a shift** (simulation, a yes/no choice at share 0.5, 5 runs per cell,
6 tasks, 2 wordings, 5,000 to 20,000 draws):

- with no true shift, the pooled shift of one variable has mean 0.000 and
  standard deviation 0.043 (0.028 at a share of 0.8); for one task alone the
  standard deviation is 0.106;
- the chance that "direction moved it" (lower end of the task interval of E
  above 0) is declared, when the share truly moves from 0.5 to 0.5 + d in
  every task:

| True move d | 0 | 10 points | 20 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|
| one variable | 1% | 2% | 5% | 18% | 50% | 92% |
| a dimension of five such variables | 2% | 6% | 27% | 80% | 100% | 100% |

The five-variable rows of both tables assume five independent variables that
all move by the same amount, and the same five in every task. A real
dimension does worse. Its variables are correlated (six corner and shadow
variables are not six independent looks at a model), only some of them move,
and at L2 the open variables of a dimension differ from task to task (the
table under [Open choices](#open-choices)), which widens the spread of the
task values. The power of a real dimension lies between the two rows.

So the pilot **can** show: defaults with a share of roughly two thirds or
more at a level; whether such a default holds in all six tasks; shifts of a
dimension by about 30 points or more between levels, if most of its
variables move (L0 to L2 on a directed dimension is expected to be far
larger); that a default gave way, on four or more tasks; differences between
models of about 30 points or more across a dimension, or about 55 points on
a single variable.

It **cannot** show: which of two choices leads when they are within 20 to 25
points of each other; a default's share to better than about 12 points either
side; moves of a single variable below about 40 points (so most of what L1
does to single variables); differences between models on a single variable
below about 50 points; anything per task beyond a description (10 runs);
whether a default would hold on tasks unlike these six; and nothing about the
product surface. Across 12 dimensions, 3 pairs of levels and 3 models there
are 108 tests of "direction moved it"; at a false-alarm rate near 2%, two or
three are expected to fire with no true shift. A finding seen in one model
and one pair of levels only is weak.

## The stability rule

The plan's check: **doubling the runs per cell does not change the top
choices in a fingerprint.** Formally, per model:

**Which cells.** All 12 L0 cells of the model (6 tasks x 2 wordings), each
doubled from 5 to 10 runs: 60 more runs per model, 180 for the pilot's three
models, a third of the pilot. L0 because it defines the baseline; all of its
cells because the fingerprint weights every task and both wordings equally,
so a check on fewer cells would test a different table from the one
published. The added runs are run indexes 6 to 10 of the same batch: the
runner, given the same batch id with `--runs 10 --levels L0`, plans run
indexes 1 to 10 and skips those already recorded ([runner.md](runner.md)).

**Which tables.** F5 is the L0 fingerprint from run indexes 1 to 5, F10 from
1 to 10, both by the rules above. The check uses the **primary** variables;
at L0 all are open. A cell must have at least 4 usable runs among the first
five and at least 8 among the ten; if any cell falls short after failed runs
were retried, the verdict is `not run`, with the cells named.

**Reported top choice.** As in [the fingerprint table](#the-fingerprint-table):
the choice with a clear lead (or none), and for a set variable the set of
default items (possibly empty).

**Counted variables.** Those with a reported top choice in F5 or in F10 (for
a set: a non-empty default set in either). A variable that is contested in
both tables is not counted: nothing was claimed and nothing changed.

**Credit** of a counted variable:

- one value per run: 1 if F5 and F10 report the same choice, else 0;
- set: the number of default items in both tables, over the number in either.

**Score** = sum of credits / number of counted variables.

**Reversal.** A claim that the doubled data contradicts:

- one value per run: F5 reports a choice that is not among the choices with
  the largest share in F10;
- set: an item that is a default item in F5 and is held by fewer than half of
  the runs in F10. Each such item is one reversal.

The other ways a counted variable can change are **new** (none reported in
F5, one in F10), and **lost** (reported in F5; in F10 still the largest
share, but no clear lead). All four counts (kept, new, lost, reversed) are
reported.

**Ties.** A tie for the largest share reports no top choice. So a tie in F5
claims nothing, and a tie in F10 that includes F5's choice is `lost`, not a
reversal; a tie in F10 between other choices is a reversal. For a set, an
item held by exactly half of the runs in F10 is not a reversal.

**Growth of established defaults.** Doubling can change a table in two ways
that call for opposite answers: it can uncover defaults that five runs were
too few to show, or it can shuffle claims among choices that are near a tie.
Let E5 be the number of established defaults in F5: the variables with one
value per run whose reported top choice has an established majority, plus
the default items of all set variables. E10 is the same count in F10.

    growth = E10 / E5 - 1
    growth = 0                         when E5 = 0 and E10 = 0
    growth is above any limit          when E5 = 0 and E10 > 0

**Verdict of the check, 5 runs against 10.**

| Verdict | Condition | What happens |
|---|---|---|
| `stable` | score at least **0.90** and at most 1 reversal | 5 runs per cell stand for this model. |
| `unstable: defaults still appearing` | score below 0.90, at most 1 reversal, growth of **0.10** or more | Ten runs report at least a tenth more established defaults than five: more runs are buying defaults. 10 runs per cell for this model. With the Human's approval of the spend, the check is repeated once, 10 against 20 (below). |
| `unstable: contested choices` | score below 0.90, at most 1 reversal, growth below 0.10 | Doubling changed more than one reported top choice in ten, but added few established defaults: the changes are claims won and lost among choices near a tie, and leads without a majority. More runs do not settle these (below), so the run count is not raised on their account: 5 runs per cell stand for this model. The variables that changed are marked `contested` in the pilot report and are not called defaults. |
| `drift suspected` | 2 or more reversals, whatever the score | No recommendation on the run count from this model. Compare run indexes 1 to 5 with 6 to 10 as two groups (the shift per dimension, which should be near 0; the dates; the `model_id_returned` values). If the provider changed the model between the two runs, the model's L0 is run again as a new batch. |
| `no defaults` | no counted variable | Recorded as such; the fingerprint has no top choices to be stable. |
| `not run` | a cell is short of usable runs | Named cells are completed first. |

T1.9 recommends 10 runs per cell for the full grid if any model is
`unstable: defaults still appearing`, and 5 otherwise.

**The repeat, 10 runs against 20.** Only once, only with the Human's
approval, and only for a model whose first verdict was
`unstable: defaults still appearing`. The same 12 cells are doubled again
(120 more runs for the model; a cell needs 8 usable runs among the first ten
and 16 among the twenty). The score, the reversals and the growth are worked
out as above with F10 and F20 in the place of F5 and F10, and the limits are
the same. What follows from them is not, because no third check is made:

| Outcome of the repeat | What happens |
|---|---|
| `stable` | 10 runs per cell stand: twenty runs report what ten did. |
| `unstable: contested choices` | 10 runs per cell stand. The variables that changed are marked `contested` and are not called defaults. |
| `unstable: defaults still appearing` | 10 runs per cell stand all the same, and there is no further repeat. The variables that gained an established default between 10 and 20 runs are listed in the pilot report as **open at 10 runs**, with the growth, so that the Human can decide whether the full grid is worth more than 10. In the simulation this outcome marks a model of weak defaults: 67% of weak models show it at 10 to 20 runs, 5% of mixed ones and 6% of blends. |
| `drift suspected`, `no defaults`, `not run` | As in the first table, with run indexes 1 to 10 compared with 11 to 20. |

Without the repeat, 10 runs per cell stand for that model.

With any verdict, the report lists every counted variable that changed: the
kind of change (new, lost, reversed; for a set, the items gained and
dropped) and whether the choice had an established majority in each of the
two tables. The pilot's L0 tables are computed from all the runs that exist,
ten or twenty, whatever the verdict.

**What the verdict does not cover.** L1 and L2, the per-task tables, the
provisional variables, and the sensitivity measures. They are covered by
their intervals only.

### Check that the rule can pass and can fail

A rule of this kind is useless if it passes almost any data or fails almost
any. It was checked by simulation at the planned sizes (not committed code;
500 simulated models per row, seed 20261126):

- 45 variables with one value per run (2 to 6 choices) and 17 set variables
  (3 to 8 items), the counts in `features.yaml`;
- 6 tasks x 2 wordings, n runs per cell, then n more;
- each task has its own shares, drawn around the model's shares (Dirichlet
  and beta draws with concentration 10, so tasks differ visibly);
- five kinds of model in which every variable is of one kind. *Strong*: the
  top choice of every variable has a true share between 0.75 and 1, items
  are near 0 or near 1. *Fairly strong*: between 0.6 and 1. *Mixed*: between
  0.4 and 1, items anywhere between 0 and 1. *Weak*: shares drawn flat, items
  between 0.3 and 0.7. *No defaults*: all choices equally likely;
- and a **blend**, the likelier case for a real model: each variable is
  strong with chance 0.6, weak with chance 0.2 and without a default with
  chance 0.2 (second simulation, seed 20261127, which also gave the split of
  the unstable verdicts below).

| Model | Runs per cell | Mean score | Middle 90% of scores | `stable` |
|---|---|---|---|---|
| strong | 3 to 6 | 0.994 | 0.967 to 1.000 | 100% |
| strong | **5 to 10** | 0.999 | 0.983 to 1.000 | **100%** |
| strong | 10 to 20 | 1.000 | 1.000 to 1.000 | 100% |
| fairly strong | 3 to 6 | 0.950 | 0.897 to 0.984 | 94% |
| fairly strong | **5 to 10** | 0.974 | 0.931 to 1.000 | **100%** |
| fairly strong | 10 to 20 | 0.991 | 0.966 to 1.000 | 100% |
| mixed | 3 to 6 | 0.869 | 0.795 to 0.940 | 24% |
| mixed | **5 to 10** | 0.898 | 0.829 to 0.955 | **50%** |
| mixed | 10 to 20 | 0.934 | 0.882 to 0.982 | 87% |
| weak | 3 to 6 | 0.702 | 0.589 to 0.809 | 0% |
| weak | **5 to 10** | 0.752 | 0.644 to 0.842 | **0%** |
| weak | 10 to 20 | 0.834 | 0.755 to 0.913 | 9% |
| no defaults | 3 to 6 | 0.359 | 0.133 to 0.625 | 0% |
| no defaults | **5 to 10** | 0.377 | 0.190 to 0.579 | **0%** |
| no defaults | 10 to 20 | 0.495 | 0.333 to 0.658 | 0% |
| blend | 3 to 6 | 0.910 | 0.844 to 0.970 | 62% |
| blend | **5 to 10** | 0.914 | 0.847 to 0.972 | **65%** |
| blend | 10 to 20 | 0.922 | 0.856 to 0.980 | 75% |
| blend | 20 to 40 | 0.927 | 0.869 to 0.979 | 79% |

How the verdicts split (second simulation; no row had two reversals):

| Model | Runs per cell | `stable` | `unstable: defaults still appearing` | `unstable: contested choices` | Median growth |
|---|---|---|---|---|---|
| strong | 5 to 10 | 100% | 0% | 0% | 0.00 |
| fairly strong | 5 to 10 | 100% | 0% | 0% | +0.04 |
| mixed | 5 to 10 | 49% | 30% | 21% | +0.09 |
| mixed | 10 to 20 | 84% | 5% | 11% | +0.06 |
| weak | 5 to 10 | 1% | 96% | 3% | +0.26 |
| weak | 10 to 20 | 9% | 67% | 24% | +0.14 |
| no defaults | 5 to 10 | 0% | 94% | 6% | +0.71 |
| blend | 3 to 6 | 62% | 6% | 32% | +0.04 |
| blend | 5 to 10 | 65% | 12% | 23% | +0.06 |
| blend | 10 to 20 | 75% | 6% | 19% | +0.04 |
| blend | 20 to 40 | 79% | 6% | 15% | +0.05 |

What the figures show:

- **The rule discriminates.** At 5 to 10 runs it passes a model with strong
  or fairly strong defaults every time, fails a model with weak or no
  defaults every time, passes a mixed model half the time and a blend two
  times in three. It neither passes nearly everything nor fails nearly
  everything.
- **The limit of 0.90** sits between the kinds of model: at 0.85 a mixed
  model passes 89% of the time and a weak one 4%; at 0.95 a fairly strong
  model passes only 82% and a mixed one 9%.
- **More runs help some models and not others.** A mixed model, whose
  defaults are of every strength, passes 24% of the time at 3 to 6 runs, 50%
  at 5 to 10 and 87% at 10 to 20: its middling defaults settle as runs are
  added. A blend does not respond: 62%, 65%, 75% and 79% from 3 to 6 up to
  20 to 40 runs. Its strong variables are settled at any run count and its
  contested ones at none, so **a model of this kind can be `unstable` at
  every run count**, one time in five even at 20 to 40 runs. Raising the run
  count for it buys nothing.
- **Growth tells the two apart**, which is why the unstable verdict is split.
  A weak model, which has modest defaults that more runs do bring out, shows
  growth of 0.10 or more in 96% of cases at 5 to 10 runs (median +0.26). An
  unstable blend is `contested choices` two times in three (23% against
  12%), an unstable mixed model `defaults still appearing` three times in
  five (30% against 21%). Stable models grow little: a strong one by 0.02 at
  most, a fairly strong one by 0.09 at most (95th percentiles). A model with
  no defaults at all is sent to 10 runs as well, on a tiny base (8
  established defaults becoming 13, of some 130 possible): with tasks that
  differ, six tasks hold small real majorities that more runs find. The
  repeat at 10 to 20 ends the matter whatever it finds, at 10 runs per cell:
  defaults still appearing there mark a weak model two times in three (67%),
  and a mixed model or a blend about one time in twenty.
- **Reversals do not happen by chance.** Without drift, one reversal occurred
  in at most 1.8% of simulated models and two or more in none of 9,500
  (every row above, and the mixed and fairly strong models again with no task
  effect and with a strong one), nor in any of the 5,500 of the second
  simulation. Allowing one keeps the false alarm rare.
- **Reversals do signal drift.** Drift was simulated by letting the added
  runs of a task come, for each variable with a given chance, from a changed
  model (its choices rotated by one place). At a chance of one half, a mixed
  model shows two or more reversals 40% of the time and is never `stable`; at
  a chance of 1, always. At one in six the change is too small to see (two
  or more reversals in 0.2%), and a strong model hides more: at one half it
  is still `stable` 34% of the time. The check is a coarse alarm for drift,
  not a monitor; the monthly canary (T6.2) is the monitor.

The simulated models are assumptions, not measurements. Which kind the real
models are is what the pilot finds out: the project's premise is that they
are strong.

## Representative outputs

"Example outputs nearest the centre" of a fingerprint are chosen per task,
because outputs of different tasks cannot be laid side by side: one output
per task, six for a model and level.

For a usable run r of a model, task and level, the **pool** is every other
usable run of the same model, task and level (both wordings: up to 9 others).

    typicality of r on a variable v   = mean of a(r, s) over the pool runs s that have a value for v
    typicality of r on a dimension d  = mean over the variables v of d that count
    typicality of r                   = mean over the dimensions that have a value

A variable counts when it is primary, open for that task and level, has a
value in r, and has a value in at least one pool run. Typicality is the share
of the run's choices that the other runs of the same prompt pair make too. It
is the plan's default score, applied to a pilot run against its own
neighbours with the run itself left out.

The **representative output** is the run with the largest typicality. Ties
go to wording A before B, then to the lower run index, then to the smaller
`record_id`. The three most typical runs are listed, with their values; so is
the least typical, as a contrast. A task and level with fewer than 3 usable
runs has no representative output.

## Thresholds

| Threshold | Value | Kind | Where it comes from |
|---|---|---|---|
| Confidence of every interval | 95% (z = 1.96; t at 0.975) | convention | |
| Clear lead, established majority, default item | Wilson lower end above 0.5 | derived | names a level pair in about 5% of cases (simulated 4.5% to 5.1%) |
| Strong default | Wilson lower end above 0.8 | convention | needs 55 of 60, or 16 unanimous runs |
| Insufficient data | T below 3 or n_eff below 16 | convention | keeps a label's meaning the same in every row. 16: least unanimous runs for a strong default; 3: least tasks for a t multiplier under 5 |
| Incomplete outcomes; partly read | more than 10% of runs | derived | the bias it allows (10 points at most) stays under the half-width at 60 runs (12 points) |
| Task-dependent | spread of 0.7 or more | derived | false flag at most 3.3% with 10 runs per task |
| Holds across tasks | support T of T, T at least 5 | derived | chance 1/32 or less; 5 of 6 would be 7/64 |
| Direction moved a dimension; models differ | lower end of the task interval above 0 | derived | false alarm 2.5% per test by construction; simulated 1% to 2% for the excess, about 1% for the model shift |
| Persists / gave way | run interval above / below 0.10 | convention | "gave way" needs 0 of 35 or more |
| Stability score | at least 0.90 | derived | separates strong from weak simulated models; table above |
| Growth that sends a model to 10 runs | 0.10 or more | derived | weak simulated models reach it in 96% of cases, stable ones in under 5%; it splits the unstable blends and mixed models |
| Reversals allowed | 1 | derived | two or more never occurred without drift in 9,500 simulated models |
| Cells complete enough for the stability check | 4 of 5, and 8 of 10 usable | convention | |
| Bin edges, CTA rule minimum of 3 | `features.yaml` | first guess | review after the pilot |

After the pilot (T1.9, T1.10) the conventions and first guesses are reviewed
against the measured tables. A change is a new metrics version.

## Worked examples

Every formula, on inputs small enough to check by hand. T1.6's tests
reproduce these. Fractions are exact; decimals are rounded to four places.

### The example grid E1

One model, level L0, two tasks (t1, t2), two wordings, five runs planned per
cell. Three variables, one per dimension: `corner_style` (categorical),
`libraries` (set) and `gradient_count` (number, bins `[0, 1, 3, 6]`), shown
as the raw count and its bin. Everything is open.

| Cell | Run | `corner_style` | `libraries` | `gradient_count` |
|---|---|---|---|---|
| t1 A | 1 | rounded | tailwindcss | 2: `1-2` |
| t1 A | 2 | rounded | lucide, tailwindcss | 3: `3-5` |
| t1 A | 3 | rounded | tailwindcss | 0: `0` |
| t1 A | 4 | rounded | (empty) | 1: `1-2` |
| t1 A | 5 | pill | lucide, tailwindcss | 7: `6+` |
| t1 B | 1 | rounded | tailwindcss | 0: `0` |
| t1 B | 2 | rounded | (empty) | 0: `0` |
| t1 B | 3 | undetermined (the corners extractor reported `error`) | tailwindcss | 4: `3-5` |
| t1 B | 4 | square | (empty) | 0: `0` |
| t1 B | 5 | rounded | tailwindcss | 2: `1-2` |
| t2 A | 1 | very-rounded | react, tailwindcss | 5: `3-5` |
| t2 A | 2 | very-rounded | react, tailwindcss | 2: `1-2` |
| t2 A | 3 | rounded | tailwindcss | 0: `0` |
| t2 A | 4 | very-rounded | react | 6: `6+` |
| t2 A | 5 | rounded | tailwindcss | 1: `1-2` |
| t2 B | 1 | rounded | tailwindcss | 0: `0` |
| t2 B | 2 | (status `refused`) | | |
| t2 B | 3 | (status `truncated`) | | |
| t2 B | 4 | (status `failed`, never retried) | | |
| t2 B | 5 | (status `ok`, prose only: `no-artifact`) | | |

`libraries` is declared with the empty set as a value, so the three empty
sets count.

### 1. Conversions

- Bins `[0, 1, 3, 6]`: 0 is `0`; 1 and 2 are `1-2`; 3 and 5 are `3-5`; 6 and
  7 are `6+`.
- Coverage of `part` in `whole`: (0, 0) is not applicable; (0, 4) is `none`;
  (2, 4) is `some`; (4, 4) is `all`.
- Ordered list `[header, hero, features, footer]` is the set `^>header`,
  `header>hero`, `hero>features`, `features>footer`, `footer>$`. The empty
  list is the set `^>$`.
- Count-map `{cta-get-started: 2, cta-learn-more: 3, placeholder-lorem-ipsum: 1}`
  with the minimums of `features.yaml` is the set `cta-learn-more`,
  `placeholder-lorem-ipsum`.
- Mask: a run with `css_framework: bootstrap` has `corner_style`
  undetermined, whatever the extractor stored; a run with
  `css_framework: tailwindcss` keeps it.

### 2. Outcomes (E1)

Cell t2 B has four selected records (the failed one has no run): `artifact`,
`refused`, `truncated`, `no-artifact`, a quarter each. Every other cell is
all `artifact`.

- task t1: artifact 1. Task t2: artifact (1 + 1/4) / 2 = 5/8; the other
  three 1/8 each.
- fingerprint: artifact (1 + 5/8) / 2 = **13/16**; `refused`, `truncated`,
  `no-artifact` **1/16** each. N = 19, n_eff = 320/17 = 18.8235.
- 3/16 = 0.1875 of the runs are not `artifact`: above 0.10, so the
  fingerprint is flagged `incomplete outcomes`.

### 3. Shares, weights and labels: `corner_style` (E1)

| Cell | n | Shares |
|---|---|---|
| t1 A | 5 | rounded 4/5, pill 1/5 |
| t1 B | 4 (one undetermined) | rounded 3/4, square 1/4 |
| t2 A | 5 | rounded 2/5, very-rounded 3/5 |
| t2 B | 1 | rounded 1 |

- task t1: rounded (4/5 + 3/4) / 2 = 31/40; pill 1/10; square 1/8.
- task t2: rounded (2/5 + 1) / 2 = 7/10; very-rounded 3/10.
- fingerprint: rounded (31/40 + 7/10) / 2 = **59/80 = 0.7375**; very-rounded
  **3/20**; square **1/16**; pill **1/20**. They sum to 1.
- N = 15, T = 2. Weights: 1/20 for each run of t1 A and t2 A, 1/16 for each
  of t1 B, 1/4 for the run of t2 B. Sum of squares: 5/400 + 4/256 + 5/400 +
  1/16 = 33/320. **n_eff = 320/33 = 9.6970.** One run carries a quarter of
  the weight, and 15 runs are worth fewer than 10.
- run intervals: rounded 0.4262 to 0.9140; very-rounded 0.0347 to 0.4639;
  square 0.0077 to 0.3656; pill 0.0051 to 0.3503.
- top choice: x1 = 0.7375 x 9.6970 = 7.1515 (rounded), x2 = 0.15 x 9.6970 =
  1.4545 (very-rounded). Clear lead: (x1 - x2)^2 = 32.4555 against 3.8416 x
  8.6061 = 33.0610: **no**. Established majority: (2 x 7.1515 - 9.6970)^2 =
  21.2158 against 3.8416 x 9.6970 = 37.2519: no. Evidence: contested.
- label: **`insufficient data`** (T = 2 is below 3 and n_eff is below 16).
  Nominal top `rounded`; no reported top choice.
- 1 of 16 usable runs is undetermined, with weight 1/20 in a pooling over all
  16 (t1 B then has 5 runs): 0.05, not above 0.10, so not `partly read`.

### 4. A set variable: `libraries` (E1)

| Cell | n | Share of runs holding each item |
|---|---|---|
| t1 A | 5 | tailwindcss 4/5, lucide 2/5 |
| t1 B | 5 | tailwindcss 3/5 |
| t2 A | 5 | tailwindcss 4/5, react 3/5 |
| t2 B | 1 | tailwindcss 1 |

- fingerprint: tailwindcss ((4/5 + 3/5)/2 + (4/5 + 1)/2) / 2 = (7/10 + 9/10)
  / 2 = **4/5**; react (0 + 3/10) / 2 = **3/20**; lucide (1/5 + 0) / 2 =
  **1/10**. The shares do not sum to 1.
- N = 16, n_eff = 1 / (15/400 + 1/16) = **10**.
- default item? tailwindcss: x = 8; (2 x 8 - 10)^2 = 36 against 3.8416 x 10 =
  38.416: **no**. The default set is empty (and the row is `insufficient
  data` in any case).

### 5. A number variable: `gradient_count` (E1)

- cell shares: t1 A `0` 1/5, `1-2` 2/5, `3-5` 1/5, `6+` 1/5; t1 B `0` 3/5,
  `1-2` 1/5, `3-5` 1/5; t2 A as t1 A; t2 B `0` 1.
- fingerprint: `0` **1/2**; `1-2` **1/4**; `3-5` **3/20**; `6+` **1/10**.
  N = 16, n_eff = 10.
- nominal top `0`: x1 = 5, x2 = 2.5; (2.5)^2 = 6.25 against 3.8416 x 7.5 =
  28.812: no clear lead.

### 6. Missing data

- **One run.** Cell t2 B has one usable run. Its share is 1 for whatever it
  chose, it has no convergence (no pair of runs), and any shift involving it
  is undefined; `cross` with another cell is defined. A fingerprint of one
  run has n_eff = 1: x1 = 1, x2 = 0, and 1 is not above 3.8416, so one run
  never makes a default.
- **A cell with no value.** If the single run of t2 B were undetermined for
  `corner_style`, the cell is dropped and t2 rests on wording A: t2 rounded
  2/5; fingerprint rounded (31/40 + 2/5) / 2 = **47/80 = 0.5875**,
  very-rounded 3/10, square 1/16, pill 1/20. Weights: 1/20 (t1 A), 1/16
  (t1 B), 1/10 (t2 A); sum of squares 5/400 + 4/256 + 5/100 = 5/64;
  **n_eff = 64/5 = 12.8**, N = 14.
- **All missing.** A variable with no value in any usable run has no row
  shares: N = 0, T = 0, label `insufficient data`, and it is skipped by every
  average.
- **A tie.** A row with shares a 1/2 and b 1/2 (at any n_eff): nominal top
  `[a, b]`; x1 - x2 = 0, so no clear lead; label `contested`; no reported top
  choice.

### 7. Intervals and labels with six tasks: E2

A variable with one value per run, complete cells of 5 runs, counts of
(indigo, blue, none) per cell:

| Task | Wording A | Wording B | Task share of indigo | of blue | of none |
|---|---|---|---|---|---|
| t1 | 5, 0, 0 | 4, 1, 0 | 9/10 | 1/10 | 0 |
| t2 | 4, 1, 0 | 5, 0, 0 | 9/10 | 1/10 | 0 |
| t3 | 3, 2, 0 | 4, 0, 1 | 7/10 | 1/5 | 1/10 |
| t4 | 5, 0, 0 | 3, 1, 1 | 4/5 | 1/10 | 1/10 |
| t5 | 1, 4, 0 | 2, 3, 0 | 3/10 | 7/10 | 0 |
| t6 | 4, 1, 0 | 4, 0, 1 | 4/5 | 1/10 | 1/10 |

- shares: indigo **11/15 = 0.7333** (44 of 60), blue **13/60 = 0.2167**, none
  **1/20**. N = 60, T = 6, n_eff = 60.
- run intervals: indigo 0.6099 to 0.8287; blue 0.1312 to 0.3362; none 0.0171
  to 0.1370.
- task interval of indigo: the six task shares have mean 0.7333 and standard
  deviation 0.2251; 2.571 x 0.2251 / sqrt(6) = 0.2363; **0.4971 to 0.9696**.
  It contains the run interval, so it stands.
- task interval of blue: mean 0.2167, standard deviation 0.2401: -0.0354 to
  0.4687, cut to **0 to 0.4687**.
- task interval of none: mean 0.05, standard deviation 0.0548: -0.0075 to
  0.1075, cut to 0 to 0.1075, then widened to contain the run interval:
  **0 to 0.1370**.
- label: x1 = 44, x2 = 13. Established majority: (88 - 60)^2 = 784 against
  3.8416 x 60 = 230.496: yes. Strong: the lower end 0.6099 is not above 0.8.
  **`default`**, reported top choice `indigo`.
- task support: indigo is the top choice of t1, t2, t3, t4 and t6, not of t5:
  **5/6**. It does not "hold across tasks".
- task spread: 9/10 - 3/10 = **3/5**. Below 7/10: not `task-dependent`.

Label limits at 60 runs: 37 of 60 is no established majority (lower end
0.4902), 38 of 60 is (0.5068); 54 of 60 is not strong (0.7985), 55 of 60 is
(0.8193).

### 8. Agreement and convergence (E1)

Cell t1 A:

- `corner_style`: four rounded, one pill. Pairs that agree: 4 x 3 / 2 = 6
  of 10. **C = 3/5.** By the formula: (4 x 3 + 1 x 0) / (5 x 4) = 12/20.
- `libraries`, runs 1 to 5: {tailwindcss}, {lucide, tailwindcss},
  {tailwindcss}, {}, {lucide, tailwindcss}. Agreements: (1,2) 1/2; (1,3) 1;
  (1,4) 0; (1,5) 1/2; (2,3) 1/2; (2,4) 0; (2,5) 1; (3,4) 0; (3,5) 1/2;
  (4,5) 0. Sum 4, over 10 pairs: **C = 2/5.**
- `gradient_count`: bins `1-2`, `3-5`, `0`, `1-2`, `6+`. One agreeing pair of
  10: **C = 1/10.**

Two ordered lists: `[header, hero, features, footer]` and `[header, hero,
pricing, footer]` share the pairs `^>header`, `header>hero`, `footer>$`, of 7
pairs in all: agreement **3/7**.

All cells:

| Variable | t1 A | t1 B | t2 A | t2 B | Task t1 | Task t2 | C |
|---|---|---|---|---|---|---|---|
| `corner_style` | 3/5 | 1/2 (4 runs: 3 of 6 pairs) | 2/5 | none | 11/20 | 2/5 | **19/40 = 0.4750** |
| `libraries` | 2/5 | 2/5 | 1/2 | none | 2/5 | 1/2 | **9/20 = 0.4500** |
| `gradient_count` | 1/10 | 3/10 | 1/10 | none | 1/5 | 1/10 | **3/20 = 0.1500** |

Each variable is the only one of its dimension here, so the dimension values
are the same. Overall: task t1 (11/20 + 2/5 + 1/5) / 3 = 23/60; task t2
(2/5 + 1/2 + 1/10) / 3 = 1/3; **C = (23/60 + 1/3) / 2 = 43/120 = 0.3583.** Task
interval with T = 2: standard deviation 0.0354; 12.706 x 0.0354 / sqrt(2) =
0.3177; 0.0407 to 0.6760. Two tasks say almost nothing.

Six tasks (E2): the convergence of the six tasks is 4/5, 4/5, 1/2, 13/20,
1/2, 3/5 (t3: wording A has counts 3, 2: (6 + 2) / 20 = 2/5; wording B has 4,
0, 1: 12/20 = 3/5; mean 1/2). Mean **0.6417**, standard deviation 0.1357,
task interval **0.4992 to 0.7841**.

### 9. Shift: wordings, levels, excess

`corner_style`, task t1. L0 cells as in E1. At L2 the variable is closed for
t1 (`expect: {in: [square]}`); L2 wording A has square, square, square,
square, rounded; L2 wording B has five square.

- within: L0 A 3/5; L0 B 1/2; L2 A 3/5; L2 B 1.
- **wording shift at L0**: cross(A, B) = share of rounded in A x in B = 4/5 x
  3/4 = 3/5 (no other choice is in both). shift = (3/5 + 1/2) / 2 - 3/5 =
  **-1/20**. A negative value: the two wordings are as alike as two samples
  of one prompt; it is kept as it is.
- **wording shift at L2**: cross = 4/5 x 1 = 4/5; shift = (3/5 + 1) / 2 - 4/5
  = **0**.
- **level shift L0 to L2, wording A**: cross = rounded 4/5 x 1/5 = 4/25;
  shift = (3/5 + 3/5) / 2 - 4/25 = **11/25**.
- **wording B**: cross = square 1/4 x 1 = 1/4; shift = (1/2 + 1) / 2 - 1/4 =
  **1/2**.
- **S(t1; L0 -> L2)** = (11/25 + 1/2) / 2 = **47/100**.
- **excess** = 47/100 - (-1/20 + 0) / 2 = 47/100 + 1/40 = **99/200 = 0.495**.

A set variable, `libraries`, wording shift at L0 in t1: within A 2/5, within
B 2/5 (sets {tailwindcss}, {}, {tailwindcss}, {}, {tailwindcss}: agreeing
pairs 3 + 1 of 10), cross 11/25 (of the 25 pairs, 6 agree fully, 6 agree by
half and 2 are both empty: 6 + 3 + 2 = 11). shift = 2/5 - 11/25 = **-1/25**.

Six tasks (E2), wording shift per task: 0, 0, 1/50, 1/20, -3/50, -1/25. Mean
**-0.0050**, standard deviation 0.0399, task interval **-0.0469 to 0.0369**:
no sign of a wording effect.

One-run cell: shift(t2 A, t2 B) for `corner_style` is undefined (t2 B has no
pair); cross(t2 A, t2 B) = 2/5.

**"Direction moved a dimension."** Two sets of six task values of the excess
E with the same mean:

- 3/10, 1/10, 1/4, 1/20, 1/5, 3/10: mean 0.2000, standard deviation 0.1049;
  2.571 x 0.1049 / sqrt(6) = 0.1101; task interval **0.0899 to 0.3101**. The
  lower end is above 0: direction moved the dimension.
- 1/2, -1/20, 0, 3/5, -1/10, 1/4: mean 0.2000, standard deviation 0.2983;
  task interval **-0.1131 to 0.5131**. Not shown: two tasks carry the whole
  mean.

### 10. Compliance and persistence

Same data, task t1, `corner_style` closed at L2 with `in: [square]`.

- task t1's L0 table: rounded 31/40, square 1/8, pill 1/10; weights 1/10 (5
  runs of A) and 1/8 (4 runs of B); n_eff = 1 / (5/100 + 4/64) = 80/9 =
  8.8889. x1 = 6.8889, x2 = 1.1111 (square). (x1 - x2)^2 = 33.3827 against
  3.8416 x 8 = 30.7328: **clear lead**. The L0 default of t1 is `rounded`,
  and `rounded` is not in the `in` list: persistence can be read.
- L2 table of t1: square (4/5 + 1) / 2 = 9/10; rounded 1/10; n_eff = 10.
- **compliance** = **9/10**, run interval 0.5958 to 0.9821.
- **persistence** = **1/10**, run interval 0.0179 to 0.4042. The interval
  spans 0.10: **undecided**, as it always is on one task.

If the `in` list were `[square, rounded]`, or if t1's L0 table had no clear
lead, persistence would not be read for t1.

A set variable: `font_sources` closed with `absent: [google-fonts,
bunny-fonts]`. One cell of five runs: {google-fonts}, {}, {}, {self-hosted},
{}. Four hold none of the listed items: compliance in the cell **4/5**. With
`present: [self-hosted]` it would be 1/5. A set has no persistence.

No verdict: `heading_category` closed with `in: [sans, display]`, and
`unknown` declared as a `no_verdict` value. One cell of five runs: sans,
display, unknown, serif, sans. The unknown run is left out; three of the
other four show an expected value: compliance in the cell **3/4**, not 3/5,
with one run counted as `no verdict`. If the entry adds `no_verdict: [same]`
and the cell is sans, same, unknown, serif, same, two runs are judged and
one of them complies: **1/2**, with three runs counted as `no verdict`.

### 11. Two models

Cell t1 A at L0. Model m1 as in E1 (rounded 4, pill 1). Model m2: pill, pill,
pill, rounded, rounded.

- within: m1 3/5; m2 (3 x 2 + 2 x 1) / 20 = 2/5.
- **cross-model agreement** X = rounded 4/5 x 2/5 + pill 1/5 x 3/5 = **11/25**.
- **model shift** D = (3/5 + 2/5) / 2 - 11/25 = **3/50 = 0.06**.

For comparison, half the squared distance between the two tables of shares is
((4/5 - 2/5)^2 + (1/5 - 3/5)^2) / 2 = 4/25 = 0.16. That figure is what the
shift would be if 5 runs gave the true shares; it is too large by the
run-to-run noise, which `shift` removes.

### 12. The stability rule

Three tasks x two wordings, complete cells: 30 runs at 5 per cell, 60 at 10.
Counts of the two largest choices in F5 and in F10 (shares are counts over 30
and 60, n_eff is 30 and 60; z^2 x 30 = 115.248, and the clear-lead limit is
z^2 x (x1 + x2)):

| Variable | F5 | Clear lead in F5 | F10 | Clear lead in F10 | Result | Credit |
|---|---|---|---|---|---|---|
| v1 | a 24, b 6 | 324 > 115.248: a | a 45, b 15 | 900 > 230.496: a | kept | 1 |
| v2 | a 17, b 13 | 16: none | a 40, b 20 | 400 > 230.496: a | new | 0 |
| v3 | a 22, b 8 | 196 > 115.248: a | a 29, b 31 | 4: none; top is b | **reversal** | 0 |
| v4 | a 15, b 15 | tie: none | a 29, b 31 | 4: none | not counted | |
| v5 | a 22, b 8 | 196 > 115.248: a | a 35, b 25 | 100: none; top is a | lost | 0 |
| v6 (set) | tailwindcss 26, lucide 19, react 6 | tailwindcss (484 > 115.248); lucide 64: no | tailwindcss 50, lucide 40, react 13 | tailwindcss (1600), lucide (400 > 230.496) | default sets {tailwindcss} and {lucide, tailwindcss} | 1/2 |

Counted variables: v1, v2, v3, v5, v6. **Score = (1 + 0 + 0 + 0 + 1/2) / 5 =
3/10.** Reversals: 1.

Established defaults (with two choices, a clear lead is an established
majority): in F5 the choices of v1, v3 and v5 and one default item, **E5 =
4**; in F10 the choices of v1 and v2 and two default items, **E10 = 4**.
**Growth = 4/4 - 1 = 0.**

Verdict: **`unstable: contested choices`** (score below 0.90, one reversal,
growth below 0.10): two defaults came and two went. Had v5 kept an
established majority in F10, E10 would be 5, growth 1/4, and the verdict
`unstable: defaults still appearing`. Had v5 instead ended with b on top,
there would be 2 reversals and the verdict `drift suspected`. With no
established default in either table (E5 = E10 = 0), growth is 0.

Read as the repeat (the same counts for F10 and F20), the outcome is again
`unstable: contested choices`, and it means: 10 runs per cell stand.

### 13. Representative output

Task t1 at L0 in E1: ten usable runs. Dimensions: corners-shadows, libraries,
gradients, one variable each. For run 1 of wording A (rounded; {tailwindcss};
`1-2`):

- `corner_style`: 8 pool runs have a value (run 3 of B does not); 6 are
  rounded: 3/4.
- `libraries`: agreements with the 9 others: 1/2, 1, 0, 1/2 (A2 to A5), 1, 0,
  1, 0, 1 (B1 to B5): sum 5: 5/9.
- `gradient_count`: 2 of 9 others are `1-2` (A4, B5): 2/9.
- typicality = (3/4 + 5/9 + 2/9) / 3 = **55/108 = 0.5093**.

| Run | corners | libraries | gradients | Typicality |
|---|---|---|---|---|
| A1 | 3/4 | 5/9 | 2/9 | 55/108 = 0.5093 |
| A2 | 3/4 | 7/18 | 1/9 | 5/12 = 0.4167 |
| A3 | 3/4 | 5/9 | 1/3 | **59/108 = 0.5463** |
| A4 | 3/4 | 2/9 | 2/9 | 43/108 = 0.3981 |
| A5 | 0 | 7/18 | 0 | 7/54 = 0.1296 |
| B1 | 3/4 | 5/9 | 1/3 | **59/108 = 0.5463** |
| B2 | 3/4 | 2/9 | 1/3 | 47/108 = 0.4352 |
| B3 | (no value) | 5/9 | 1/9 | 1/3 = 0.3333 |
| B4 | 0 | 2/9 | 1/3 | 5/27 = 0.1852 |
| B5 | 3/4 | 5/9 | 2/9 | 55/108 = 0.5093 |

A3 and B1 tie at 59/108. Wording A goes first: the representative output is
**A3**. The three most typical: A3, B1, A1 (A1 and B5 tie at 55/108; A
first). The least typical: A5. B3 has no value for `corner_style`, so its
typicality is the mean of two dimensions.

### 14. Closed by dependence

With `depends_on` chains a <- b <- c (b depends on a, c on b): closing a
closes b and c; closing b closes c and leaves a open; closing c closes
nothing else.

From the two data files, prompt set version 1, level L2. Primary and
provisional variables that no entry lists and that are closed all the same:

| Task | Closed by dependence alone |
|---|---|
| bakery-landing | `font_sources`, `system_stack` (the heading face is dictated); `mechanisms` (through `dark_mode`) |
| pricing-page | `mechanisms` |
| portfolio | `gradient_hues` (the palette); `libraries` (through `icon_libraries`); `mechanisms` |
| event-page | `gradient_hues`; `libraries`; `mechanisms` |
| todo-app | `font_sources`, `system_stack`; `mechanisms` |
| dashboard | `gradient_hues`; `tailwind_breakpoints` (through `css_framework`); `mechanisms` |

At L0 and L1 nothing is closed, by an entry or by dependence.

## Notes for T1.6

- Read `features.yaml` and `dictated.yaml`; hard-code no feature name, bin,
  mask or dictated entry. Refuse, with a message, on: a feature in a record
  that is not declared; a declared extractor missing from a usable run or at
  another version; a `prompt_set_version` other than the one in
  `dictated.yaml`; a number below its first bin edge; records of more than
  one `settings` value in one table.
- A variable is closed for a task and level when an entry of
  `dictated.yaml` lists it or when it depends, in any number of steps, on
  one that is closed. Work this out from the files; the table of example 14
  and the table under "Open choices" are tests of it.
- Compliance and persistence leave out runs with a `no_verdict` value and
  count them.
- Keep shares, agreements and shifts as exact fractions
  (`fractions.Fraction`) until they are written out. Ties, the 0.7 and 0.90
  limits and "fewer than half" are decided on fractions; the clear-lead,
  majority and strong conditions, which involve z, on floats.
- Every table states its metrics version, the extractor versions, the batch
  group, the dates and the counts N, T and n_eff behind each row.
- The tests reproduce every bold figure of the worked examples, and the
  intermediate values given with them.
- The stability check is a command that takes a record file and a model and
  prints the score, the four counts, E5, E10 and the growth, the verdict,
  and the variables that changed with the kind of change. It takes the two
  run counts to compare (5 and 10, or 10 and 20) and says which of the two
  tables of outcomes applies.
- T4.1 designs the default score of a real artifact. Nothing here fixes it;
  typicality is its nearest relative and may be reused.
