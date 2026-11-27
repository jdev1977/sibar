# The answer checker

Grades the final answers of math and engineering outputs against the
reference answers in [references/](references/README.md) (task T2.10). The
worked solutions are in [docs/references/](../docs/references/README.md). It
reads text; it runs nothing from an output and calls no model.

**The engineering answers are study data, not designs.** Every engineering
result carries that note.

The rule behind every choice here: a false "correct" or a false "wrong" is
worse than "could not determine".

## Usage

    python -m checker --records FILE
    python -m checker --records FILE --record-id ID --answers answers.yaml
    python -m checker --records FILE --answers answers.yaml --no-extract
    python -m checker --task math/loan-amortization --level L0 --response reply.md
    python -m checker --task engineering/heat-sink --level L2 --answers answers.yaml

With `--records`, every math and engineering record with status `ok` or
`truncated` gets a `checks` entry named `checker` (an earlier one is
replaced), and the file is rewritten once, atomically. Nothing is written if
the answers file or the record file is refused. The same record, answers and
checker version give the same bytes. With `--task`, one result is printed as
JSON.

Exit code 0: done. 1: some record could not be graded. 2: refused.

## The result

The entry's `outcome` is `ok` when the response was graded, whatever the
grade, and `error` when it could not be (no reference file, no level, or a
`prompt_set_version` other than the one the reference was solved from;
`detail.reason` says which). `detail` holds:

| Field | Meaning |
|---|---|
| `verdict` | The level: `correct`, `correct_alternative`, `wrong`, `incomplete`, `could_not_determine` or `not_checkable` |
| `answers_verdict` | The same, from the reference values alone, without the criteria |
| `partial` | The reference values cover only part of what is asked: `correct` says that part is right, and no more |
| `quantities` | Per quantity: `status` (`correct`, `correct_alternative`, `wrong`, `not_stated`, `could_not_determine`), the `alternative`, a `reason`, and each `stated` value with its `source` (`extracted` or `supplied`) |
| `criteria` | Per criterion and item: `pass`, `fail`, `could_not_determine` or `not_applicable`; `record_only` items are marked and decide nothing |
| `alternatives` | The alternatives the answer matched |
| `answers_from` | `extracted`, `supplied` or both |
| `task`, `prompt_set_version`, `reference_sha256` | What it was graded against |

### How the level verdict follows

- `wrong`: a graded quantity is wrong (an `if_reported` one included: it may
  be missing, not wrong), or a criterion fails.
- Otherwise `could_not_determine` if a required quantity is undetermined, or
  another quantity has several statements that do not settle.
- `incomplete`: a required quantity, or every `one_of` group, is not stated.
- `correct` or `correct_alternative`: every required quantity and one
  `one_of` group are right. At a level that is not `partial`, every criterion
  must also pass; until then the verdict is `could_not_determine` and
  `answers_verdict` says what the values showed.
- `not_checkable`: the level has no reference answer. Side checks are still
  listed.

A text item about a figure the response does not state (the conveyor's
stated ratio and speed) is `not_applicable` when that quantity is
`not_stated`.

Items of a criterion that only a reader can judge (the kind of pump, the
shape of an outline) stay undetermined until an answers file judges them. So
the extractor alone never gives a level verdict of `correct` for pipe and
pump at L2.

## Answers files

YAML or JSON, written by a person, a tagger or a model. One entry, or a list
of entries each with a `record_id`. An entry without `record_id` needs
exactly one record (`--record-id`).

