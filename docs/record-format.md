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
| `batch_id` | text or null | The batch (one planned run of the grid, such as `pilot-1`) the record belongs to; no spaces. Null for records made outside a batch. |
| `source` | text | `controlled` (sent by the runner), `uncontrolled_import` (taken from an outside dataset, such as the historical website baseline) or `manual` (typed by hand, as on the product surface). |
| `source_note` | text or null | Where an import or manual record came from: dataset name, version and original id; or the product used. |
| `project_type` | slug | `website`, `pipeline`, `math`, `engineering`, and more later. Any slug is accepted. |
| `task_id` | slug | The task within the type, as named in `prompts/<type>/`. |
| `prompt_set_version` | text | Version of the prompt set the prompt came from. |
| `level` | text | `L0`, `L1` or `L2`. |
| `wording` | text | `A` or `B`. Types with one wording use `A`. |
| `run_index` | integer | Which run of the cell, from 1. |
| `prompt_text` | text | The exact prompt sent. |
| `provider` | slug | The model's maker, as in `models.yaml` (such as `anthropic`), even when the call went through a gateway. |
| `gateway` | slug or null | The multi-provider gateway the call went through, or null for a direct call to the maker's API. |
| `model_id` | text | The exact model ID requested (no spaces). It may contain `/` or `:`; anyone building a file path from it must sanitise it first. |
| `model_id_returned` | text or null | The model ID the response reported, when it differs or is more exact (such as a dated snapshot); null when not reported. |
| `surface` | text | `api` or `product`. |
| `system_prompt` | text or null | The system prompt sent. Always null for controlled records; null when unknown. |
| `settings` | object | The parameters sent with the request, exactly; `{}` when none were sent. |
| `timestamp` | text | When the request was sent: ISO 8601 in UTC ending in `Z` (or `+00:00`; `-00:00` is rejected), such as `2026-11-25T14:03:07.250Z`. |
| `tokens` | object | `input`, `output`, `reasoning`: each a whole number of at least 0, or null when not reported. |
| `cost_usd` | number or null | Cost of the call in US dollars, or null when not known. |
| `status` | text | `ok`, `failed` (no usable response), `refused` (the model declined) or `truncated` (stopped by a length limit). |
| `error` | text or null | What went wrong. Required when `failed`; must be null when `ok`. |
| `stop_reason` | text or null | The provider's stop reason, as returned. |
| `request_id` | text or null | The provider's or gateway's id for the request or response, for tracing a call later; no spaces. |
| `raw_response` | text or null | The model's text output, unedited. Required when `ok`, and must not be empty or only whitespace (the stored text is never stripped). |
| `files` | list | Files extracted from the response (see below). |
| `checks` | list | Sandbox, render and reference-answer results (see below). Empty when none were run. |
| `extractors` | list | Every extractor that has run on the record, with its version, including ones that found nothing (see below). |
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
backslash, no part ending in a space or dot, and no Windows reserved name
(`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, with or without an
extension, in any case). `size` is in bytes. No path may appear twice in a
record, counting the files of `checks` too and ignoring case, since Windows
and macOS file systems ignore case by default.

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

### `extractors` and `features` entries

```json
"extractors": [{"extractor": "website-css", "extractor_version": "1"},
               {"extractor": "website-icons", "extractor_version": "1"}],
"features": [{"name": "fonts", "value": ["system-ui"],
              "extractor": "website-css", "extractor_version": "1"}]
```

`extractors` lists every extractor that has run on the record, once each, with
the version that ran. An extractor that ran and found nothing appears there
with no features, so "not run" and "found nothing" stay distinct. Every feature
names an extractor listed there, at the same version. `value` is any JSON, and
each (extractor, name) pair appears once.

Re-running an extractor replaces all its entries and its `extractors` version
(`runner.record.with_features`; empty values mark a run that found nothing).
Re-extraction therefore **rewrites the file**: read it with `read_records`,
update each record with `with_features`, and write it back with
`write_records`, which validates everything first and replaces the file
atomically (temporary file in the same directory, flushed to disk, then
`os.replace`). It refuses to run over a file with bad or truncated lines, which
would be lost, unless told to discard them.

**Model-based rubric tagging** is stored the same way, with this naming:

- `extractor` is `rubric.<project_type>`, such as `rubric.website`.
- `extractor_version` is `<rubric version>@<tagger model id>`, such as
  `3@claude-haiku-5-5`, so a new rubric version or a different tagging model
  counts as a different version and replaces the earlier tags.
- `name` is the rubric item's id, and `value` the chosen option (or a list of
  options for a multi-select item).

## The file

- UTF-8 JSON Lines, one record per line, ending in `\n`. Non-ASCII characters
  are written as `\u` escapes, so no reader can split a record.
- A record is written only once its newline is on disk. A last line without a
  newline is an interrupted write: readers report it and ignore it, and
  `repair_tail` cuts it before the next append. A resumed run redoes that cell.
- Any other bad line (invalid JSON, invalid record, blank line, repeated
  `record_id`, `NaN`, a repeated key) is an error.
- `write_records` replaces a whole file atomically; use it for rewrites, never
  edit a record file in place.
- One writer per file at a time.

## Cell key

`runner.record.cell_key(record)` gives (batch, project type, task, prompt-set
version, level, wording, model, surface, run index): the grid cell a record
fills. A resumed run skips cells that already have a record it accepts, such as
one with status `ok`. A new batch or a revised prompt set therefore never
treats older records as filling its cells. Several records may share a cell,
for example a failed attempt and its retry.

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
