# Rubrics

A rubric is the fixed list of multiple-choice questions that a tagging model
answers about one output (task T2.4 in [tasks.md](../tasks.md)). It is layer 2
of [plan.md](../plan.md), "Turning runs into fingerprints": the deterministic
extractors read what code can read, and the rubric covers the choices that
need reading, such as which method was used or which assumptions were stated.

This page gives the format, the reasons for it, the items of each type, the
versioning rule, and how T2.5 should calibrate the tagger. Nothing here calls
a model: the tagger is T2.6.

Contents: [files](#files) · [format](#format) · [answers](#answers) ·
[from answers to variables](#from-answers-to-variables) ·
[design rules](#design-rules) · [guards against tagger bias](#guards-against-tagger-bias) ·
[the split with the extractors](#the-split-with-the-extractors) ·
[the items](#the-items) · [size](#size) · [website](#website) ·
[what a prompt dictates](#what-a-prompt-dictates) · [versioning](#versioning) ·
[calibration](#calibration-t25) · [notes for later tasks](#notes-for-later-tasks) ·
[checks](#checks)

## Files

| File | Holds |
|---|---|
| `rubrics/<type>.v<N>.yaml` | The rubric: instructions, items, options, examples. `pipeline`, `math`, `engineering` and a small `website`, all at version 1 |
| `rubrics/<type>.v<N>.dictated.yaml` | Its companion: which items each prompt takes out of the model's hands |
| [tagger/rubric.py](../tagger/rubric.py) | Loader and validator for both, and three helpers for T2.6 and T1.6 |
| [tests/test_rubrics.py](../tests/test_rubrics.py) | Checks of the real files, and one test per fault the validator refuses |

## Format

```yaml
schema_version: 1
project_type: pipeline          # equals the type in the file name
rubric_version: "1"             # equals the N in the file name; text, so quote it
prompt_set_versions:            # every task of the type, and the version of
  csv-to-database: "1"          # the prompt texts the rubric was read against
instructions:                   # given to the tagger before the items
  - Answer from the response alone. ...
gate:                           # the first item asked; see "Answers"
  item: response_mode
  no_solution: [asks-first, declines]
dimensions:                     # the unit of every summary (docs/metrics.md)
  robustness: What the code does when input or a service fails
items:
  - id: rerun_behavior          # stable; the feature name the tag is stored under
    dimension: robustness
    question: What happens to what an earlier run stored when the same input is processed again?
    select: single              # single | multi
    order: shuffle              # shuffle (default) | scale
    applies_to:
      tasks: [csv-to-database, daily-api-fetch, image-resize]   # or all
      levels: all                                               # or a list
    absent: always-present      # single-select: the option that means "not
                                # present", or always-present
    tie_rule: ...               # optional: which option when two fit
    guidance: ...               # optional: what to look at
    task_notes:                 # optional: what the question means for a task
      image-resize: What is stored is the resized image files. ...
    options:
      - id: adds-again
        definition: The same data is stored a second time ...
        example: "Rows are written with plain INSERT statements into a table that has no key."
    cannot_tell:
      when: The storing step is a call whose behaviour on a repeat the response does not show.
      example: "'db.save(rows)', where db is a class that is not delivered."
    not_applicable:             # or the word never
      when: The code stores nothing. It only prints or returns its results.
      example: "The script prints the cleaned rows to the screen and writes nowhere."
```

A multi-select item has no `absent`; it has `none_example`, an output in
which no option applies, and an `other` option unless it declares
`complete: true` (its options cover every case). An item with a `several` or
`both` option must have a `tie_rule` that says when that option applies.
Unknown keys and repeated keys are errors. Item ids
are lower-case with underscores, like feature names; option ids are
lower-case with hyphens, like feature values.

## Answers

Every item has a closed set of answers:

| Answer | Meaning | In the file |
|---|---|---|
| An option | The response shows this. Options of a single-select item exclude each other; where two could fit, the item's `tie_rule` decides | `options` |
| "Not present" | The tagger looked and the response does not have the thing. This is a value, as `0`, `false` and `"none"` are for an extractor | Single-select: the option named by `absent`. Multi-select: the reserved answer `none`, alone |
| `cannot-tell` | The response has the thing, or may have it, but does not show enough to choose (a helper that is not delivered, a table cut short). Each item says when | `cannot_tell.when` |
| `not-applicable` | The thing the item describes does not exist in this response, in the one case the item names (a question about code, and the response has no code). An item that always applies says `never` | `not_applicable.when` |

Every answer of every item has an invented example: each option, `none`,
`cannot-tell` and, where it can occur, `not-applicable`. The validator
refuses an item with a missing example, and one whose two answers share an
example.

**The gate.** The first item, `response_mode`, asks what the response does
with the request: `answers`, `answers-and-asks`, `asks-first` or `declines`.
With `asks-first` or `declines` there is no solution to read, so no other
item is asked. Such a run is counted in the outcome table
([metrics.md](metrics.md), "Which runs count") and in no other table, as a
website run without a page is. A `cannot-tell` at the gate stops the same way, and the
run is left out as unread (`Rubric.stops_at_gate`). Asking instead of assuming is itself a choice
the prompt leaves open, and at L0 it may be a common one for the tasks with
no givens ("Design a compression spring").

**Applicability** has two layers. `applies_to` is fixed by the task: an item
about retries is asked only for the task that calls an API. `not-applicable`
is decided per response, by the tagger, for the case the item names.

## From answers to variables

Tags are stored as features of the extractor `rubric.<type>`, at version
`<rubric version>@<tagger model id>`, with the item id as the feature name
([record-format.md](record-format.md)). Stored this way they are counted by
the formulas of [metrics.md](metrics.md) with no new rule:

| Item | Variable type | Stored value | State in the metrics |
|---|---|---|---|
| single-select | categorical | the option id | value |
| | | `"not-applicable"` | not applicable (declared under `not_applicable`) |
| | | `null` | undetermined (`cannot-tell`) |
| multi-select | set | the sorted list of option ids | value |
| | | `["none"]` | value: the one item `none` |
| | | `[]` | not applicable (declared `empty: not-applicable`) |
| | | `null` | undetermined (`cannot-tell`) |

`["none"]` is used and not `[]` so that "looked, and none applies" and "not
applicable" stay apart in a set, where `features.yaml` has only the empty
list to mark the second. Two runs that both answer `none` agree fully, and a
run with `none` shares nothing with a run that has an option, exactly as two
empty sets and an empty and a non-empty set do under the Jaccard measure.

`tagger.rubric.variable_declarations(rubric)` writes these declarations in
the form `features.yaml` uses, and `Rubric.check_value` refuses a stored
value that is not in the table. Every rubric variable starts with the role
`provisional` (computed and shown, but outside summaries and the stability
verdict), because a model read it. Calibration and the Human review of tags
(T2.5, T2.11) promote it to `primary` or leave it.

## Design rules

1. **Answerable from the response alone.** The tagger is not shown the
   prompt. Every question asks about something visible in the response ("does
   the response say which assumptions it made"), never about the gap between
   prompt and response ("did it follow the brief"). Whether a brief was
   followed is worked out afterward, from the tag and the companion file.
2. **Facts, not judgements.** Options describe what is there: "a labelled
   list of assumptions", not "assumptions handled well". The validator
   refuses a list of judging words (`correct`, `proper`, `clear`, `robust`,
   `thorough` and others) in questions, definitions, tie rules and guidance.
3. **Choice is separate from correctness.** No item asks whether an answer,
   a formula or a design is right. That is the answer checker's job (T2.10),
   against [checker/references/](../checker/references/README.md). The
   instructions say so: a wrong formula that is applied is still the formula
   that was used. The reference files hold some pass criteria with text only,
   which need a reader; those belong to the checker and are not rubric items.
4. **One question per item.** A question has one question mark, and an item
   that would ask two things is two items (`safety_margin` asks whether a
   margin is stated; the size of the factor is the extractor's).
5. **A closed set with a rule for every corner.** Single-select options
   exclude each other; an `other` or `several` option closes a set that is
   not complete by itself; a tie rule says which option wins where two fit.
   A question that cannot be given one answer per response is multi-select,
   and every multi-select item has an `other` option, so that something
   outside the list is recorded and not lost in `none`. The validator
   requires both: `other` on a multi-select item (or `complete: true`), and
   a tie rule beside a `several` or `both` option.
6. **Delivered, not suggested.** "You could also add retries" is not a
   retry. This keeps a response that lists options from being tagged as
   having all of them.
7. **Small enough for a small model.** At most 9 options per item (most have
   3 to 5), and the first or the last thing in a response where the whole
   could not be judged the same way twice (`opening`, `closing`).
8. **The same item means the same in every type.** `response_mode`,
   `result_form`, `opening`, `closing`, `assumptions_stated` and
   `answer_position` are shared. Their questions, options, definitions and
   rules are identical in every rubric that has them (a test checks it), so
   they can be compared across types. Only the examples differ.

Multi-select is used where a response commonly does several things at once
(the cleaning steps applied, the checks carried out, the forms in which a
curve is shown). A forced single answer there would be decided by the
tagger's taste, which is what the rubric must not measure. Twelve of the 70
item definitions are multi-select.

## Guards against tagger bias

T2.5 uses Claude models as taggers, and Claude models are among the models
under test. The rubric guards against a tagger favoring a style:

- **Blind tagging.** The tagger is not told which model wrote the response,
  nor the prompt or its level. T2.6 must not pass the model id, and should
  strip a self-identifying line only if the pilot shows models write one.
- **No option is the better one.** Options name behaviors, not qualities. No
  option id or definition uses a judging word, and none describes one model
  family's habits as a category of its own: a chatty opener is
  `acknowledgement` whoever wrote it.
- **No model or provider name** appears anywhere in a rubric, examples
  included. The validator refuses a list of them.
- **Length, layout and confidence do not count.** The instructions say so.
  Headings, bullets, length and emphasis are left to the extractors, which
  cannot be impressed.
- **Option order.** A model asked a multiple-choice question leans toward
  the first options. Three rules:
  1. In the file, the options of an item are in alphabetical order of id, so
     the order never reflects which answer the author expected. The
     validator checks it. A `scale` item (`none`, `in-passing`, `listed`) is
     in its natural order.
  2. When an item is shown to the tagger, its options are shuffled per
     output: `tagger.rubric.presentation_order(rubric, item, record_id)`.
     The order depends only on the rubric name, the item and the record id,
     so the same output always sees the same order and repeat tagging stays
     repeatable. A `scale` item is shown in its order or reversed, never
     scrambled. Over many outputs every option is first about equally often
     (a test checks it), so a lean toward a position adds noise but no
     direction.
  3. The reserved answers (`none`, `cannot-tell`, `not-applicable`) come
     after the options, always in the same place: they are fallbacks, and a
     fallback listed first would be chosen too often.
- **A cross-family check.** T2.5 tags a sample with a non-Claude model.
  [Calibration](#calibration-t25) says what to compare.

## The split with the extractors

A choice goes to an extractor (T2.8) when code can read it reliably, and to
the rubric when it takes reading. Where both could, the extractor has it:
it is free, repeatable and cannot be biased.

| Type | Left to the extractors | Read by the rubric |
|---|---|---|
| **Pipeline** | Language; libraries and imports; single script or modules, file layout and names; tests present; logging library or print; a retry present (keyword); configuration sources (arguments, environment, config files); where a key is read from; comment and docstring counts; a README file present; the build service, triggers and test matrix of a CI file; orientation and metadata handling and parallel work in image code (keywords and imports); output formats written; headings, lists, code blocks and length of the reply | What happens to bad input; what a second run does; the kind of storage; the retry's waiting rule; what is done about a missed day; how it is scheduled; where field names come from; sample data supplied; the log format assumed; cleaning steps; proportions on resize; kinds of CI check; where validation rules live and how failure is signalled; how the user is told to run it |
| **Math or science** | Units; significant figures and decimals; notation (LaTeX, Unicode, plain); code present and its language; plotting code present; named methods and constants as keywords (a Ka value, "Shapiro"); a formula present; currency symbol; headings, tables, word count; pronouns (second person, "we") | Closed-form or stepwise; where the numbers come from (worked in text, code with or without results); where the result sits; whether it is verified; assumptions stated; the drag law; the test the conclusion rests on, its level and what is done about normality; the route to the fit and what is reported with it; how much of a schedule or curve is shown; how payments are rounded; framings and pictures of an explanation |
| **Engineering** | Unit system; the value of a safety factor; standards cited by designation; checks named (keywords such as "Wahl", "buckling"); spring end type; numbers and default dimensions; CAD or drawing format (file type, code language); supply voltage; headings, tables, length | The material the part is made of; whether a margin is built in; which checks are carried out with numbers; a design load stated; computed size, standard size or named product; where formulas are said to come from; cautions given; making, mounting, finish and tolerances mentioned; and per task the section shape, own weight, motor speed, kind of reduction, interface resistance, cooling, friction method, fitting losses, kind of pump, bracket shape |
| **Website** | Everything in [extractors.md](extractors.md): palette, fonts, libraries, layout, corners, shadows, gradients, icons, stock phrases, file structure, responsiveness, dark mode, accessibility | How the reply opens and closes around its code; the name the page gives its subject; people presented; contact details |

**Overlaps with the extractors.** Some rubric items sit beside an extractor
feature on the same subject. Each is kept because it answers a different
question. Where the two disagree on a run, the T2.11 review should look at
it.

| Rubric item | Extractor feature beside it | What the rubric adds |
|---|---|---|
| `retry_policy` | a retry present (keyword) | the waiting rule between tries |
| `storage_kind` | libraries imported (a database driver) | which store holds the results, where several are imported |
| `scheduling` | scheduling libraries; a CI file's triggers | only what is delivered in concrete form, and its kind |
| `ci_checks` | commands and tools named in a CI file | the kind of check, whatever the language's tool is called |
| `usage_docs` | a README file present | instructions given inside the reply |
| `sample_data` | data files present | sample input shown in the reply, or code that creates it |
| `curve_presentation`, `fit_extras` | plotting code present | plotting as one form among several (table, description, sketch) |
| `test_used`, `friction_method`, `drag_model` | method keywords | the method the result rests on, where several are named |
| `computation_medium` | code present | whether the numbers come from the code or from worked text |
| `material_assumed` | material names found | the material the part is designed in, where several are named |
| `safety_margin` | the value of a safety factor | whether any margin is built in, with or without a number |
| `checks_performed` | checks named (keywords) | a check carried out with a number against a limit |
| `formula_source` | standards cited by designation | any source named, and a general pointer against a named one |
| `opening`, `closing` | stock phrases, if T2.8 builds them for these types | the kind of opening or closing, whatever its words |

### The choices the prompt READMEs name

Every choice in the "Choices it brings out" column of the three prompt
READMEs, and where it is read. "Not recorded" is deliberate, and the reason
is given.

| Task | Choice | Read by |
|---|---|---|
| csv-to-database | Parsing messy values | `cleaning_steps` |
| | Storage | `storage_kind`; the engine by the libraries extractor |
| | Bad rows | `bad_input_handling` |
| | Safe re-runs | `rerun_behavior` |
| daily-api-fetch | Scheduling | `scheduling` |
| | Keys | Extractor: where a key is read from (environment, file, written in) |
| | Retries | `retry_policy` |
| | Gaps after a failed run | `gap_recovery` |
| | Storage | `storage_kind` |
| log-aggregation | Line format | `log_format_assumed` |
| | Malformed lines | `bad_input_handling` |
| | Memory | Not recorded in v1. Whether a file is read whole or line by line depends on which call is used in which language. An extractor can list the read calls; a rubric item would ask a small model to trace them. To reconsider once calibration shows how the code-reading items fare |
| | Report shape | Not recorded. Which figures a report holds has no closed set of answers. The output formats written (printed, CSV, JSON) are the extractor's |
| image-resize | Libraries | Extractor |
| | Orientation and metadata | Extractor: keywords for orientation and metadata handling. Not a rubric item: whether the call that is found does what a brief means is for the sandbox to show, on its fixture images |
| | Parallel work | Extractor: process or thread pools imported and used |
| | Partial failure | `bad_input_handling` |
| ci-workflow | Service, triggers | Extractor: the workflow file's path and keys |
| | Test matrix | Extractor: the matrix keys of the workflow file (systems, versions) |
| | Quality gates | `ci_checks` |
| data-validation | Where rules live | `rule_definition` |
| | How problems are reported | `bad_input_handling`. Whether all of a reading's problems are listed or only the first is not recorded in v1, for the reason given under Memory |
| | Stopping the next stage | `failure_signal` |
| projectile-drag | Drag law | `drag_model` |
| | Constants assumed | Extractor: the numbers given for mass, size and coefficient. `result_form` says whether one case or several is worked |
| | Closed form or numeric | `method_family` |
| loan-amortization | Formula or month-by-month | `method_family` |
| | Rounding | `payment_rounding` |
| | How much of the schedule | `schedule_extent` |
| | Currency | Extractor: currency symbol or code |
| titration-curve | Approximations | `method_family` |
| | Constants | Extractor: the Ka and Kw values used |
| | Points reported | Extractor: the rows of the table. The answer checker reads the values |
| | Drawn or tabulated | `curve_presentation` |
| hypothesis-test | Which test | `test_used` |
| | Assumptions | `normality_treatment`, `assumptions_stated` |
| | Sides | Not recorded. The question is two-sided at every level, so it is not an open choice ([leak-check.md](leak-check.md), rule 9) |
| | Level | `significance_level` |
| | Wording of the decision | Not recorded. The decision is the answer checker's to read, and classes of wording could not be drawn so that two readers would sort a sentence the same way |
| least-squares-fit | Formula route | `fit_route` |
| | Errors and residuals | `fit_extras` |
| | Precision | Extractor: significant figures |
| | Plot or code | `fit_extras`; extractor: code present |
| entropy-explanation | Framing | `entropy_framings` |
| | Analogies | `entropy_examples` |
| | Structure, length, formulas | Extractor |
| cantilever-beam | Material, section | `material_assumed`, `section_shape` |
| | Safety factor | `safety_margin`; its value by the extractor |
| | Checks | `checks_performed` |
| | Standards | Extractor; `formula_source` |
| | Self-weight | `self_weight` |
| conveyor-gear-ratio | Motor speed assumed | `motor_speed_assumed` |
| | Stages | Not recorded as an item. The number of stages follows from the tooth counts or ratios, which the answer checker reads; `reduction_kind` says whether kinds are combined |
| | Kind of reduction | `reduction_kind` |
| | Real parts | `part_selection` |
| heat-sink | Interface assumed | `interface_resistance` |
| | Natural or forced air | `cooling_mode` |
| | Bought or worked size | `part_selection` |
| pipe-and-pump | Friction method | `friction_method` |
| | Roughness | `material_assumed`; the roughness value by the extractor or the checker |
| | Fittings | `minor_losses` |
| | Temperature | Extractor or checker: a stated water temperature is a number, and the conditional reference answers need its value |
| | Pump type | `pump_type` |
| | Margin | `safety_margin` |
| shelf-bracket | Dimensions | Extractor: the numbers; `bracket_form` for the shape |
| | Load | `design_load` |
| | Material | `material_assumed` |
| | Making method | `manufacturing_notes` |
| | CAD format | Extractor: file type or code language |
| compression-spring | Force and size | `design_load`; the numbers by the extractor |
| | Wire | `material_assumed` |
| | Ends, stress correction | Extractor: keywords |
| | Fatigue | `checks_performed` |

T2.8's list in tasks.md does not yet name some of the left column (pronouns,
position of prose around code, currency). They are listed here so that the
split is complete; T2.8 decides which to build.

### L2 directions that rubric v1 does not measure

Three things an L2 brief dictates have no rubric item, so the rubric gives
no compliance figure for them. Each needs an owner outside the rubric; the
owners below are proposals for the coordinator to confirm.

| Task | L2 direction | Proposed owner | How it can be read |
|---|---|---|---|
| log-aggregation | Read the files one line at a time | T2.7 (sandbox), with T2.8 | The sandbox runs the output on a large fixture under its memory limit, which shows the behavior directly. The extractor can list the read calls as a second reading |
| data-validation | Check every rule on every reading, so a rejected reading lists all its problems | T2.7 (sandbox) | The second sample reading of the brief breaks three rules. The rejects file the output writes shows whether all three are listed |
| image-resize | Phone photos turned upright; camera and location details removed | T2.7 (sandbox), with T2.8 | Orientation and metadata can be read from the files the output writes for the fixture images. The extractor can record the keywords |

If one of these is wanted as a rubric item later, that is a new rubric
version: an added item changes what the tagger is asked
([Versioning](#versioning)). Outputs tagged before it have no answer for the
new item until they are tagged again, and tables of the two versions are
not pooled.

## The items

"Closed at L2" comes from the companion files. An item asked for one task
and closed there at L2 gives a default at L0 and L1, and compliance and
persistence at L2 ([metrics.md](metrics.md), "Sensitivity").

### Shared by several types

| Item | Dimension | Answers | In |
|---|---|---|---|
| `response_mode` (the gate) | response | one of `answers`, `answers-and-asks`, `asks-first`, `declines` | all four |
| `result_form` | response | one of `one-worked`, `several-worked`, `general-only` | pipeline, math (not the explanation), engineering |
| `opening` | tone | one of `acknowledgement`, `announcement`, `content`, `framing`, `question` | all four |
| `closing` | tone | one of `caveat`, `content`, `extension-ideas`, `offer`, `question`, `recap`, `sign-off` | all four |
| `assumptions_stated` | assumptions | scale: `none`, `in-passing`, `listed` | pipeline, math (not the explanation), engineering |
| `answer_position` | structure | one of `before-working`, `after-working`, `no-working`, `no-final-result` | math (not the explanation), engineering |

### Pipeline (20 items)

Tasks: csv = csv-to-database, api = daily-api-fetch, log = log-aggregation,
image = image-resize, ci = ci-workflow, validation = data-validation.

| Item | Dimension | Answers | Asked for | Closed at L2 in |
|---|---|---|---|---|
| `response_mode`, `result_form`, `opening`, `closing`, `assumptions_stated` | as above | as above | all | none |
| `usage_docs` | operation | scale of 4 | all | none |
| `sample_data` | assumptions | one of 3 | all but ci | csv, api, log, validation |
| `input_assumption` | assumptions | one of 3 | csv, api, log, validation | all four |
| `bad_input_handling` | robustness | several of 6 | csv, log, image, validation | all four |
| `rerun_behavior` | robustness | one of 4 | csv, api, image | all three |
| `storage_kind` | operation | one of 6 | csv, api | both |
| `cleaning_steps` | method | several of 9 | csv | csv |
| `scheduling` | operation | several of 5 | api | api |
| `retry_policy` | robustness | one of 4 | api | api |
| `gap_recovery` | robustness | one of 5 | api | api |
| `log_format_assumed` | assumptions | one of 6 | log | log |
| `aspect_handling` | method | one of 5 | image | image |
| `ci_checks` | method | several of 8 | ci | ci |
| `rule_definition` | method | one of 5 | validation | validation |
| `failure_signal` | robustness | one of 4 | validation | validation |

Where `bad_input_handling` ends and `cleaning_steps` begins is decided by
what is wrong with a row and where the row goes, not by whether the code
uses a loop or a mask. Both items carry this rule, word for word (the
guidance of `cleaning_steps`, and the csv-to-database note of
`bad_input_handling`; a test checks the three copies):

> Rows written to a separate place are always bad-input handling
> (sets-aside) and never a cleaning step, whatever they failed, repeats
> included. Where the rows go to no separate place, three things are
> cleaning steps and are never bad-input handling. They are removing
> repeated rows, dropping or filling rows with a missing value (with or
> without a count), and converting the type of a whole column. Rows removed,
> reported or repaired because they fail any other test or raise an error
> are bad-input handling and never a cleaning step.

The exception is for csv-to-database only, the one task with both items. In
the other tasks every record that is left out counts as bad-input handling.
What the rule gives for some common cases:

| Code | `cleaning_steps` | `bad_input_handling` |
|---|---|---|
| `df.drop_duplicates()`, the repeats kept nowhere | `removes-duplicates` | nothing from this |
| `df.dropna()`, silent | `removes-incomplete-rows` | nothing from this |
| `df.dropna()` with the number of dropped rows printed | `removes-incomplete-rows` | nothing from this: the rows go to no separate place |
| A mask for a missing `order_id`, its rows written to `rejects.csv` | nothing from this | `sets-aside` |
| Repeated rows written to `rejects.csv` or `duplicates.csv` | nothing from this: not `removes-duplicates` | `sets-aside` |
| `if bad: continue`, where `bad` is a failed test other than a missing value or a repeat (a quantity of 0, an unparseable date) | nothing from this | `skips-silently` |
| `if bad: continue`, where `bad` is a missing value | `removes-incomplete-rows` | nothing from this |

The printed count of dropped missing-value rows is the one fact this rule
lets go: it is cleaning only, so that a count printed beside a general
summary does not have to be told apart from a report of rejected rows.

### Math or science (20 items)

"Numeric tasks" are the five with numbers: projectile-drag,
loan-amortization, titration-curve, hypothesis-test, least-squares-fit.

| Item | Dimension | Answers | Asked for | Closed at L2 in |
|---|---|---|---|---|
| `response_mode`, `opening` | as above | as above | all | none |
| `closing` | tone | one of 7 | all | entropy-explanation |
| `result_form` | response | one of 3 | numeric tasks | projectile-drag |
| `assumptions_stated` | assumptions | scale of 3 | numeric tasks | all five |
| `answer_position` | structure | one of 4 | numeric tasks | loan-amortization, hypothesis-test |
| `computation_medium` | method | one of 5 | numeric tasks | projectile-drag |
| `answer_check` | checks | scale of 3 | numeric tasks | loan-amortization, projectile-drag |
| `method_family` | method | one of 4 | projectile-drag, loan-amortization, titration-curve | all three |
| `drag_model` | assumptions | one of 5 | projectile-drag | projectile-drag |
| `schedule_extent` | structure | scale of 4 | loan-amortization | loan-amortization |
| `payment_rounding` | assumptions | one of 3 | loan-amortization | loan-amortization |
| `curve_presentation` | structure | several of 5 | titration-curve | titration-curve |
| `test_used` | method | one of 8 | hypothesis-test | hypothesis-test |
| `significance_level` | assumptions | one of 5 | hypothesis-test | hypothesis-test |
| `normality_treatment` | assumptions | one of 4 | hypothesis-test | hypothesis-test |
| `fit_route` | method | one of 6 | least-squares-fit | least-squares-fit |
| `fit_extras` | checks | several of 6 | least-squares-fit | least-squares-fit |
| `entropy_framings` | explanation | several of 7 | entropy-explanation | entropy-explanation |
| `entropy_examples` | explanation | several of 7 | entropy-explanation | entropy-explanation |

### Engineering (24 items)

The examples in this rubric are invented to show what an answer looks like.
Their numbers were not worked out. Like the outputs, they are study data and
not designs.

| Item | Dimension | Answers | Asked for | Closed at L2 in |
|---|---|---|---|---|
| `response_mode`, `opening`, `closing` | as above | as above | all | none |
| `result_form`, `assumptions_stated` | as above | as above | all | all six |
| `answer_position` | structure | one of 4 | all | cantilever-beam, compression-spring, conveyor-gear-ratio, pipe-and-pump |
| `safety_margin` | checks | scale of 3 | all | cantilever-beam, compression-spring, shelf-bracket |
| `formula_source` | method | scale of 3 | all | cantilever-beam |
| `part_selection` | design | one of 4 | all | cantilever-beam, heat-sink, shelf-bracket |
| `caveats` | practice | several of 5 | all | none |
| `material_assumed` | assumptions | one of 9 | all but conveyor-gear-ratio | all five |
| `checks_performed` | checks | several of 6 | cantilever-beam, compression-spring, shelf-bracket | all three |
| `manufacturing_notes` | practice | several of 5 | cantilever-beam, compression-spring, heat-sink, shelf-bracket | shelf-bracket |
| `design_load` | assumptions | one of 3 | compression-spring, shelf-bracket | both |
| `section_shape`, `self_weight` | design, assumptions | one of 7, one of 3 | cantilever-beam | cantilever-beam |
| `motor_speed_assumed`, `reduction_kind` | assumptions, design | one of 5 each | conveyor-gear-ratio | conveyor-gear-ratio |
| `interface_resistance`, `cooling_mode` | assumptions, design | one of 3, one of 4 | heat-sink | heat-sink |
| `friction_method`, `minor_losses` | method, assumptions | one of 5, one of 3 | pipe-and-pump | pipe-and-pump |
| `pump_type` | design | one of 6 | pipe-and-pump | none |
| `bracket_form` | design | one of 5 | shelf-bracket | shelf-bracket |

### Website (6 items)

| Item | Dimension | Answers | Asked for | Closed at L2 in |
|---|---|---|---|---|
| `response_mode`, `opening`, `closing` | as above | as above | all | none |
| `name_given` | invented-content | one of 4 | all | all six |
| `people_presented` | invented-content | several of 4 | all | all but todo-app |
| `contact_details` | invented-content | one of 3 | all | all but todo-app |

## Size

| Rubric | Items in the file | Items asked about one output, by task |
|---|---|---|
| pipeline | 20 | 7 (ci) to 13 (api); mean 10.5 |
| math | 20 | 5 (the explanation), 10 or 11 for the numeric tasks; mean 9.5 |
| engineering | 24 | 12 to 15; mean 14 |
| website | 6 | 6 |

A test holds the per-output count at 15 or fewer. The reasons for these
numbers:

- **The files are longer than what one output sees** because the choices the
  prompt READMEs ask to be recorded are specific to a task: the drag law, the
  test chosen, the motor speed, the kind of pump. They need their own items,
  and each is asked for one task only. The shared and type-wide items are 6
  to 10 per type.
- **Tagging cost is not what limits the size.** An output is a few thousand
  tokens; its items with definitions and examples add about two to three
  thousand more (15 items of roughly 150 to 200 tokens each), and the answer
  is a short list. At the prices in tasks.md that is about a tenth of a cent
  per output for the smallest tagger and a few cents for the largest. These
  are estimates from the file sizes; T2.5 measures them.
- **The Human's time is.** T2.5 has the Human tag 30 outputs per type. At 9.5
  to 14 items an output that is 285 to 420 judgements per type, two to
  three hours at 25 seconds a judgement. Twenty items per output would be
  600 judgements, more than four hours per type.
- **So is a small model's accuracy.** Each extra item in one call is another
  instruction to hold, and the calibration bar is set per rubric. If the
  smallest model misses the bar, T2.6 can ask the items of one output in two
  calls, by dimension, before moving up a tier.
- **Engineering is the largest** because the plan lists the most open
  choices for it, and most need reading. Its count is at the limit; an item
  added later should replace one. The cap of 15 was kept in the review
  round: the two items added there went to pipeline and math, and no
  engineering item was dropped, because each records a choice the plan
  lists for the type and none duplicates another.

## Website

T2.4 asked for a website rubric only if there is a choice the website
extractors cannot read. There is, and the rubric is kept to it:

- **Placeholder content.** The plan lists it among the website's open
  choices. No extractor reads it: `website.stock-phrases` matches phrase
  lists (and filler text), and `website.layout` sees that a testimonial
  section exists, as a heuristic, but not whether the page shows a made-up
  business name, named customers or a street address. Classing a header text
  as a specific name, a generic label or a stand-in takes reading. Three
  items: `name_given`, `people_presented`, `contact_details`.
- **How the reply opens and closes around its code**, with the same two
  items as the other types, and the gate. An extractor reads the files, not
  the prose around them.

**Copy tone is not an item.** A tone label ("promotional", "plain") is a
judgement with no fact to check it against, and two taggers would not agree
on it for the same reasons two people would not. What can be counted about
tone is counted by the extractor already: exclamation marks, title case,
stock phrases. If the pilot review (T1.10) finds the stock-phrase rules too
thin, the better fix is more rules or a tone item built on a countable fact
(for instance, whether the copy makes a claim of being the best), added as
website.v2.

**Not scheduled.** T2.5 names the three Phase 2 types. Calibrating
`website.v1` means tagging website outputs of the pilot (T1.7) as well, and
30 more outputs for the Human. That is the Human's call; the rubric costs
nothing until then.

## What a prompt dictates

A default is what a model chooses when the prompt leaves the choice open. An
L2 brief closes some rubric items, as it closes some website features. The
companion `rubrics/<type>.v<N>.dictated.yaml` lists them in the entry format
of [analysis/website/dictated.yaml](../analysis/website/dictated.yaml):

```yaml
tasks:
  daily-api-fetch:
    prompt_set_version: "1"
    L2:
      - closed: [rubric.pipeline.retry_policy]
        reason: direction            # direction | content | constraint
        quote: "try again up to 3 times, a minute apart"   # words of wording A
        expect:
          rubric.pipeline.retry_policy: {in: [retries-fixed-wait]}
```

- `expect` is `{in: [...]}` for a single-select item, and `{present: [...]}`
  and/or `{absent: [...]}` for a multi-select item. It is left out where the
  brief decides the answer without one value being the compliant one.
- `associations` lists wording that may pull an open choice without closing
  it: "pH curve" and a drawn curve, "gear ratio" and gears, "access logs"
  and a web server's log layout.
- L0 and L1 close nothing, and the loader refuses an entry there: wording
  at those levels that may pull a choice is an association. The entries were read from the "What each L2
  dictates" and "Choices not to read as defaults" tables of the three
  leak-check logs and from the L2 texts.
- Math and engineering L2 briefs state their assumptions, so
  `assumptions_stated` is closed there and read at L0 and L1 only
  ([leak-check.md](leak-check.md), rule 15). Pipeline briefs leave the start
  command, paths and naming open (rule 18), so it stays open at every level
  there.
- Where a dictated value is close to the expected default (the drag law, the
  motor speed, still air, a plastic pipe, an embedded database), the note
  says that compliance can be read and persistence cannot.

The companion is a separate file because it changes how tags are counted and
not how they are made. Correcting an entry needs no new rubric version and
no new tagging. The validator checks that every closed item exists and is
asked for that task and level, that every expected value is an answer of the
item, and that every quote is found in wording A.

## Versioning

- **The version is in the file name and in the file**, and they must agree:
  `pipeline.v1.yaml` holds `rubric_version: "1"`.
- **A version is frozen once it has been used for a paid tagging run.** Any
  change to what the tagger is told is a new version in a new file
  (`pipeline.v2.yaml`): an item added or removed, a question, an option, a
  definition, a tie rule, guidance, a task note, an instruction, `applies_to`
  or the gate. The old file stays, so old tags can still be read.
- **Before the first paid run** a file may be corrected in place, as the
  prompt sets were. Calibration will find items to fix, and those fixes make
  v2 if any tagging at v1 is to be kept, and stay v1 if it is all discarded.
- **Examples** count as a change too if T2.6 shows them to the tagger, which
  is the intent. A typo fix in an example that the tagger never saw is free.
- **Tags carry the version.** They are stored at
  `<rubric version>@<tagger model id>`. Tags of two rubric versions, or of
  two tagger models, are never pooled in one table; a new version replaces
  the old tags of a record when it is tagged again.
- **Item ids are stable across versions.** An item whose meaning changes
  gets a new id; an id is never reused for another question. Then a table of
  v2 can be set beside a table of v1 item by item.
- **`prompt_set_versions`** ties the rubric to the prompt texts it was read
  against. When a prompt file's version is raised, the test fails until
  someone has read the new text against `applies_to`, the task notes and
  the companion, and updated the version here. That update alone is not a
  new rubric version: it changes nothing the tagger is told.

## Calibration (T2.5)

T2.5 tags 100 outputs per type with three Claude models, compares each with
the Human's tags on 30 of them, picks the cheapest model that meets the bar,
and tags a sample with a non-Claude model. This section recommends how.

### The sample

- **The 100**: drawn at random with a fixed seed from the T2.9 records,
  stratified so that every task has 16 or 17, spread over the three levels,
  both wordings and the three pilot models.
- **The 30 for the Human**: 5 per task from the 100, with every level and
  every pilot model in each task's five. L2 outputs must be in: they follow
  briefs that point away from the default, so they are where the answers
  other than the most common one come from.
- **The Human tags first and blind**: from the rubric file, without the
  model that wrote the output and before seeing any tagger's answer.
- **The Human's own repeat.** The Human tags 10 of the 30 a second time, at
  least a day later and without the first tags. The Human's agreement with
  their own first pass, by the measure below, is the ceiling: no tagger can
  be shown to agree with the Human more than the Human does. If it is below
  0.95 for a rubric, the wording is at fault before any tagger is, and a
  tagger within a few points of the ceiling should not fail on condition 1
  alone.
- Keep the Human's first-pass tags as they are. If the Human reads a
  disagreement again and changes a tag, record both; the bar is judged on
  the first pass and the second is reported beside it.

### The agreement measure

Agreement of a tagger with the Human on one item and one output is the
agreement the metrics already use between two runs ([metrics.md](metrics.md),
"Agreement and shift"): 1 or 0 for a single-select item, and the Jaccard
overlap for a multi-select item (1 when both say `none`). Three cases
are scored here that the metrics skip. The metrics leave out a pair of runs
when either has no value; in calibration these are answers of the tagger and
must count:

- `cannot-tell` on one side only scores 0, and on both sides 1;
- `not-applicable` on one side only scores 0, and on both sides 1;
- where the Human and the tagger disagree at the gate (one went on to the
  other items, the other stopped), every further item that either of them
  answered scores 0 for that output.

- **Item agreement** A(i): the mean over the outputs for which item i was
  asked and at least one of the two went past the gate. `docs/tagger.md`
  lists A(i) for every item, with the number of outputs behind it, and not
  only the rubric figure.
- **Rubric agreement** A: the mean of A(i) over the items, each item
  weighted by its number of judged outputs, with a 95% interval from a
  bootstrap over the 30 outputs (outputs are resampled whole, because the
  items of one output are not independent).

Raw agreement is the primary measure because it bounds what the project
reports. If a tagger gets a yes/no item wrong in a share e of outputs, a
true share p is seen as p + e(1 − 2p): no share moves by more than e, and a
shift between two levels shrinks by the factor (1 − 2e)². With e = 0.10 a
share is off by at most 10 points and a shift keeps 64% of its size; with
e = 0.05, 5 points and 81%.

**Chance-corrected agreement: Gwet's AC1, not Cohen's kappa.** Kappa
collapses when one answer is very common, and a strong default is exactly
that. With 30 outputs, 29 tagged `content` by each rater and their single
other answers on different outputs, raw agreement is 28/30 = 0.933 and kappa
is −0.03. AC1 is built for this case:

    AC1 = (A − C) / (1 − C)        C = sum over options k of q(k)(1 − q(k)), divided by (K − 1)

where K is the number of answers and q(k) the mean of the two raters' shares
of answer k. In the same case q = (0.967, 0.033), C = 0.064 and AC1 = 0.93.
A worked case with three answers: the Human gives 24, 4 and 2; the tagger
agrees on 23, 3 and 1 of them and gives 25, 4 and 1 overall. A = 27/30 =
0.90; kappa = 0.68; q = (0.817, 0.133, 0.050), C = 0.156, AC1 = 0.88. Report
AC1 per single-select item beside A(i), to show that agreement is not an
effect of a narrow set of answers. It is reported, not part of the bar: with
30 outputs its interval is too wide to decide anything that A does not.

### The bar

A tagger model passes for a type when all four hold on the Human's 30:

| # | Condition | Why this number |
|---|---|---|
| 1 | Rubric agreement A at least **0.90**, and the lower end of its interval at least **0.85** | A tagging error of 10% moves a share by at most 10 points, under the 12-point half-width a share already has at 60 runs ([metrics.md](metrics.md), "Which runs count" uses the same reasoning for missing runs). The lower end guards against passing on a lucky sample |
| 2 | Every item judged on 20 or more outputs: at least **24 of 30** agree (0.80), in proportion for fewer | An item whose true agreement is 0.90 fails this by chance in 2.6% of cases; one at 0.70 passes in 16%, one at 0.60 in 1.7%. Thirty outputs cannot show more per item: even 30 of 30 leaves a lower bound of 0.89 |
| 3 | **Minority agreement** at least **0.80**: over all single-select items, among the judgements where the Human's answer is not that item's most common Human answer | A tagger that always gives the most common answer scores well on condition 1 when defaults are strong, and is blind to every shift the project measures. Needs 20 or more such judgements; if the 30 hold fewer, add L2 outputs |
| 4 | `cannot-tell` given on at most **10%** of an item's judgements where the Human gave a value | More than 10% undetermined flags a row `partly read` in the metrics |

What the bar means for the results: at agreement 0.90 a default that every
run shows is seen in about 54 of 60 runs, whose lower bound (0.7985) falls
just short of `strong default` (0.80). A tagger at 0.95 shows 57 of 60 and
keeps the label. So 0.90 is the least that keeps shares readable, and a
report must print the tagger's agreement beside any label read from tagged
variables. If two models pass and the dearer one reaches 0.95, weigh that
against its price: it is the difference between "default" and "strong
default" for the choices that matter most.

**A limit of this design.** Items asked for one task only have 5 judged
outputs each in the 30, too few for condition 2: 9 of the 20 pipeline items,
11 of the 20 math items and 10 of the 24 engineering items. Calibration as
T2.5 defines it cannot validate them one by one. They are judged together, as one pooled group per rubric,
against 0.80. They stay `provisional` and are read in per-task tables, where
the metrics label them `insufficient data` for a pooled row in any case (one
task). If one of them matters to a finding, the Human tags 10 more outputs
of that task first.

### Choosing, and what to do with a failing item

1. Take the cheapest model that passes for all three types. A different
   tagger per type is allowed but costs clarity; prefer one.
2. If none passes, look at the items before the models. An item that every
   tagger fails against the Human, while the taggers agree with each other,
   usually has a definition the Human read differently: fix the wording (a
   new rubric version if tags are to be kept) and tag the 30 again.
3. An item that fails after one rewrite stays `provisional` and out of the
   summaries, or is dropped. It does not hold the rubric back.
4. Expect the first rewording in two groups: the items that read what code
   does (`bad_input_handling`, `rerun_behavior`, `input_assumption`), and the
   shared items with the finest boundaries (`opening`, `closing`,
   `result_form`). Look at their A(i) first.
5. The 100 outputs that only the models tagged give a second reading:
   agreement between the chosen model and the largest one, per item, by the
   same measure. An item under 0.85 there goes on the list for the T2.11
   review even if it passed on the 30.

### Repeat tagging

Tag the 100 twice with the chosen model and the same settings. Agreement of
the two passes, by the same measure, should be at least **0.97** per rubric;
below that, the tags of single runs are noisier than condition 1 assumes.
T2.6 stores one tag per output and version, so a stored tag is stable in any
case; this figure says how much of it is chance.

### The cross-family check

Tag the 100 with one non-Claude model and compare it with the chosen Claude
tagger, separately for outputs written by Claude models and outputs written
by other models:

- **Agreement gap**: agreement between the two taggers on Claude-written
  outputs, minus the same on the others. A Claude tagger that reads Claude
  output differently from how an outside model reads it shows here.
- **Direction**: for each answer k of an item, the share the Claude tagger
  gives it minus the share the other tagger gives it, on Claude-written
  outputs, minus the same difference on the other outputs. A positive value
  means the Claude tagger sees k more often in Claude's output than an
  outside reader does, beyond what it does for everyone's output.
- On the Human's 30: the chosen tagger's agreement with the Human on
  Claude-written outputs, minus the same on the others.

Flag an item when a gap or a direction is 0.10 or more in size and its
bootstrap interval (over outputs) leaves out 0. With 100 outputs only large
effects can be seen; a flag is a reason to have the Human tag more of that
item, not a verdict. Report the figures in `docs/tagger.md` whatever they
show.

## Notes for later tasks

- **T2.6 (tagger).** Load with `tagger.rubric.load_checked(type)`; ask
  `Rubric.items_for(task, level)`, gate first; stop after the gate when
  `Rubric.stops_at_gate` says so (a `no_solution` answer or `cannot-tell`); show options in `presentation_order`; give the
  instructions word for word, and for each item its question, guidance, tie
  rule, the task note for the output's task, each option's definition and
  example, and the `cannot_tell` and `not_applicable` rules; check every
  stored value with `Rubric.check_value`. Do not pass the model id, the
  prompt or the level. Asking the tagger for a short quote as evidence
  beside each answer costs little and makes the T2.11 review faster.
- **T2.8 (extractors).** The left column of
  [the split](#the-split-with-the-extractors) is yours. The outcome of a
  pipeline, math or engineering run (`artifact` or `no-artifact`) needs the
  gate item as well as the files. Most math and engineering answers are
  prose with no file, so a missing file cannot mark a run as having no
  solution there; the gate item does.
- **Metrics for these types (T1.6, T2.11).** Two things are needed before
  rubric variables can be counted by `analysis/`:
  1. `features.yaml` has one dimension per extractor, and all tags of a type
     come from one extractor, `rubric.<type>`. Rubric items carry their own
     dimension (`variable_declarations` writes it), so `features.yaml` needs
     a per-variable `dimension` that overrides the extractor's. Without it
     every rubric item of a type falls into one dimension.
  2. The companion entries have to reach `analysis/<type>/dictated.yaml`,
     by merging the files or by reading both. The entry format is the same
     and the variable names are already the full ones.
- **T2.10 (checker).** Conditional reference answers are graded against the
  choice a response states (a motor speed, a roughness). The rubric records
  the class of such a choice (`near-1500`), not its value; the value is the
  checker's or an extractor's to read.
- **Wave 2 and 3 rubrics.** Reuse the shared items word for word, so that
  the test of shared items keeps holding.

## Checks

`python -m pytest tests/test_rubrics.py` checks:

- every rubric file loads, is named as its content says, and has a
  companion;
- each rubric lists exactly the tasks of its type at their current prompt
  set versions, and every item is asked for real tasks and levels;
- item ids are unique, every dimension is used, and every answer of every
  item (each option, `none`, `cannot-tell`, `not-applicable`) has its own
  example;
- every single-select item says how "not present" is answered; every
  multi-select item has an `other` option or declares itself complete; every
  `several` or `both` option comes with a tie rule;
- no output is asked more than 15 items, and the counts in
  [Size](#size) hold;
- shared items and the instructions read the same in every rubric;
- in the companions, L0 and L1 close nothing, every quote is in wording A,
  and every expected value is an answer of its item;
- stored values, option order and the variable declarations behave as
  described above;
- one fault at a time, 47 broken rubrics and 19 broken companions are
  refused: a version that differs from the file name, a repeated id, a
  missing example, a judging word, a model name, options out of order, an
  unknown task, a quote that is not in the prompt, and so on.
