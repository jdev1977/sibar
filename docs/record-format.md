# Run record format (schema version 1)

Every generation is stored as one **run record**: a JSON object on one line of
a JSON Lines file. The format is defined in [runner/record.py](../runner/record.py);
this page describes it. If the two disagree, the code is right and this page is
a bug.

Validate files with:

```
python -m runner.record runs.jsonl            # records only
python -m runner.record --files runs.jsonl    # also check stored files
```

## Fields

Every field below is required. A field that does not apply holds `null` (or an
empty list); unknown fields are rejected.

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | `1`. Changes whenever the field list or a rule changes. |
| `record_id` | text | Lower-case UUID, unique across all records. |
| `source` | text | `controlled` (sent by the runner), `uncontrolled_import` (taken from an outside dataset, such as the historical website baseline) or `manual` (typed by hand, as on the product surface). |
| `source_note` | text or null | Where an import or manual record came from: dataset name, version and original id; or the product used. |
| `project_type` | slug | `website`, `pipeline`, `math`, `engineering`, and more later. Any slug is accepted. |
| `task_id` | slug | The task within the type, as named in `prompts/<type>/`. |
| `prompt_set_version` | text | Version of the prompt set the prompt came from. |
| `level` | text | `L0`, `L1` or `L2`. |
| `wording` | text | `A` or `B`. Types with one wording use `A`. |
| `run_index` | integer | Which run of the cell, from 1. |
| `prompt_text` | text | The exact prompt sent. |
| `provider` | slug | The provider, as in `models.yaml`. |
| `model_id` | text | The exact model ID called (no spaces). |
| `surface` | text | `api` or `product`. |
| `system_prompt` | text or null | The system prompt sent. Always null for controlled records; null when unknown. |
| `settings` | object | The parameters sent with the request, exactly; `{}` when none were sent. |
| `timestamp` | text | When the request was sent: ISO 8601 in UTC ending in `Z` (or `+00:00`), such as `2026-11-25T14:03:07.250Z`. |
| `tokens` | object | `input`, `output`, `reasoning`: each a whole number of at least 0, or null when not reported. |
| `cost_usd` | number or null | Cost of the call in US dollars, or null when not known. |
| `status` | text | `ok`, `failed` (no usable response), `refused` (the model declined) or `truncated` (stopped by a length limit). |
| `error` | text or null | What went wrong. Required when `failed`; must be null when `ok`. |
| `stop_reason` | text or null | The provider's stop reason, as returned. |
| `raw_response` | text or null | The model's text output, unedited. Required and non-empty when `ok`. |
| `files` | list | Files extracted from the response (see below). |
| `checks` | list | Sandbox, render and reference-answer results (see below). Empty when none were run. |
| `features` | list | Extracted features (see below). |

Slugs are lower-case letters, digits, `.`, `_` and `-`, starting with a letter
or digit.

### Rules across fields

- A `controlled` record is on the `api` surface and has a null `system_prompt`.
- `prompt_set_version`, `level`, `wording` and `run_index` may be null only on
  an `uncontrolled_import`, whose source did not follow the grid.
- Checks between fields run only when each field is valid on its own, so one
  mistake is reported once.

### `files` entries

```json
{"path": "src/index.html", "sha256": "<64 lower-case hex digits>", "size": 131}
```

`path` is relative to the record's **data directory**, which is
`files/<record_id>/` beside the JSONL file (`runner.record.files_dir`). It uses
`/`, and has no empty, `.` or `..` parts, no leading `/`, drive, colon or
backslash. `size` is in bytes. No path may appear twice in a record, counting
the files of `checks` too.

### `checks` entries

```json
{"name": "render.desktop-light", "tool": "render", "tool_version": "1",
 "outcome": "ok", "detail": {"width": 1440}, "files": [ ... ]}
```

One entry per thing done to the output after generation: a screenshot, a
sandboxed run, a comparison with the reference answer. `outcome` is `ok` (done
and passed), `failed` (done, and the output failed it, such as failing tests or
a wrong answer) or `error` (the check itself could not run). `detail` is any
JSON, such as test counts or the final answer found. `files` holds what the
check produced, such as screenshots, with the same rules as `files` above.

### `features` entries

```json
{"name": "fonts", "value": ["system-ui"], "extractor": "website-css", "extractor_version": "1"}
```

`value` is any JSON. Within a record, each extractor appears at one version
only, and each (extractor, name) pair once. Re-running an extractor replaces all
its entries (`runner.record.with_features`). Rubric tagging by a model is
stored the same way, with the rubric as the extractor.

## The file

- UTF-8 JSON Lines, one record per line, ending in `\n`. Non-ASCII characters
  are written as `\u` escapes, so no reader can split a record.
- A record is written only once its newline is on disk. A last line without a
  newline is an interrupted write: readers report it and ignore it, and
  `repair_tail` cuts it before the next append. A resumed run redoes that cell.
- Any other bad line (invalid JSON, invalid record, blank line, repeated
  `record_id`, `NaN`, a repeated key) is an error.
- One writer per file at a time.

## Cell key

`runner.record.cell_key(record)` gives (project type, task, level, wording,
model, surface, run index): the grid cell a record fills. A resumed run skips
cells that already have a record it accepts, such as one with status `ok`.
Several records may share a cell, for example a failed attempt and its retry.

## Why the standard library and not `jsonschema`

The rules that matter most here (UTC-only timestamps, portable relative paths,
"an ok record needs its raw response", null allowed only on imports, one
version per extractor) would be Python code even with a JSON Schema, and the
library would add several pinned dependencies. The validator returns every
problem found, not only the first.

## Versioning

Any change to the field list, a field's type or a rule raises
`schema_version`. Records of an older version are rejected by the newer
validator until a migration exists; never edit old records in place to fit.
