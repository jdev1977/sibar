# Cost ledger and budget cap

[runner/ledger.py](../runner/ledger.py) records what every model call costs and
refuses a call that could take spending past a cap.

```
python -m runner.ledger                 # totals by batch and model
python -m runner.ledger FILE.jsonl      # the same for another ledger file
```

The command only reads. It exits 1 if the file has bad lines or cannot be read.

## Use

```python
from runner.ledger import BudgetExceeded, Ledger, Usage, estimate_prompt_tokens

with Ledger(batch_id="pilot-1", batch_cap_usd="20", total_cap_usd="50") as ledger:
    reservation = ledger.reserve(          # raises BudgetExceeded: stop the run
        model_id=model_id, record_id=record_id,
        prompt_tokens=estimate_prompt_tokens(prompt_text),
        max_output_tokens=sent_limit)      # None if the request sends no limit
    usage, request_id = None, None
    try:
        ...                                # send the request; set both
    finally:
        charge = ledger.settle(reservation, usage, request_id=request_id)
```

A call whose result arrives after its run has ended, such as a request in a
provider's batch job, is settled by a later run of the same `batch_id`:
`ledger.reopen(call_id)` rebuilds the open reservation from its `reserve`
line, and `settle` is then called as usual. Until then it counts at its
worst case. `reopen` refuses a call that is unknown, already settled or of
another batch.

## The cap

Before each call, for each cap that applies:

    spent + worst case of the next call <= cap

- **spent** is every charge in scope plus the worst case of every call that has
  no charge yet.
- **Worst case** is the prompt estimate at the input rate plus the maximum
  output tokens at the output rate, on the price tier the estimate falls in.
- `batch_cap_usd` is required. It covers one `batch_id` across every run
  recorded in the file, so a restarted batch starts from what it already spent.
- `total_cap_usd` is optional and covers all batches in the file together.
- A cap equal to the amount needed allows the call. A cap of 0 allows none.
- Caps are not stored in the file. Each run states them, and a later run may
  state different ones; the spending it is compared with cannot be reset.

The cap holds as long as no call costs more than was reserved for it. That
needs, from the caller:

1. one reservation for **each request sent**, including retries (turn off a
   client library's automatic retries);
2. `max_output_tokens` equal to the limit sent in the request, or None when none
   is sent (the model's maximum from `models.yaml` is then assumed). It is taken
   to bound reasoning tokens too. Sending no limit is only valid where the
   `models.yaml` maximum truly bounds the request. It does not when a mode lets
   one request produce more than that maximum, such as Gemini long decode
   (`max_output_tokens` above 65,536, background execution or automatic
   continuation): send an explicit limit there and reserve that;
3. a prompt estimate that is not too low. `estimate_prompt_tokens` counts one
   token per UTF-8 byte plus 1000, for text only;
4. nothing billed beyond list-price tokens (see Prices).

If a call still costs more than its reservation, the full cost is recorded,
`Charge.over_reservation` is true, and later calls are checked against the
higher figure.

Reserving the model's maximum output is expensive: for Claude Opus 5.5 it is
$2.56 per call, so a cap must leave at least that much room.

## What a call is charged

| Settled with | Charged | `estimated` |
|---|---|---|
| input and output counts, whatever the call's outcome (ok, failed, refused, truncated) | the reported tokens | false |
| no usage, or input or output missing | the worst case, or more if a reported count is above it | true |
| nothing (crash, or `settle` never called or raised) | the worst case | true |

`Usage.reasoning` is charged at the output rate **in addition to** `output`.
Pass `reasoning_in_output=True` only when the provider's documentation says its
output count already includes reasoning; leaving it False can only over-charge.
(If reasoning exceeds output it is added regardless.) A missing reasoning count
means none. `Usage.input` is the whole prompt, including cached tokens.

A request that the provider rejected without reporting usage is also charged at
the worst case.

## Prices

From `models.yaml`: the base rates, and `price_tiers` for models that charge a
whole call at a higher rate above a prompt size (Claude Haiku 5.5, GPT-6.2 Sol,
GPT-6 Luna). When a prompt is above several thresholds, the tier with the
highest threshold applies, whatever the order of the list. DeepSeek's listed rates are its peak, cache-miss rates and are
always used. Cached-input and off-peak discounts are ignored, so those can only
make the real bill lower.

Not modelled, so the runner must not use them without adding them here: prompt
cache write surcharges, priority or regional processing, paid tools, and gateway
fees or prices that differ from the maker's. An unknown model or a missing price
is an error.

Money is computed in `Decimal` and stored as text.

## The file

`data/ledger.jsonl` in the repository root (gitignored), whatever directory the
run starts in. Another file path, another checkout or a deleted file is a
separate or empty ledger with its own spending: keep one file per budget.

It is append-only JSON Lines with two lines per call, joined by `call_id`:

- `reserve`, flushed to disk **before** the request is sent: the worst case,
  with the prompt estimate and output limit as `tokens`, `estimated` true;
- `charge`, after the call: the reported tokens and the cost.

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `type` | `reserve` or `charge` |
| `call_id` | UUID of the call |
| `timestamp` | UTC time the line was written |
| `batch_id`, `record_id` | The batch and the run record |
| `request_id` | The provider's id, or null |
| `provider`, `model_id` | From `models.yaml` |
| `tokens` | `input`, `output`, `reasoning`; null when not reported |
| `cost_usd` | Decimal as text, such as `"0.0019"` |
| `estimated` | True when the cost is a worst case |

An unterminated last line (an interrupted write) is cut when the ledger is
opened. Any other bad line makes the ledger refuse to open, because spending is
unknown; fix the file by hand and keep a copy. If a write fails, that `Ledger`
refuses all further calls.

## Concurrency

- Threads may share one `Ledger`; checking the cap and reserving happen as one
  step, so they cannot overshoot together.
- Only one `Ledger` may hold a file at a time. A second one, in the same or
  another process, is refused. The lock is an operating-system lock on
  `<file>.lock`; it ends with the process, so a crash needs no cleanup. Do not
  delete the lock file while a run is active.
- Do not share a `Ledger` across `fork`. Network file systems are not supported.
