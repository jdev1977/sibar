# runner

Python package for producing run records: their format and validator, and the
generation runs against the models under test.

- `models.py` loads and checks [models.yaml](../models.yaml), the list of
  models under test (T0.2). The list is not final until `confirmed_by_human` in
  it is `true`.
- `record.py` defines the run record format, its validator and the JSON Lines
  file handling (T0.4); see [docs/record-format.md](../docs/record-format.md).
  `python -m runner.record FILE...` validates record files.

Run output goes to the gitignored `data/`, not here.

Filled by these tasks in [tasks.md](../tasks.md):

- T0.4: run record format and validator
- T0.5: generation runner
- X3: cost ledger and budget cap
- T6.1: one-command re-run for a new model