```yaml
record_id: 0f6c...             # optional with one record
complete: false                # true: this is everything the response states
quantities:
  overall_ratio: {value: 28.47, inputs: {motor_rpm: 1450}}
  drum_speed: {value: 50.9, unit: rpm}
  decision: {value: reject}                    # a choice
  residuals: {value: {1: 0.139, 2: -0.007}}    # a list: key to value
  p_value: not_stated
  ph_at_volume:                                # several statements
    - {value: 4.92, unit: pH, inputs: {base_ml: 15, ka: 1.8e-5, kw: 1.0e-14}}
inputs: {z1: 12, z2: 68, z3: 12, z4: 72}       # shared by formulas and criteria
conditions: {one_face: true}   # an alternative's id: stated or not
facts: {test: wilcoxon_exact, level_percent: 5}   # hypothesis test only
criteria:                      # a reader's judgement of an item
  pump_kind: {kind_named: pass}
```

- Quantity ids, input names, criterion and item ids, and alternative ids are
  those of the reference file. Inputs are numbers in the unit the reference
  file gives for them. A quantity with a unit needs one (a unit the reference
  lists); without it the value is not graded.
- `complete: false` (default): what is missing is unknown (a hypothesis
  decision then needs `facts.level_percent`, unless the extractor ran). The values go over
  the extracted ones, quantity by quantity.
- `complete: true`: the entry replaces the extracted values. A quantity left
  out is `not_stated`, a condition left out is not stated, the range for an
  unstated choice applies, the hypothesis test is the t test and the level 5%
  unless `facts` says otherwise, and the spring `life` criterion takes its
  default limit.
- `facts.test`: `t`, `z`, `wilcoxon` (variant unknown), `wilcoxon_exact`,
  `wilcoxon_normal`, `wilcoxon_normal_corrected`, `sign_flip_permutation`,
  `sign_test` or `other`.

## Grading rules worth knowing

- A value that matches an alternative counts only when the response states its
  condition. If that is not established, the result is
  `could_not_determine`; if it is known not to be stated, `wrong`.
- A conditional quantity is graded against the stated inputs. Without them it
  is not graded, except for the two quantities with a `range`, and then only
  from a `complete` answers file.
- The hypothesis p-value is graded against the test used, and the decision
  against the rule "reject when that test's p is below the stated level".
- A response that states an effective annual rate (or residuals as fitted
  minus measured) and gives the reference value is not graded.

## Extraction

[extract.py](extract.py) is the deterministic extractor. It returns the same
structure an answers file gives (`checker.answers.Answers`), which is the
seam for a model-based extractor: produce that structure, and grading is
unchanged.

It reads the reply's prose, its tables and plain-text blocks, and any named
Markdown or text file of the output. It does not read code or what code
would print.

### What it finds

- A value after its own label: `Monthly payment: $178.21`, `x̄ = 409.4/8 =
  51.175` (the last part of a chain), or a table row. The label must match as
  a whole ([labels.py](labels.py)). Where a bare name is ambiguous, a
  qualifying word is needed: "required total resistance", "final side
  length", "resulting junction temperature", "required ratio", "actual
  rate".
- Keyed tables: a full 60-row loan schedule, the pH table, the differences
  and ranks of the measurements, the residuals by x.
- A fitted line `y = a + bx`, a 95% interval, the decision on H0, the
  governing limit of the beam.
- For the hypothesis test, the tests and significance levels the text
  mentions.

### Where conditional inputs come from

| Input | How it is found |
|---|---|
| Motor speed (conveyor) | The one speed of 500 rpm or more in the text; two different ones leave it unknown |
| Wire diameter, coil diameter, active and total coils (spring) | Their labels, with units; two different values leave it unknown |
| Bracket radius | Its label |
| Screw positions `e`, `s`, `a`, `p`; tooth counts | Not extracted: answers file |
| Pipe roughness, water temperature, viscosity, Hazen-Williams C, fittings | Not extracted: answers file |
| Heat-sink interface and sink resistance, junction target | Not extracted: answers file |
| Force on the spring, solid length and stresses used by criteria; stated limits and allowables (beam, spring life, pump rating) | Not extracted: answers file |
| Acid constants | Not extracted: answers file |
| Load factor, self-weight, belt thickness | Not extracted. A mention keeps the matching alternative open |

