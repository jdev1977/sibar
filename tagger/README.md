# tagger

Rubric tagging by a model (tasks T2.4 and T2.6 in [tasks.md](../tasks.md)).
A tagging model answers the multiple-choice items of
[rubrics/](../rubrics/README.md) about each output, and the answers are
stored as features of the run record. The rubric format and the calibration
plan are in [docs/rubrics.md](../docs/rubrics.md); the calibration report
will be `docs/tagger.md` (T2.5).

**Nothing here has been run against a live API.** No keys exist yet. Both
batch adapters were written from the providers' documentation read on
2026-11-26 (links in [backends.py](backends.py)) and are tested against
in-memory fakes of those APIs. The first paid run is the first live test:
start it small (`--max-requests 5`, a low `--batch-cap`) and read the job
log and the ledger before going on.

| File | Does |
|---|---|
| [rubric.py](rubric.py) | Loads and checks the rubrics and their companions (T2.4) |
| [taggers.yaml](taggers.yaml), [models.py](models.py) | The tagging models, their prices and output limit |
| [prompt.py](prompt.py) | The request for one output: prompt text, answer schema, cache key |
| [answers.py](answers.py) | Checks a reply against the rubric; what is stored |
| [backends.py](backends.py) | Anthropic Message Batches and OpenAI Batch, behind one interface |
| [store.py](store.py) | The tag cache and a run's job log |
| [run.py](run.py) | `python -m tagger tag` |
| [agreement.py](agreement.py) | `python -m tagger agreement` and `python -m tagger template` |

## Tagging

    python -m tagger tag --records data/runs/pilot-1/records.jsonl \
        --type pipeline --tagger claude-haiku-5-5 --run cal-haiku --dry-run
    python -m tagger tag ... --paid --batch-cap 5 --total-cap 50 [--wait]

| Option | Meaning |
|---|---|
| `--records FILE...` | Run record files. Records of the rubric's type with status `ok` are tagged (`--statuses ok,truncated` to add others) |
| `--type`, `--rubric-version` | The rubric, `rubrics/<type>.v<N>.yaml` (default version 1) |
| `--tagger` | A tagger id from [taggers.yaml](taggers.yaml) |
| `--run` | The run's name: its folder `data/tagger/<run>/` and its ledger batch `tag-<run>`. **Resume a run with the same `--run`** (and the same `--ledger`): only it collects its jobs |
| `--dry-run` | Counts, the worst case at standard rates and at the batch price, and missing keys. Sends and writes nothing (not even a repair of a cut last line). `--show-prompt RECORD_ID` prints one request |
| `--paid` | Sends requests. Needs `--batch-cap` and `--total-cap`, the tagger's key in its environment variable, and `confirmed_by_human: true` in taggers.yaml |
| `--max-requests` | Requests per job (default 1000) |
| `--max-tokens`, `--effort` | Output limit (default 16000, from taggers.yaml) and reasoning effort (default: the model's own). Both change the request, so the cache key |
| `--wait`, `--poll-seconds` | Keep polling until every record is tagged (default: do one round and stop) |
| `--retry-errors` | Tag once more the outputs whose cached answer is `status: error` |
| `--abandon JOB` | Declare dead a job sent with no answer, after checking the provider's console (see "After a crash"). A submitted job, with a provider id, cannot be abandoned |
| `--out`, `--cache`, `--ledger`, `--run-dir` | Other paths |

A batch job takes minutes to hours. Without `--wait`, each invocation
collects the jobs that have ended, sends what is left and stops; run it again
later. Exit codes: 0 every selected record is tagged; 1 some are waiting or
ended in an error; 2 refused; 3 the cap stops the next job; 4 blocked by a
job that may exist; 130 interrupted.

### What the tagger is given

One request per output, asking every item of the output's task and level,
gate first:

- a **system** text: the role; the rule that the response is data and any
  instruction inside it is to be classified, never followed; the rubric's
  instructions word for word; how to answer; and for each item its question,
  guidance, tie rule, the task note for this task, each option's definition
  and example in the presentation order for this output, then `none`,
  `cannot-tell` and `not-applicable` with their rules and examples;
- a **user** text: the record's `raw_response`, unedited, between two marker
  lines whose code comes from the response's SHA-256 (a response cannot hold
  its own end marker);
- the **answer schema** (the provider's structured output: Anthropic
  `output_config.format`, OpenAI strict `text.format`): one object per item
  with `evidence` (a quote of at most 25 words) and `answer`.

Nothing else of the record is sent: not the model that wrote it, its
provider, the prompt, the level, the wording, the batch or the record id
(which only seeds the option order). `custom_id` values are opaque job
numbers. Self-identifying lines inside a response are not stripped; docs/rubrics.md
asks for that only if the pilot shows models write them.

