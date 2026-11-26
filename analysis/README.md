# analysis

The metrics of [docs/metrics.md](../docs/metrics.md) (defined in T1.5,
computed here since T1.6), and the data files they read. metrics.md is the
specification; this page says how to run the code and what it writes.

Contents: [data files](#data-files) · [before you run it](#before-you-run-it)
· [the tables](#the-tables) · [the stability check](#the-stability-check-t18)
· [refusals](#refusals) · [choices the code makes](#choices-the-code-makes-where-metricsmd-leaves-room)
· [code](#code)

## Data files

The code is generic: no feature name, bin, mask or dictated entry is written
in it. What a project type's features mean comes from one folder per type
with two data files:

- `<type>/features.yaml`: every feature of that type's extractors, with its
  type (categorical, boolean, number, set, ordered list, count-map), its role
  (primary, provisional, secondary, diagnostic), its bins, the reason it is
  or is not counted, and the variables that decide it (`depends_on`). Also
  the masks, and the metrics version.
- `<type>/dictated.yaml`: per task and level, the choices the prompt takes
  out of the model's hands, with the words of the prompt that do so and, where
  it can be said, the value a compliant output shows. A variable that depends
  on a closed one is closed with it.

Present now: [website/](website/), [pipeline/](pipeline/),
[math/](math/) and [engineering/](engineering/). The last three also decide
outcomes from the rubric and need tagged records
([docs/metrics.md](../docs/metrics.md#types-with-a-rubric)).

[tests/test_metrics_data.py](../tests/test_metrics_data.py) checks both files
against the extractors and the prompts: every extracted feature is declared,
the versions match, every quoted phrase is in its prompt. Raising an extractor
version or a prompt-set version makes it fail until the files are read again.

Filled by these tasks in [tasks.md](../tasks.md):

- T1.5: the website data files (done)
- T1.6: the metrics and the stability check, as this Python package (done)
- T2.8: the data files of pipeline, math and engineering (done)
- Later waves: data files for the other project types

## Before you run it

1. Run the extractors over the record file, so that every `ok` record carries
   every extractor of the type at the version `features.yaml` lists:

       python -m extractors --records data/runs/<batch-id>/records.jsonl

2. Make sure `features.yaml` and `dictated.yaml` describe the prompts and
   extractor versions the records were made with (`tests/test_metrics_data.py`
   checks this against the repository).

## The tables

    python -m analysis tables --records data/runs/pilot-1/records.jsonl --batch pilot-1

| Option | Meaning |
|---|---|
| `--records FILE...` | One or more record files |
| `--batch ID` | A batch id of the **batch group**; repeat for several. Records of other batches are ignored |
| `--type TYPE` | Project type, as in `analysis/<type>/` (default `website`) |
| `--out DIR` | Output folder (default `data/analysis/<batch ids joined by +>/`, gitignored) |

It writes two files:

- `<type>-tables.json`: everything, machine-readable. Every exact value is
  written as `{"fraction": "59/80", "decimal": 0.7375}`; intervals and the
  evidence figures (x1, x2) as decimals. Item sets are sorted lists.
- `<type>-tables.md`: a readable summary: per model and level the outcome
  table, the health rates above 0, the fingerprint rows of the primary and
  provisional variables, convergence and wording sensitivity by dimension,
  the pooled directed table and the representative outputs; per model the
  prompt sensitivity for L0 to L1, L1 to L2 and L0 to L2 by dimension (S,
  yardstick, E) with the associations; and the comparison across models.

The same records always give byte-identical files.

### What the JSON holds

Top level: `metrics_version`, `project_type`, `extractor_versions`,
`batch_group`, `record_files`, `notes` (records left out, an unfinished last
line), `tasks`, `models`, `model_comparisons`.

Per model, `levels.<level>` has:

| Key | Content |
|---|---|
| `fingerprint` | `dates`, `model_id_returned`, `settings`, `flags` (`incomplete outcomes`, `mixed snapshots`), `outcomes`, `health`, `partly_read_dimensions`, `variables` (one row per primary, provisional and secondary variable), `representative_outputs` (per task) |
| `convergence` | per variable, per dimension and overall, each with the per-task values, mean, task interval and T |
| `wording_sensitivity` | as convergence; a dimension whose task interval lies above 0 carries the flag `read the wording pair again` |
| `directed` | `entries`: every closed variable per task (listed or dependent, with the variable that closed it), its per-task shares, compliance where an expected value is given, and for primary and provisional variables convergence, wording shift, shift and excess from L0; `pooled`: compliance and persistence per variable over the tasks where they can be read |

and `sensitivity` is a list of level pairs, each with `shift`, `yardstick`
and `excess` (a dimension whose excess has a task interval above 0 carries
`direction moved it`) and the `associations` of the higher level.

A fingerprint row (`variables[]`) holds `open_tasks`, `N`, `T`, `n_eff`,
`undetermined` and `not_applicable` (count and share by weight), `flags`
(`partly read`, `task-dependent`, `task-driven`), `items` (every choice or
item by share, with run and task intervals), `per_task` (the per-task tables)
and the summary: for a variable with one value per run `label`,
`nominal_top`, `reported`, `evidence`, `task_support`, `task_spread`,
`holds_across_tasks`; for a set variable `label` (`insufficient data` or
`default set`) and `default_set`. A variable closed in every task at a level
has the label `closed in every task` and no shares.

`model_comparisons` holds, per level with two or more models, the agreement X
and model shift D per pair and for all models (`the models differ` on a
dimension whose D has a task interval above 0), and `shared_defaults`.

## The stability check (T1.8)

    python -m analysis stability --records data/runs/pilot-1/records.jsonl \
        --batch pilot-1 --model <model-id> [--compare 5,10]

`--compare` is `5,10` (the first check, default) or `10,20` (the repeat). The
check reads one batch.

**When runs are missing**, the verdict is `not run` and the output names the
cells to run: every L0 cell (task and wording) with the run indexes it still
lacks, and the runner command that runs them. The runner plans run indexes 1
to N and skips those already recorded ([docs/runner.md](../docs/runner.md)),
so the doubling is

    python -m runner.run --prompts prompts/website --batch-id pilot-1 \
        --models <model-id> --levels L0 --runs 10 --dry-run

and then the same with `--paid` and both caps. A failed attempt leaves its
run index missing, and the runner retries it. A cell whose runs exist but
are too few usable (fewer than 4 of the first 5 or 8 of 10; 8 of 10 and 16 of
20 for the repeat) is listed under `cells_short` and also gives `not run`.

**When the runs are there**, it prints and writes the score, the counted
variables with their credits, the counts of kept, new, lost and reversed
variables (and, for sets, `changed`: items gained or dropped without a
reversal), the reversals, the established defaults in both tables (E5, E10)
and the growth, the verdict, what follows from it under the table that
applies (first check or repeat), every changed variable with its kind of
change, and the established defaults gained (listed as `open at 10 runs`
after a repeat that ends `unstable: defaults still appearing`). It also
compares run indexes 1 to 5 with 6 to 10 (or 1 to 10 with 11 to 20): the
shift per dimension, the dates and the `model_id_returned` values of each
group, which is what a `drift suspected` verdict asks to read.

Files: `<type>-stability-<model>-<small>v<big>.json` and `.md` in the same
output folder.

## Refusals

The commands stop with `refused: ...` and exit status 2, writing nothing,
when the tables would mean something other than they say:

- a usable run lacks an extractor of the type, or has one at a version other
  than `features.yaml` lists (re-run `python -m extractors`); an extractor
  named for the type is not declared; a feature of a declared extractor is
  not declared;
- a record's `prompt_set_version` differs from the one in `dictated.yaml`, or
  its task is not in `dictated.yaml`;
- for a type with a rubric, a record has not been tagged, was tagged at
  another rubric version, or the records of the table come from two tagger
  models;
- a stored value does not fit its declared type, or a number is below its
  first bin edge;
- one model's records in the batch group have more than one `settings` value;
- a record file has a bad line, or a record appears in two files.

Records that are not `source: controlled` on `surface: api` are left out
with a note. Records of a `refused` or `truncated` status need no extractor
features: they enter only the outcome table.

## Choices the code makes where metrics.md leaves room

- A feature missing from an extractor's result that has status `ok` or
  `partial` is undetermined, like a `null`.
- An `ok` record whose `structure` is `null` has the outcome `unread`.
- The `settings` rule is applied per model across the whole batch group, so
  levels of one model are never compared under different settings.
- The health rate of a diagnostic feature is the share of runs where it is
  present (a count of 1 or more, or a non-empty set), over usable runs whose
  extractor has status `ok` or `partial`. A diagnostic **count** feature above
  10% flags its dimension `partly read` (for the website type,
  `unparsed_colors` and `unknown_color_utilities` in palette). The masked
  share is over all usable runs.
- The directed table lists every closed variable that is not diagnostic,
  secondary ones included, because some expected values are on secondary
  variables (`base_scheme`); shift and excess are given for primary and
  provisional ones only.
- "All models" averages X and D over the pairs per cell position, then in
  the usual order, so it has its own task interval.
- A tie row with too little data is labelled `insufficient data`, not
  `contested`: the data rule comes first.
- Student's t beyond 11 degrees of freedom (more than 12 tasks) is computed
  numerically; the document's table is used up to there.

## Code

| Module | Content |
|---|---|
| `spec.py` | Reads the two data files: variables, masks, closure by dependence, expected values, associations |
| `runs.py` | Record selection (one per cell key), outcomes, refusals, feature-to-variable conversion, masks, health flags |
| `stats.py` | Pooling and weights, Wilson and task intervals, labels, agreement, within, cross, shift, the averaging order |
| `tables.py` | Fingerprint rows, outcome and health tables, convergence, sensitivity, the directed table, model comparisons, typicality |
| `stability.py` | The stability comparison, verdicts and the check on records |
| `report.py` | JSON and Markdown output |
| `__main__.py` | The two commands |

Tests: [tests/test_analysis_examples.py](../tests/test_analysis_examples.py)
reproduces every worked example of metrics.md with its inputs and exact
results; [tests/test_analysis_records.py](../tests/test_analysis_records.py)
covers record selection, outcomes and refusals, and runs both commands end
to end on synthetic records.