A criterion is never failed on an extracted input alone.

### Assumptions of the response's own

Where the text mentions one, an extracted value that differs is
`could_not_determine`, not `wrong`, for the quantities that follow from it
(the patterns are `DOUBTS` in [labels.py](labels.py)): a margin or safety
allowance or factor (heat sink, pipe and pump, beam, conveyor, bracket,
spring; for the beam not the dictated factor of 3), a junction target (heat
sink), a load factor or self-weight (beam, bracket), belt slip or thickness,
a preload, fees, taxes, insurance or extra payments, another temperature or
activity corrections, points left out or weighted, a launch height, wind or
spin, and, for the mean and its interval, differences. A right value is still
`correct`.

The patterns are broad on purpose, because a false "wrong" is worse than
"could not determine". Only these are taken as harmless (`BENIGN` and
`UNCHARGED`), and not where the same sentence states an added amount: an
interval that excludes 50, the target or zero; a "significant difference";
a note without any figure that the payment excludes taxes, insurance or fees;
"for safety, use ..." operating advice without figures or sizing words; a
fuse margin above the current; an initial height of 0; "ignore spin and
wind".

### When it concludes nothing

The result is `could_not_determine` when there is no labelled value; when the
only ones stand in a condition, comparison, check, option or trial; when
statements disagree; when a labelled statement with a number cannot be read
(a range, a decimal comma, a space as thousands separator, an unknown unit or
trailing words); when a differing value was found but a matching number is
also somewhere in the response; for any mismatch, when the response is cut
off; and when a correction ("actually", "correction", "revised") or a
summary holds a number that was neither read nor given and could replace the
value: one under that quantity's label, or else in a unit it accepts, or
with no label and no known unit (then every value).

### What is not extracted

Quantities with no label pattern, among them every entropy count, the pipe's
friction and Reynolds number at L0 and L1, `ph_at_volume`, the tooth-count
and stated-section quantities, most intermediate values and the screw force
alternatives. `not_stated` is never concluded from text: only an answers file
can say it.

## Blind spots

- **Graded accuracy is biased upward.** Where a harmless mention cannot be
  told from a real assumption, the doubt stays, so a wrong value beside it is
  `could_not_determine` while a right one is `correct`. Examples: "no safety
  factor is applied", "no outliers were removed", "no fees", "assume no
  slip", "this leaves some margin", "the design junction temperature is
  125 °C", "the ball returns to its launch height", "significant
  differences". Count `could_not_determine` results, and read a sample,
  before comparing accuracy between groups.
- Recall is low by design. Expect many `could_not_determine` results; send
  those to a reader or a model-based extractor.
- The extractor can be fooled. A labelled figure may be an unflagged
  intermediate or rejected value while the real conclusion is written in a
  form it does not read. The guards above narrow this; they cannot close it.
  Spot-check extracted `wrong` and `correct` results against the response
  before relying on counts.
- Money is graded to the cent, as the references set it. A response that
  rounds money in the labelled line itself ("Monthly payment: $178", "Total
  interest: $1,693") is graded `wrong` unless the precise figure also appears
  somewhere in it.
- The wordings that put a value in doubt are a fixed list. A margin,
  assumption or correction worded another way is not noticed, and the value
  that follows from it can be graded `wrong`.
- Hedging and conditions are recognised by English words only. Replies in
  other languages, or numbers in images, are not read.
- Whether an alternative's condition is stated is judged by the absence of a
  few words. A response that states an assumption in other words is graded as
  not stating it.
- The checker grades final values, not the method, the working, the CAD file
  or the explanation.
- A `correct` at a `partial` level says nothing about the sizing.

## Tests

    python -m pytest tests/test_checker_grade.py tests/test_checker_extract.py tests/test_checker_records.py tests/test_reference_solutions.py

## Changing it

Raise `VERSION` in [records.py](records.py) whenever the same record and
answers could give a different result.
