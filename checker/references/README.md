# Reference answers for the checker

One YAML file per math and engineering task, at
`checker/references/<type>/<task_id>.yaml`. Each holds the answers that the
answer checker (T2.10 in [tasks.md](../../tasks.md)) grades a model's final
answer against, with the tolerance for each and the reason for it. Written
for T2.3. The worked solution behind each file is in
[docs/references/](../../docs/references/README.md), one document per task.

**The engineering answers are study data, not designs.** They exist to grade
answers collected for a study of model defaults. Do not build from them.

The checker itself is T2.10 and is not written yet. This folder is data only.

## How the numbers are kept right

`python -m pytest tests/test_reference_solutions.py` recomputes every number
in these files from the givens, with plain Python in
[tests/reference_solvers.py](../../tests/reference_solvers.py), and checks the
shape of each file. A changed prompt given or a mistyped value fails the
test. The test also checks that each file names the prompt set version it was
solved from, and that every given is found word for word in the prompts.

## File format

```yaml
schema_version: 1
project_type: engineering        # the folder name
task_id: heat-sink               # the file name without .yaml
prompt_set_version: "1"          # version of the prompt file this was solved from
title: Size a heat sink
study_data_note: ...             # engineering files only, always present there
givens:                          # numbers every prompt of the task carries
  - {id: power, text: "20 W", value: 20, unit: W}
l2_givens:                       # numbers only the L2 brief carries
  - {id: pad, text: "0.3 °C/W", value: 0.3, unit: °C/W}
assumptions:                     # what the reference assumes where the prompts are silent
  - Steady state.
levels:
  L0:
    checkable: true
    note: ...
    quantities: [total_resistance]     # graded; a complete answer has them
    if_reported: [temperature_rise]    # graded only when the answer states them
    criteria: [sink_is_adequate]       # pass criteria for an open choice
  L1: ...
  L2: ...
quantities:
  total_resistance: ...
criteria:
  sink_is_adequate: ...
```

`text` in a given is the exact string in the prompts. `givens` are in all six
prompts of the task; `l2_givens` are in both L2 wordings.

### Levels

- `checkable` says whether the level has a reference answer to the question
  asked. Where it is false the `note` says why, and the checker records no
  correctness result for that level.
- `quantities` are the answers a complete response gives. `if_reported` are
  graded only when the response states them (an intermediate value, an extra
  figure). A missing `if_reported` value is not an error.
- `criteria` are pass criteria for choices with no single right value (a
  pump, a set of tooth counts, a spring).
- `consistency` lists formulas that check a response's own numbers against
  each other. It is used at levels that are not checkable, and it is not a
  correctness grade.

A level that is not checkable can still list `if_reported`, `criteria` or
`consistency` entries. They are side checks and do not grade the answer.

### Quantities

```yaml
quantities:
  plate_area:
    description: Total cooled area of the plate, both faces together
    kind: fixed                  # fixed | conditional
    type: number                 # number (default) | integer | choice | list | date
    unit: m²                     # "1" for a pure number
    value: 0.03390
    exact: "2/59"                # optional exact form
    tolerance: {rel: 0.01, why: "..."}
    tolerance_at:                # optional: another tolerance at some levels
      L2: {abs: 0.001, why: "..."}
    other_units:                 # accepted units and how to convert
      - {unit: cm², factor: 10000}
    alternatives:                # accepted for a stated, legitimate other assumption
      - id: one_face
        condition: The answer says it gives the area of one face.
        levels: [L2]             # optional: where it applies (default: everywhere)
        value: 0.01695
    accepted_examples:           # values the tolerance is meant to accept
      - {value: 0.0339, why: Three significant figures}
    not_accepted:                # known wrong answers the tolerance must reject
      - {value: 0.0678, why: One face taken as the whole cooled area}
```

- **`kind: fixed`**: one reference `value` follows from the givens and the
  reference's assumptions.
- **`kind: conditional`**: the answer depends on a choice the model states
  (a motor speed, a pipe roughness, a screw spacing). The file gives
  `inputs` (the stated choices), and a `formula` or, where no closed formula
  exists, a `method` in words. `examples` are worked cases. A conditional
  quantity may also carry a `value`, the answer under the reference's own
  standard assumption, and a `range`, the span accepted when the model does
  not state the choice. Grade a conditional quantity against the model's own
  stated inputs.
