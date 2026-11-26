# prompts

Task prompts, one folder per project type (`prompts/<type>/`). Each task is
written at three levels of direction (L0, L1, L2) and two wordings; Wave 3 types
start at one wording. Prompts are versioned and use neutral wording, with no
product or project names.

Filled by these tasks in [tasks.md](../tasks.md):

- T1.1, T1.2: website prompts and their leak check ([website/](website/README.md)).
  The leak-check rules for every type are in
  [docs/leak-check.md](../docs/leak-check.md).
- T2.1, T2.2: pipeline, math or science, and engineering prompts and leak check
- W2.x.1, W2.x.2: Wave 2 prompts and leak check
- W3.x: Wave 3 prompts

## File format

One YAML file per task, at `prompts/<type>/<task_id>.yaml` (`.yml` also
works). [runner/prompts.py](../runner/prompts.py) loads and checks it, and the
runner (`python -m runner.run --prompts ...`) sends it. Example:

```yaml
schema_version: 1
project_type: website          # must equal the folder name
task_id: bakery-landing        # must equal the file name without .yaml
prompt_set_version: "1"        # text, so quote it
prompts:
  L0:
    A: Make a website for a bakery.
    B: Build a website for a bakery.
  L1:
    A: Make a website for a neighborhood sourdough bakery that takes weekend pre-orders.
    B: ...
  L2:
    A: |
      A longer brief over several lines...
    B: |
      ...
notes: Optional text for prompt authors, such as leak-check reasons. Never sent.
```

Rules:

- `project_type` and `task_id` are slugs: lower-case letters, digits, `.`,
  `_` and `-`, starting with a letter or digit.
- `prompt_set_version` is text with no spaces. Raise it whenever any prompt in
  the set changes: records carry it, and a resumed run never counts records of
  another version as done.
- `prompts` holds all three levels. Each level has wording `A`, and wording
  `B` unless the type uses one wording (Wave 3 types at first). No other
  levels or wordings are allowed.
- Each text is non-empty. Leading and trailing whitespace (including the final
  line break that `|` adds) is removed; the rest is sent exactly as written.
- Unknown keys and repeated keys are errors.

A small example lives in the tests:
[tests/fixtures/prompts/example/tiny-task.yaml](../tests/fixtures/prompts/example/tiny-task.yaml).
It is not a real task.
