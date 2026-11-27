# Generation runner

`python -m runner.run` sends each prompt to each model under test, once per
run, with **no system prompt and default settings**, and writes one
[run record](record-format.md) per attempt. Every attempt is reserved in the
[cost ledger](ledger.md) before it is sent, so a hard budget cap holds.

> **Status: not verified live.** The runner and its four provider adapters
> were written from each provider's documentation (read 2026-11-25) and tested
> only against a fake transport. No API keys existed (T0.3), so **no adapter
> has made a real call**. Run the [live check](#live-check-the-t05-done-when)
> before any larger run, and expect small fixes.

## Use

```
python -m runner.run --prompts PATH... --batch-id ID --dry-run
python -m runner.run --prompts PATH... --batch-id ID --paid --batch-cap USD --total-cap USD [--ledger PATH]
```

Commands in these docs are written `python -m ...`, one command per line, and
run from the repository root. On the Windows machine, in PowerShell, write
`.venv\Scripts\python` for `python` (the project's virtual environment, with
the pinned packages; or activate it first with `.venv\Scripts\Activate.ps1`).
Paths with forward slashes work as they are.

`--dry-run` lists every cell still to run with its worst-case cost, compares
the total with the caps and reports missing keys. It sends nothing and writes
nothing.

`--paid` spends money. It refuses to start unless:

- `models.yaml` has `confirmed_by_human: true`;
- both `--batch-cap` and `--total-cap` are given (US dollars);
- every chosen model's key is in the environment (see [Keys](#keys)).

It prints the ledger path (marked `(default)` when `--ledger` is not given)
and warns when the batch id is new to the ledger, since a new batch starts its
batch cap from $0.

| Option | Meaning |
|---|---|
| `--prompts PATH...` | Prompt files or folders, such as `prompts/website` (format: [prompts/README.md](../prompts/README.md)) |
| `--batch-id ID` | The batch, such as `pilot-1`: letters, digits, `.`, `_`, `-` |
| `--models` | `all` (default), `pilot`, or ids separated by commas |
| `--levels`, `--wordings` | Default `L0,L1,L2` and `A,B` |
| `--runs N` | Runs per prompt and model (default 1) |
| `--batch-cap`, `--total-cap` | Caps for this batch and for the whole ledger file |
| `--ledger PATH` | Default `data/ledger.jsonl` in the checkout |
| `--out PATH` | Record file; default `data/runs/<batch-id>/records.jsonl` |
| `--rerun refused,truncated` | Also run these statuses again (failed always runs again) |
| `--workers N` | Requests in flight at once (default 1) |
| `--max-attempts N` | Attempts per cell including the first (default 4) |
| `--max-consecutive-429 N` | Stop a provider after N HTTP 429 answers in a row (default 6) |
| `--rpm PROVIDER=N` | Requests per minute per provider (default 30 each) |
| `--read-timeout`, `--total-timeout` | Seconds: a silent response fails after 900, any response after 3600 |
| `--models-file PATH` | Another model list (tests use a copy) |

Exit status: 0 every cell finished (ok, refused or truncated); 1 some cells
failed or were skipped; 2 refused to start (nothing sent); 3 stopped at a
budget cap; 4 stopped for another reason (ledger failure, a call that cost
more than reserved, an internal error); 130 interrupted.

## Live check (the T0.5 done-when)

"One prompt runs against every listed model and saves a valid record for
each." Once the keys are set (T0.3) and `confirmed_by_human` is true:

```
python -m runner.run --prompts tests/fixtures/prompts/example/tiny-task.yaml --levels L0 --wordings A --runs 1 --models all --max-attempts 2 --batch-id t0.5-live-check --dry-run

python -m runner.run --prompts tests/fixtures/prompts/example/tiny-task.yaml --levels L0 --wordings A --runs 1 --models all --max-attempts 2 --batch-id t0.5-live-check --paid --batch-cap 15 --total-cap 15

python -m runner.record --files data/runs/t0.5-live-check/records.jsonl
python -m runner.ledger
```

The prompt asks for a short poem, so real costs are cents. The caps are set
by the worst case instead, because every attempt is reserved at its worst
case and an attempt without reported usage (an HTTP error, a timeout) stays
charged at it. The headroom a run can need is therefore **attempts per cell ×
worst case per cell**, summed over the cells: one attempt of each of the eight
models is $6.66 at worst (Claude Opus 5.5 alone $2.56), so with
`--max-attempts 2` the caps need $13.32; $15 leaves a little over.

The check passes when the last two commands show eight valid records, all
`ok`, and one charge per request. If a provider fails, its record says why;
fix the adapter and run the same command again: done cells are skipped. A
retry spends the same headroom again, and worst-case charges (overstated
when the provider would not actually bill a failed request) stay in the
ledger for good: after a few failed attempts, raise the batch cap or start a
new batch id, and keep the total cap as the overall limit.

## The pilot (T1.7)

540 generations: the six website prompts, three levels, two wordings, five
runs, on the three pilot models of models.yaml (`pilot:`). **`--models`
defaults to `all` (every model in models.yaml), so the pilot must say
`--models pilot`.** Dry-run first, read the cell count (540) and the worst
case, and choose the caps from it (the Human approves the spend):

```
python -m runner.run --prompts prompts/website --models pilot --runs 5 --batch-id pilot-1 --dry-run

python -m runner.run --prompts prompts/website --models pilot --runs 5 --batch-id pilot-1 --paid --batch-cap USD --total-cap USD
```

Levels and wordings default to all (`L0,L1,L2`, `A,B`). Re-running the same
command resumes: done cells are skipped (see [Resuming](#resuming)). Then
`python -m extractors --records data/runs/pilot-1/records.jsonl` and
[analysis/README.md](../analysis/README.md).

## What is sent

One user message holding the prompt text, exactly as loaded. Nothing else that
changes generation: no system prompt, no temperature or other sampling
parameter, no reasoning or thinking setting. Every adapter streams. OpenAI and
Google are also told `store: false`, so they do not keep the response for later
retrieval; their abuse-monitoring logs are kept all the same
([docs/terms](terms/README.md)).

| Provider | Endpoint | Body | Recorded `settings` | Output limit |
|---|---|---|---|---|
| Anthropic | `POST https://api.anthropic.com/v1/messages` | `model`, `max_tokens`, `messages`, `stream` | `max_tokens`, `stream`, `anthropic-version` | `max_tokens` is required: the model's maximum from models.yaml (128000) |
| OpenAI | `POST https://api.openai.com/v1/responses` | `model`, `input`, `stream`, `store` (false) | `stream`, `store` | none sent; bounded by the model's 128,000 maximum |
| Google | `POST https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse` | `model`, `input`, `stream`, `store` (false) | `stream`, `store`, `alt`, `api-revision` | none sent; Gemini 4 then stops at 65,536 (thinking and output) |
| DeepSeek | `POST https://api.deepseek.com/chat/completions` | `model`, `messages`, `stream` | `stream` | none sent; the documented default is "64K" in thinking mode |

`settings` holds the body parameters sent (besides the model and prompt) plus
the header that pins the API version, so a record can be sent again exactly.
It also holds what the response reports about how it was served, as
`reported_<field>`: Anthropic `reported_service_tier`, `reported_speed` and
`reported_inference_geo`; OpenAI and Google `reported_service_tier`. DeepSeek
documents none.

**Each provider account or project must be on the default (standard) tier.**
Priority, flex, scale, fast and regional serving are priced differently from
the list rates in models.yaml, which the ledger uses. If a response reports
anything but Anthropic `standard`/`standard`/`global`, OpenAI `default` (or
`auto`) or Google `standard`, the record is kept, its cost is charged at the
worst case (record `cost_usd` null), and that provider is stopped for the run.

Why streaming: Anthropic says not to send a large `max_tokens` without it;
Google cuts a non-streamed request at 10 minutes and a streamed one at 20;
for OpenAI and DeepSeek it is a choice, to keep long reasoning responses alive
on the connection.

Headers: Anthropic `Authorization: Bearer`, `anthropic-version: 2026-10-21`
(and `anthropic-workspace-id` if `ANTHROPIC_WORKSPACE_ID` is set); OpenAI and
DeepSeek `Authorization: Bearer`; Google `x-goog-api-key` and
`Api-Revision: 2026-05-20`.

Each adapter module (`runner/providers/*.py`) cites the pages it follows and
lists what it could not verify.

**Why no provider SDKs and no HTTP library.** Each provider needs one POST and
a line-by-line read of a streamed body, which the standard library
(`http.client` over `ssl`, in `runner/transport.py`) does in under two hundred
lines. SDKs would add four dependency trees, each with its own automatic
retries (which must be off, since the ledger reserves every attempt) and its
own view of timeouts; and the runner needs to know whether a failure came
before the request left the machine (nothing billed) or after (maybe billed),
which `http.client` shows directly because connecting is a separate step.
The cost is following API changes by hand; the adapters cite the pages to
recheck.

## What is recorded

| Record field | Anthropic | OpenAI | Google | DeepSeek |
|---|---|---|---|---|
| `raw_response` | text blocks | `output_text` parts of message items | text of `model_output` steps | `content` deltas |
| `stop_reason` | `stop_reason` | incomplete reason, else `status` | interaction `status` | `finish_reason` |
| `model_id_returned` | `message.model` | `response.model` | `interaction.model` | chunk `model` |
| `request_id` | `request-id` header (else message id) | `x-request-id` header (else response id) | interaction id | `x-request-id` header if any, else completion id |

Text from separate blocks is joined with a blank line (so a code fence that
ends one block still closes); text inside a block is never changed. Reasoning
or thinking text is not stored. The only other change to model output: an
exact key in use, if it ever appeared, would be replaced (see [Keys](#keys)).

**Status.** `ok`: finished normally with text. `truncated`: stopped by a
length limit (Anthropic `max_tokens` or `model_context_window_exceeded`;
OpenAI incomplete `max_output_tokens`; Google `incomplete` or
`requires_continuation`; DeepSeek `length`). `refused`: the model or a filter
declined (Anthropic `refusal`; an OpenAI refusal part, `content_filter` or a
policy failure; a Google blocked code; DeepSeek `content_filter`). `failed`:
anything else, including a finished response with no text. A failed record
holds the error text.

**Tokens.** All counts are normalised:

- `input`: the whole prompt, cached parts included;
- `output`: every generated token billed at the output rate, **reasoning
  included**;
- `reasoning`: the reasoning part of `output`, or null if not reported.

| Provider | input | Does the provider's output count include reasoning? | reasoning |
|---|---|---|---|
| Anthropic | `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` | Yes (`output_tokens` is "the inclusive, authoritative total") | `output_tokens_details.thinking_tokens` |
| OpenAI | `input_tokens` | Yes (documented example: total = input + output) | `output_tokens_details.reasoning_tokens` |
| Google | `total_input_tokens` (+ tool-use tokens) | **No**: `output = total_output_tokens + total_thought_tokens` | `total_thought_tokens` |
| DeepSeek | `prompt_tokens` | Yes (`completion_tokens_details` is a breakdown of the completion; billing is input plus output) | `completion_tokens_details.reasoning_tokens` |

Where a provider also reports a total (OpenAI `total_tokens`, Google
`total_tokens`, DeepSeek `total_tokens`), `output` is billed as at least the
total minus the input (and Google's tool-use tokens), so tokens a provider
counts without breaking them down are still charged. Anthropic reports no
total.

**Files.** Fenced code blocks and complete HTML documents outside fences are
saved under `files/<record_id>/extracted/` beside the record file, with
`sha256` and `size` in the record (`runner/files.py`). A block is named from a
file name in its info string or on the line before it, else `block-NN.<ext>`;
unfenced HTML is `document-NN.html`. Names from the model are made safe: no
`..`, drive or root, a whitelist of characters, Windows reserved names
defused, trailing dots and spaces removed, limited depth and length, unique
ignoring case; files are created exclusively and must land inside the folder.
A name is also replaced by the generic one when the whole path, folder
included, would pass 240 characters (Windows without long-path support
refuses 260). Unclosed blocks are not extracted. Failed records get no files.

Saving files can never lose a response: if writing fails for any reason, the
partly written `files/<record_id>/` folder is removed, a warning is printed,
and the record is written with an empty `files` list and the whole response
in `raw_response`, from which extraction can be redone.

## Retries and rate limits

Retried, with exponential backoff and jitter (2 s doubling to 60 s, waiting
between half and all of that) and never sooner than a `Retry-After` header
asks: HTTP 408, 409, 429, 5xx (including Anthropic 529), connection failures,
timeouts, streams that stop early, and server errors inside a stream. A
`Retry-After` above 600 s is not waited for. Anthropic's `x-should-retry`
header is followed.

Not retried: other 4xx (authentication, validation, billing), spend-limit and
quota errors (Anthropic `enforced_spend_limit_reached`, OpenAI
`insufficient_quota` and the spend-limit codes, Google `quota_exceeded`),
refusals, truncations, unreadable responses, and a response cut by the total
time limit while it was already streaming (sending it again would likely run
as long; it is still charged at the worst case).

Errors that would repeat stop further calls for the rest of the run, so they
cannot spend the budget cell after cell: 401, 402, 403 and spend or quota
errors stop **that provider**, and so do `--max-consecutive-429` HTTP 429
answers in a row from it, across cells (default 6, since a daily quota or
billing limit can answer every request with a retryable-looking 429, each
charged at the worst case); a non-standard service tier stops it too (see
[What is sent](#what-is-sent)). 400, 404, 413, 422, an unreadable response,
a response that is not an event stream, an unexpected stop reason, a total
timeout or an unexpected error in the transport stop **that model**. Every
attempt still gets its record. Other models carry on, and skipped cells run
on the next invocation.

Each provider gets an even spacing of `60 / rpm` seconds between request
starts, shared by all workers (default 30 per minute). Providers also limit
tokens per minute and concurrency; their 429 answers are retried.

## Money

Every attempt, retries included, is reserved in the ledger immediately
before it is sent and settled immediately after, whatever the outcome:

| Outcome | Charged |
|---|---|
| The provider reported input and output tokens | Those tokens, at list price |
| The connection could not be opened (no byte of the request was sent) | $0 |
| A non-standard service tier was reported | The worst case (premium prices are not modelled) |
| Anything else: timeout or drop after sending, HTTP error without usage, unreadable response, crash | The worst case: prompt estimate plus the output limit at the output rate |

The worst case uses the limit sent (Anthropic) or the model's maximum from
models.yaml (the others); see the table above for why that bounds each
request. A run never sends `background`, a long-decode limit or anything else
that lifts that bound. An HTTP error is charged at the worst case because the
providers do not document that a rejected request is free (X3 rule): a run
with many errors stops at its cap early and the ledger overstates spend.

The run stops cleanly, recording calls already in flight, when a reservation
would pass a cap (`BudgetExceeded`), when the ledger cannot be written, or
when a call cost more than was reserved (an assumption behind the cap failed).
Record `cost_usd` is the charge when it came from reported tokens, and null
when the ledger charged the worst case.

## Resuming

A record's cell is (batch, project type, task, prompt-set version, level,
wording, model, surface, run index). On start, a paid run:

1. locks the record file and the ledger (a second run on either is refused);
2. removes an unfinished last record line left by a crash (the ledger does the
   same for its own file);
3. treats a cell as done when it has a record whose status is not to be run
   again. By default only **failed** cells run again; refused and truncated
   cells count as done unless `--rerun refused,truncated` is given;
4. refuses if a record for a planned cell holds different prompt text under
   the same prompt-set version: raise `prompt_set_version` after editing a
   prompt.

A crash between reserving and settling leaves the call counted at its worst
case; a crash after settling but before the record is written means the cell
runs again (and is paid again). Files written for a record that was never
saved stay in `files/` and can be deleted.

Ctrl-C once: calls in flight finish and are recorded, then the run stops.
Twice: the run exits at once and calls in flight count at their worst case.

## Keys

Keys are read from the environment variables named in models.yaml
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`).
The runner does not read a `.env` file: set the variables in the shell that
runs it ([docs/secrets.md](secrets.md#setting-keys-in-powershell) shows how
in PowerShell).
A paid run refuses to start, naming the variables, if a chosen model's key is
missing or contains spaces or line breaks (values are never shown). Choose
models with `--models` to run without some providers.

Keys go only into request headers, never into URLs, bodies, records, files,
the ledger or messages. Console output and error text pass through a scrubber
that replaces the keys in use and anything shaped like a known key or bearer
token with `[redacted]`. Model output (`raw_response` and extracted files)
gets only the exact keys in use replaced, so a model's own key-shaped
placeholders (`sk-...` in example code) stay as written. A request object
never shows its headers, and an invalid header value never appears in an
error.

`ANTHROPIC_WORKSPACE_ID` (optional, not secret) is sent as
`anthropic-workspace-id`, which Anthropic requires for keys not scoped to one
workspace.

## Output

```
data/ledger.jsonl                                  cost ledger (all batches)
data/runs/<batch-id>/records.jsonl                 one record per attempt
data/runs/<batch-id>/files/<record_id>/extracted/  files from each response
```

`data/` is gitignored.

## How T0.6 reads measured tokens

The records hold the measured counts; failed attempts are records too.

```python
from runner.record import read_records

records = read_records("data/runs/t0.5-live-check/records.jsonl").records
for r in records:
    if r["status"] != "failed":
        print(r["model_id"], r["tokens"]["input"], r["tokens"]["output"],
              r["tokens"]["reasoning"], r["cost_usd"])
```

`tokens.output` already includes reasoning for every provider, so a cost
estimate is `input × input price + output × output price` (models.yaml). Per
batch and model totals, including worst-case charges for unknown costs, come
from `python -m runner.ledger`. The live check measures one short prompt; the
pilot estimate should scale by prompt length and expected output size.

## Not verified

- Every adapter against the live API (no keys yet).
- Anthropic: that 128000 is accepted as `max_tokens` for both Claude models;
  whether the account's key needs `anthropic-workspace-id`.
- OpenAI: the output bound when `max_output_tokens` is omitted (models.yaml's
  128000 is assumed); cache-write surcharges are not modelled.
- Google: that Gemini 3.5 Flash-Lite stops at 65,536 when no limit is sent
  (its model page gives that limit; the long-decode page covers Gemini 4); the
  request id (no header is documented).
- DeepSeek: the exact default output limit; whether errors can arrive inside
  a stream; any request id header.
- Billing of HTTP error responses (charged at worst case, see Money; kept by
  ruling in review).
- The serving values a default account reports (assumed: Anthropic
  `standard`, `standard`, `global`; OpenAI `default`; Google `standard`). If a
  default account reports something else, the first call stops that provider
  and the value is in the record's settings.
- Default read and total timeouts (900 s, 3600 s) against real long
  generations; default rate limits (30 per minute) against each account's
  real limits.
- On Windows, a blocking socket read is not interrupted by Ctrl-C; the main
  thread still reacts, but the call in flight finishes first.