- **`type: choice`**: `value` is one of `choices` (a decision, a governing
  limit), and `rule` says in words how the choice follows.
  **`type: integer`**: a whole number, compared exactly.
  **`type: list`**: `value` is a list, and the tolerance applies to each
  element. **`type: date`**: an ISO date.
- `accepted_examples` and `not_accepted` are test values for the checker:
  right answers the tolerance is meant to pass, and answers from known
  mistakes it must fail. `not_accepted` is judged against the reference
  value alone; a listed value can still be right under an alternative whose
  condition the response states.

### Tolerance

`tolerance` holds `abs`, `rel` or both, and `why`. A stated value `x` passes
against reference `r` when `|x − r| ≤ abs`, or when `|x − r| ≤ rel × |r|`.
With both set, either is enough. `{abs: 0}` means exact. A quantity of type
`choice` or `date` has no tolerance. `tolerance_at` replaces the tolerance
at the levels it names.

For a conditional quantity the tolerance is applied to the value its formula
gives. A `range` is taken as written: a value from `low` to `high` passes,
and the tolerance is not added to it.

### Alternatives

An alternative is a second accepted value, for a legitimate assumption that
differs from the reference's. Its `condition` says what the response must
state for it to apply; grade against the alternative only when the response
states that assumption. An alternative has its own `value`, or its own
`formula`, `inputs` and `examples`, and may have its own `tolerance` (else
the quantity's). Alternatives with the same `id` on several quantities of one
file belong to the same assumption. A result that matched an alternative
should be recorded as such, not as a match of the reference.

### Units

`unit` is the unit of `value`. Each entry of `other_units` is another unit
that is accepted: the reference value in that unit is `value × factor`
(`+ offset` where given). Compare in the unit the response uses, with the
same relative tolerance, or with the absolute tolerance multiplied by
`factor`.

### Formulas

`formula` is an arithmetic expression in Python syntax over the names in
`inputs`: numbers, `+ - * / **`, brackets, and the functions `sqrt`, `log10`,
`abs`, `min`, `max`, with the constant `pi`. A `check` in a criterion is
the same with comparisons (`<`, `<=`, `>`, `>=`, `==`), `and`, `or` and
`not`, and is true when the criterion is met. Nothing else is allowed, so a
checker can evaluate them without running arbitrary code. The test evaluates
every formula on its examples.

### Criteria

```yaml
criteria:
  pump_choice:
    description: The kind of pump chosen
    pass_when:
      - id: duty_covered
        text: The pump is rated for at least the flow and head worked out.
        inputs: {rated_flow_l_per_s: {description: ..., unit: L/s}}
        check: "rated_flow_l_per_s >= 1.5"
      - id: reason_given
        text: The reason refers to the flow and head.
```

An item with a `check` can be tested from numbers the response states. An
item with `text` only needs a reader (a person or the tagger). A criterion
may carry `all_passing`: the complete list of input sets that pass its
checks, where that list is short enough to write down (`note`, `inputs`,
`sets`).

## Writing numbers

Write a number with a decimal point or as a plain whole number. The YAML
reader used here takes `1e6` and `10.0e6` as text, not as numbers (an
exponent needs a decimal point and a sign: `1.0e+6`). Inside a `formula` or
a `check`, which are text, `1e6` is fine. The test fails on a value or an
example input that is not a number.

Put a `why`, `text` or `note` that contains a comma or a colon in quotes when
it sits inside `{ ... }`. Unquoted, the comma ends the entry.

## Assumptions the files share

- Grade a value against the precision of the givens: a correctly rounded
  answer passes, and the tolerances are set for that.
- Where a prompt leaves a standard assumption unstated (a nominal annual
  rate charged monthly, a textbook acid constant, ordinary least squares),
  the file's `assumptions` state it. Whether the model states it too is
  recorded elsewhere; it does not change the grade.
- A different method that reaches the same value passes. The files grade the
  final answers, not the method. Whether a model followed a dictated method
  is read by the extractors and the rubric.