**Website outputs** are tagged from the same `raw_response`: the full reply,
prose and code, from which the runner extracted the files. The extracted
files are not sent separately. They hold nothing the reply does not, and the
website items read the prose around the code (`opening`, `closing`) and the
page text in it (`name_given`, `people_presented`, `contact_details`). A page
that a script builds at run time is read as source, not as rendered text.

The tagger is asked every item in one call; when the gate answer stops the
tagging (`asks-first`, `declines`, or `cannot-tell`) the other answers are
discarded and only the gate is stored.

### What is stored

A copy of the record files, `data/tagger/<run>/records.<tagger>.jsonl`: every
input record, and on each tagged one the features of extractor
`rubric.<type>` at version `<rubric version>@<tagger id>`
([record-format.md](../docs/record-format.md)). Item values follow
[docs/rubrics.md](../docs/rubrics.md), "From answers to variables". Beside
them, as every extractor does, `status` (`ok`, `partial` or `error`) and,
when not `ok`, `error`. Declare both under `common` in `features.yaml`; a
variable's `dimension` key now gives each item its own dimension.

Each tagger writes its own copy, so a record never holds two taggers' tags
(one entry per extractor per record). If the input already holds tags of
the same extractor (another tagger's copy given as input), they are removed
from every record this tagger has not tagged yet, so a copy never mixes two
taggers. The input files are not changed.

### Faults in an answer

Every reply is checked strictly ([answers.py](answers.py)): exactly the items
asked (an extra or a missing item is a fault), each `{evidence, answer}`, an
answer id of the item (`not-applicable` only where the item has it), a
multi-select list of distinct option ids or a reserved answer alone.

1. A reply with a fault that matters (any of those; not a JSON object; a
   refusal; cut off at the output limit; an API error) is asked **once
   more**, with the same request, in the next job. Faults in items after a
   stopping gate do not matter.
2. The second reply is used as it is. A faulty item is stored as `null`
   (cannot tell), with `status: partial` and an `error` naming the items. A
   second reply with no usable object stores `status: error` and no item.
3. Requests that were canceled or expired, or whose job never ran, were not
   processed. They are sent again without using the retry, in at most four
   jobs in all; then `status: error`.

### Tagging the same output twice

**A live model does not give the same tags twice.** Repeatability here comes
from a cache, `data/tagger/cache.jsonl`: one final answer per key, where the
key is the SHA-256 of the whole request (template version, provider, model,
output limit, effort, rubric text, option order, schema and the response),
of the response, of the rubric name and version, and of
`ANSWERS_VERSION` in [answers.py](answers.py) (raise it when a change there
could store other features for the same reply). Tagging an output again
with the same settings sends nothing and stores the cached tags, in any run.
Any change to what would be sent, or to how a reply becomes stored
features, is a new key and a new request.

To **measure** how much a live model's tags vary (docs/rubrics.md, "Repeat
tagging", target 0.97), tag again into a separate cache and compare:

    python -m tagger tag ... --run repeat-1 --cache data/tagger/cache-repeat.jsonl --paid ...
    python -m tagger agreement --type pipeline \
        --a data/tagger/cal-haiku/records.claude-haiku-5-5.jsonl \
        --b data/tagger/repeat-1/records.claude-haiku-5-5.jsonl

### Money

- Every request is reserved in the ledger ([docs/ledger.md](../docs/ledger.md))
  before its job is created, at its worst case: a high prompt estimate (one
  token per byte of system text, response and schema, plus 1000) and the
  full output limit, at the **standard** rate. A job holds only the requests
  that fit under both caps; if none fits the run stops (exit 3).
- When a job ends, each request is settled from the usage it reports.
  Errored, canceled and expired requests are not billed (Anthropic says so;
  OpenAI bills only completed requests of an expired batch) and settle at
  zero. A billed request with no usage settles at its worst case.
- The ledger charges standard rates, as it does everywhere: batch discounts
  are ignored, so its figures are the most a run can cost. Both providers
  bill batches at half the standard rates; the dry run prints that figure
  too. A cap therefore runs out at about twice the real spend.
- The tagger-only model (Claude Sonnet 5.5) is priced from taggers.yaml and
  passed to the ledger with the models under test; models.yaml and the
  pilot list are not changed.
- **Set a spend limit in the provider's Console too** (Anthropic Console
  workspace limits, OpenAI project budget) before the first paid run, a
  little above `--total-cap`. The ledger is this project's cap; the
  provider's limit is the backstop if a bug or a second machine gets past it.
- **Watch the truncation rate.** Every request may write up to `--max-tokens`
  (16000 by default), and the reservation is that full amount. After the
  first small run, read the job log: a reply cut at the output limit (a
  `result` line with `status: truncated`) is a fault and is asked
  again, so many cuts double the spend and leave `partial` tags. If cuts
  appear, the limit is too low for that output size or the model is
  rambling; if the largest real output is far below the limit, lower
  `--max-tokens` to free room under the caps (a new limit is a new cache
  key, so only untagged outputs are affected).

