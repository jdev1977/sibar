# runner

Python package for producing run records: their format and validator, and the
generation runs against the models under test.

- `models.py` loads and checks [models.yaml](../models.yaml), the list of
  models under test (T0.2). The list is not final until `confirmed_by_human` in
  it is `true`.
- `record.py` defines the run record format, its validator and the JSON Lines
  file handling (T0.4); see [docs/record-format.md](../docs/record-format.md).
  `python -m runner.record FILE...` validates record files.
- `ledger.py` records the cost of every call and enforces a hard budget cap
  (X3); see [docs/ledger.md](../docs/ledger.md). `python -m runner.ledger`
  prints totals by batch and model.
- The generation runner (T0.5), described in
  [docs/runner.md](../docs/runner.md); not yet verified against the live APIs:
  - `run.py`: the command line, `python -m runner.run`;
  - `loop.py`: the run loop (plan cells, resume, reserve, send, settle, record);
  - `providers/`: one adapter per provider (Anthropic, OpenAI, Google,
    DeepSeek) behind one interface;
  - `transport.py`: HTTPS with the standard library, injectable for tests;
  - `sse.py`, `retry.py`, `ratelimit.py`, `scrub.py`: streamed events,
    retries, request rate, key removal;
  - `files.py`: files extracted from responses;
  - `prompts.py`: the prompt file loader (format in
    [prompts/README.md](../prompts/README.md)).

Run output goes to the gitignored `data/`, not here.

Filled by these tasks in [tasks.md](../tasks.md):

- T0.4: run record format and validator
- T0.5: generation runner
- T6.1: one-command re-run for a new model