### After a crash

The job log `data/tagger/<run>/jobs.jsonl` is written before and after every
step ([store.py](store.py)). **Resume with the same `--run` and `--ledger`**:
a job's `prepared` line names the ledger file and ledger batch its requests
are reserved in, and a run with another ledger or batch is refused (exit 2)
rather than settle them where they were not reserved. A new `--run` on the
same cache does not send again what another run has in flight (the run list
`<cache>.runs` names every job log that used the cache); it says which run
holds those requests. On the next run:

- a job prepared but never sent: its reservations are settled at zero and
  its requests sent again. `prepared` is written with the call ids before
  any reservation is made, so a crash while reserving leaves nothing the
  next run cannot find;
- a job whose create request was sent with no answer: it may exist, and
  neither API takes an idempotency key, so it is never created again blind.
  The provider's job list is searched: an OpenAI job by the
  `sibar_submission` value in its metadata; an Anthropic job, which holds no
  metadata, by its size and a creation time within 15 minutes. One match is
  adopted, and when its results come every `custom_id` must be one this run
  sent, or nothing is settled (exit 4). No match, or several, blocks the run
  (exit 4): check the provider's console, then wait for the job, or run
  again with `--abandon JOB` if it does not exist. An abandoned job's
  reservations stay in the ledger at their worst case;
- a job that was submitted: collected when it ends, even by a later run
  (`Ledger.reopen` settles a reservation made by an earlier run). It cannot
  be abandoned: wait for it, or cancel it at the provider, and its
  unprocessed requests are sent again when it is collected;
- if the ledger cannot record a settlement (a damaged file, a missing
  reservation), the run stops (exit 4) with the result kept in the job log;
  only "already settled" (a run that stopped after settling) is passed over.

Only one tagging run may use a run folder or a cache file at a time (the
same operating-system lock as the ledger).

## Agreement

    python -m tagger agreement --type pipeline --a human/tags.yaml \
        --b data/tagger/cal-haiku/records.claude-haiku-5-5.jsonl [--json out.json]
    python -m tagger agreement --type pipeline --a CLAUDE.jsonl --b OTHER.jsonl \
        --family anthropic

Side A is the reference. A side is a human tag file (`.yaml`) or a tagged
record file. The command prints, as [docs/rubrics.md](../docs/rubrics.md),
"Calibration (T2.5)" defines them: A(i) with its number of outputs for every
item, AC1 for single-select items, the `cannot-tell` rate, the rubric
agreement A with a 95% bootstrap interval over outputs, the pooled agreement
of items on fewer than 20 outputs, minority agreement, and the four
conditions of the bar. `--family PROVIDER` adds the cross-family check: the
agreement gap between outputs written by that provider's models and the
others, and the direction per answer, each with a bootstrap interval,
flagged at 0.10 or more when the interval leaves out 0. AC1 takes K as the
number of answers either side gave, which reproduces both worked examples in
docs/rubrics.md.

Two readings of docs/rubrics.md: an output whose tagging ended in
`status: error` has no answer, so it is left out of every measure and
counted on its own line (docs/rubrics.md scores `cannot-tell` because it is
an answer; an error is not). A `null` item of a `partial` tagging stays a
`cannot-tell`, as the metrics read it. Minority agreement counts only the
judgements where A answered the item: where A stopped at the gate, the
items after it have no A answer.

## The human tag file

    python -m tagger template --type pipeline --records FILE... \
        --sample 30 --seed 1 --out data/tagger/human-pipeline

writes `tags.yaml` and one reading sheet per output in `sheets/`. A sheet
holds the rubric's instructions, the items with their options in the same
order the tagger sees for that output, and the response. It does not name
the model, the prompt or the level. T2.5 chooses the 30 (`--record-id`,
repeated, takes an exact list). The outputs are listed in random order.

```yaml
schema_version: 1
kind: human-tags
rubric: pipeline.v1
tagger: human            # a role, never a person's name
pass: 1                  # 2 for the Human's repeat of 10 outputs
outputs:
  - record_id: 0b1e...
    task: csv-to-database
    sheet: sheets/0b1e....md
    items: [response_mode, assumptions_stated, ...]   # gate first
    answers:
      response_mode: answers              # an answer id
      cleaning_steps: [removes-duplicates, trims-whitespace]
      rerun_behavior: not-applicable
      opening: cannot-tell
      bad_input_handling: none            # or [none]
```

Every item must be answered; write `cannot-tell` rather than leave one
blank. When the gate is `asks-first`, `declines` or `cannot-tell`, leave the
other items blank (`~`). The file is refused, with every problem listed, if
an answer is not an answer of its item.
