"""The cost ledger and hard budget cap (task X3).

Every call to a model is written to an append-only JSON Lines file twice: a
``reserve`` line with its worst-case cost, on disk before the call is sent, and
a ``charge`` line with its actual cost afterwards. A call counts at its charge,
or at its worst case while it has none, so a crash between the two never loses
spend. ``docs/ledger.md`` describes the file and the rules.

Use::

    with Ledger(batch_id="pilot-1", batch_cap_usd="20") as ledger:
        reservation = ledger.reserve(model_id=..., record_id=...,
                                     prompt_tokens=estimate_prompt_tokens(text),
                                     max_output_tokens=...)  # BudgetExceeded
        ...send the request...
        charge = ledger.settle(reservation, Usage(input=..., output=...),
                               request_id=...)

Run ``python -m runner.ledger [FILE]`` to print totals by batch and model.
"""

import decimal
import json
import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple

from runner.models import load_models
# The value tests and file handling are the record format's (T0.4).
from runner.record import (
    _UUID, LineProblem, RecordError, _is_count, _is_word, _timestamp_problem,
    append_line, parse_json, repair_tail, utc_now,
)

ROOT = Path(__file__).resolve().parents[1]
# Fixed to the checkout, not the working directory: starting a run from
# somewhere else must not start an empty ledger.
DEFAULT_PATH = ROOT / "data" / "ledger.jsonl"
SCHEMA_VERSION = 1
# Allowance for message framing and anything a provider adds to a prompt.
PROMPT_OVERHEAD_TOKENS = 1000
TYPES = ("reserve", "charge")
ENTRY_FIELDS = (
    "schema_version", "type", "call_id", "timestamp", "batch_id", "record_id",
    "request_id", "provider", "model_id", "tokens", "cost_usd", "estimated",
)
TOKEN_FIELDS = ("input", "output", "reasoning")
# A charge must repeat these from its reservation.
SHARED_FIELDS = ("batch_id", "record_id", "provider", "model_id")
_AMOUNT = re.compile(r"[0-9]+(\.[0-9]+)?")


class LedgerError(ValueError):
    """The ledger cannot do what was asked; no call may be sent."""


class BudgetExceeded(LedgerError):
    """The next call could take spending past a cap. The run must stop."""

    def __init__(self, scope, batch_id, cap_usd, spent_usd, worst_case_usd):
        self.scope = scope  # "batch" or "total"
        self.batch_id = batch_id
        self.cap_usd = cap_usd
        self.spent_usd = spent_usd  # includes open reservations
        self.worst_case_usd = worst_case_usd
        where = f"batch {batch_id!r}" if scope == "batch" else "total"
        super().__init__(
            f"{where} cap of ${_text(cap_usd)} would be passed: "
            f"${_text(spent_usd)} spent or reserved, and the next call could "
            f"cost ${_text(worst_case_usd)}")


@dataclass(frozen=True)
class Usage:
    """Token counts a provider reported; None for a count it did not report.

    ``input`` is the whole prompt, including any cached part. Reasoning tokens
    are charged at the output rate on top of ``output`` unless
    ``reasoning_in_output`` says the provider's output count already has them.
    """

    input: Optional[int] = None
    output: Optional[int] = None
    reasoning: Optional[int] = None
    reasoning_in_output: bool = False


@dataclass(frozen=True)
class Reservation:
    """Permission to send one call, holding its worst-case cost."""

    call_id: str
    batch_id: str
    record_id: str
    provider: str
    model_id: str
    prompt_tokens: int
    max_output_tokens: int
    worst_case_usd: Decimal


@dataclass(frozen=True)
class Charge:
    """What a settled call was charged."""

    call_id: str
    cost_usd: Decimal
    estimated: bool  # usage was unknown, so this is a worst case
    over_reservation: bool  # cost more than was reserved


@dataclass(frozen=True)
class LedgerRead:
    """What :func:`read_ledger` found; as ``runner.record.ReadResult``."""

    entries: list
    problems: Tuple[LineProblem, ...]
    truncated_tail: Optional[LineProblem]

    @property
    def ok(self):
        return not self.problems


@dataclass(frozen=True)
class Total:
    """Spending of one model in one batch."""

    batch_id: str
    model_id: str
    calls: int
    estimated_calls: int  # worst-case charges and open reservations
    input_tokens: int  # reported counts only
    output_tokens: int
    reasoning_tokens: int
    cost_usd: Decimal


# --- Money -----------------------------------------------------------------------


def _exact():
    """Decimal arithmetic that no caller's context settings can round."""
    return decimal.localcontext(decimal.Context(prec=60))


def _sum(amounts):
    with _exact():
        return sum(amounts, Decimal(0))


def _text(amount):
    """A Decimal as plain digits, without an exponent or trailing zeros."""
    with _exact():
        return format(amount.normalize(), "f")


def _cap(value, name):
    problem = LedgerError(
        f"{name}: a cap in US dollars of at least 0 is required, not {value!r}")
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise problem
    try:
        amount = Decimal(str(value))
    except decimal.InvalidOperation:
        raise problem from None
    if not amount.is_finite() or amount < 0:
        raise problem
    return amount


def call_cost(model, input_tokens, output_tokens):
    """The cost in US dollars of one call to ``model`` (a ``runner.models.Model``).

    ``output_tokens`` is everything billed at the output rate. A prompt above a
    price tier's threshold puts the whole call on that tier's rates. Cached,
    batch and off-peak discounts are ignored.
    """
    rates = model
    for tier in model.price_tiers:
        if input_tokens > tier.above_input_tokens:
            rates = tier
    prices = (rates.input_price_per_mtok_usd, rates.output_price_per_mtok_usd)
    if None in prices:
        raise LedgerError(f"model {model.id!r} has no price in the model list")
    with _exact():
        input_price, output_price = (Decimal(str(price)) for price in prices)
        return (input_tokens * input_price
                + output_tokens * output_price).scaleb(-6)


def estimate_prompt_tokens(*texts):
    """A high estimate of the prompt tokens for ``texts``: one per UTF-8 byte
    (a token covers at least one byte) plus ``PROMPT_OVERHEAD_TOKENS``. Pass
    every text sent. Not an estimate for images or other non-text input."""
    return sum(len(text.encode("utf-8")) for text in texts) + PROMPT_OVERHEAD_TOKENS


def _billed_output(output, reasoning, included):
    """Tokens charged at the output rate."""
    reasoning = reasoning or 0
    if included and reasoning <= output:
        return output
    return output + reasoning  # more reasoning than output: it is not included


# --- Reading ---------------------------------------------------------------------


def _entry_problems(entry):
    if not isinstance(entry, dict):
        return ["must be a JSON object"]
    if set(entry) != set(ENTRY_FIELDS):
        wrong = sorted(set(entry) ^ set(ENTRY_FIELDS))
        return ["missing or unknown fields: " + ", ".join(wrong)]
    tokens, amount = entry["tokens"], entry["cost_usd"]
    rules = {
        "schema_version": type(entry["schema_version"]) is int
        and entry["schema_version"] == SCHEMA_VERSION,
        "type": entry["type"] in TYPES,
        "timestamp": _timestamp_problem(entry["timestamp"]) is None,
        "request_id": entry["request_id"] is None or _is_word(entry["request_id"]),
        "tokens": isinstance(tokens, dict) and set(tokens) == set(TOKEN_FIELDS)
        and all(v is None or _is_count(v) for v in tokens.values()),
        "cost_usd": isinstance(amount, str) and bool(_AMOUNT.fullmatch(amount)),
        "estimated": type(entry["estimated"]) is bool,
        **{name: _is_word(entry[name]) for name in ("call_id",) + SHARED_FIELDS},
    }
    return [f"{name}: bad value" for name, ok in rules.items() if not ok]


def _sequence_problems(entry, calls):
    """Check ``entry`` against the earlier line for its call, if any."""
    earlier = calls.get(entry["call_id"])
    if entry["type"] == "reserve":
        return ["this call is already reserved"] if earlier else []
    if earlier is None:
        return ["charge without a reservation"]
    if earlier["type"] == "charge":
        return ["this call is already charged"]
    return [f"{name}: differs from the reservation"
            for name in SHARED_FIELDS if entry[name] != earlier[name]]


def read_ledger(path):
    """Read and check every line of a ledger file without changing it.

    Raises OSError if the file cannot be read.
    """
    lines = Path(path).read_bytes().split(b"\n")
    tail = lines.pop()  # empty when the file ends with a newline
    entries, problems, calls = [], [], {}
    for number, line in enumerate(lines, start=1):
        try:
            entry = parse_json(line)
            errors = _entry_problems(entry) or _sequence_problems(entry, calls)
        except RecordError as error:
            errors = list(error.errors)
        if errors:
            problems.append(LineProblem(number, tuple(errors)))
            continue
        calls[entry["call_id"]] = entry
        entries.append(entry)
    truncated = None
    if tail:
        truncated = LineProblem(len(lines) + 1,
                                ("unterminated last line (interrupted write?)",))
    return LedgerRead(entries, tuple(problems), truncated)


def _calls(entries):
    """The line that counts for each call: its charge, else its reservation."""
    return {entry["call_id"]: entry for entry in entries}


def totals(entries):
    """A :class:`Total` per (batch, model), sorted, from ledger entries."""
    groups = {}
    for entry in _calls(entries).values():
        groups.setdefault((entry["batch_id"], entry["model_id"]), []).append(entry)
    result = []
    for (batch_id, model_id), calls in sorted(groups.items()):
        reported = [c["tokens"] for c in calls if c["type"] == "charge"]
        counts = (sum(tokens[name] or 0 for tokens in reported)
                  for name in TOKEN_FIELDS)
        result.append(Total(
            batch_id, model_id, len(calls),
            sum(c["estimated"] for c in calls), *counts,
            _sum(Decimal(c["cost_usd"]) for c in calls)))
    return result


# --- One process at a time -------------------------------------------------------


def _lock(path):
    """Take an exclusive lock on the file at ``path``; return its descriptor.

    The operating system drops the lock when the process ends, however it ends,
    so a crash leaves nothing to clean up. The file itself stays.
    """
    handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(handle)
        raise LedgerError(
            f"{path.name}: the ledger is in use by another run") from error
    return handle


def _unlock(handle):
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(handle, 0, os.SEEK_SET)
            msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(handle)


# --- The ledger ------------------------------------------------------------------


class Ledger:
    """An open ledger file, with the caps that apply to one run.

    ``batch_cap_usd`` (required) limits the spending of ``batch_id`` over the
    whole file, including earlier runs of that batch. ``total_cap_usd``
    (optional) limits the spending of every batch in the file together. Caps are
    int, float, text or Decimal. ``models`` is a ``runner.models.ModelList``,
    read from ``models.yaml`` if not given.

    Threads may share one Ledger. A second Ledger on the same file, in this
    process or another, is refused until this one is closed. Do not use one
    across ``fork``.

    Raises :class:`LedgerError` if the file has bad lines, as spending would be
    unknown. An unterminated last line is cut; the bytes are kept in
    ``repaired_tail``.
    """

    def __init__(self, path=DEFAULT_PATH, *, batch_id, batch_cap_usd=None,
                 total_cap_usd=None, models=None):
        if not _is_word(batch_id):
            raise LedgerError("batch_id: must be text with no spaces, "
                              f"not {batch_id!r}")
        self.batch_id = batch_id
        self.batch_cap_usd = _cap(batch_cap_usd, "batch_cap_usd")
        self.total_cap_usd = (None if total_cap_usd is None
                              else _cap(total_cap_usd, "total_cap_usd"))
        self._models = (load_models(ROOT / "models.yaml") if models is None
                        else models)
        self.path = Path(path).resolve()
        self.repaired_tail = None
        self._mutex = threading.Lock()
        self._open = {}  # call_id -> Reservation made by this object
        self._broken = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = _lock(self.path.with_name(self.path.name + ".lock"))
        try:
            self._calls = self._load()  # call_id -> (batch_id, cost)
        except BaseException:
            self.close()
            raise

    def _load(self):
        if not self.path.exists():
            return {}
        found = read_ledger(self.path)
        if found.problems:
            listed = "; ".join(f"line {p.line}: {', '.join(p.errors)}"
                               for p in found.problems)
            raise LedgerError(f"{self.path.name}: spending is unknown, so no "
                              f"call is allowed. {listed}")
        if found.truncated_tail:
            # Either a reservation whose call was never sent, or a charge,
            # whose reservation then counts instead. (That is less than the
            # charge only if the call cost more than was reserved.)
            self.repaired_tail = repair_tail(self.path)
        return {call_id: (entry["batch_id"], Decimal(entry["cost_usd"]))
                for call_id, entry in _calls(found.entries).items()}

    def close(self):
        """Release the file. Unsettled calls stay charged at their worst case."""
        with self._mutex:
            if self._handle is not None:
                handle, self._handle = self._handle, None
                _unlock(handle)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # Spending. The underscored methods expect the mutex to be held.

    def _spent(self):
        return _sum(cost for batch, cost in self._calls.values()
                    if batch == self.batch_id)

    def _total_spent(self):
        return _sum(cost for _, cost in self._calls.values())

    def _caps(self):
        """(scope, cap, spent) for every cap that applies."""
        caps = [("batch", self.batch_cap_usd, self._spent())]
        if self.total_cap_usd is not None:
            caps.append(("total", self.total_cap_usd, self._total_spent()))
        return caps

    @property
    def spent_usd(self):
        """This batch's charges plus its open reservations."""
        with self._mutex:
            return self._spent()

    @property
    def total_spent_usd(self):
        """The same over every batch in the file."""
        with self._mutex:
            return self._total_spent()

    @property
    def remaining_usd(self):
        """The room left under the tightest cap; never below 0."""
        with self._mutex, _exact():
            return max(Decimal(0), min(cap - spent
                                       for _, cap, spent in self._caps()))

    # Calls.

    def _require_usable(self):
        if self._handle is None:
            raise LedgerError("the ledger is closed")
        if self._broken:
            raise LedgerError("a ledger write failed; close the ledger and "
                              "check the file before sending more calls")

    def _model(self, model_id):
        try:
            return self._models.get(model_id)
        except KeyError:
            raise LedgerError(f"unknown model {model_id!r}: it is not in the "
                              "model list") from None

    def _write(self, kind, call, tokens, cost, estimated, request_id=None):
        entry = {
            "schema_version": SCHEMA_VERSION,
            "type": kind,
            "call_id": call.call_id,
            "timestamp": utc_now(),
            "batch_id": call.batch_id,
            "record_id": call.record_id,
            "request_id": request_id,
            "provider": call.provider,
            "model_id": call.model_id,
            "tokens": dict(zip(TOKEN_FIELDS, tokens)),
            "cost_usd": _text(cost),
            "estimated": estimated,
        }
        try:
            append_line(self.path, json.dumps(
                entry, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
        except BaseException:
            self._broken = True
            raise
        self._calls[call.call_id] = (call.batch_id, cost)

    def reserve(self, *, model_id, record_id, prompt_tokens,
                max_output_tokens=None):
        """Allow one call, or raise; send nothing unless this returns.

        ``prompt_tokens`` is a high estimate (see
        :func:`estimate_prompt_tokens`). ``max_output_tokens`` is the output
        limit **sent in the request**, covering reasoning; leave it None when
        the request sends none, and the model's maximum is assumed. Raises
        :class:`BudgetExceeded` if spending plus this call's worst case is above
        a cap, otherwise writes the reservation to disk and returns it.
        """
        with self._mutex:
            self._require_usable()
            model = self._model(model_id)
            if max_output_tokens is None:
                max_output_tokens = model.defaults.max_output_tokens
            for name, value in (("prompt_tokens", prompt_tokens),
                                ("max_output_tokens", max_output_tokens)):
                if not (_is_count(value) and value > 0):
                    raise LedgerError(
                        f"{name}: must be a whole number above 0, not {value!r}")
            if not (isinstance(record_id, str) and _UUID.fullmatch(record_id)):
                raise LedgerError(
                    f"record_id: must be a lower-case UUID, not {record_id!r}")
            worst = call_cost(model, prompt_tokens, max_output_tokens)
            for scope, cap, spent in self._caps():
                if _sum((spent, worst)) > cap:
                    raise BudgetExceeded(scope, self.batch_id, cap, spent, worst)
            reservation = Reservation(
                str(uuid.uuid4()), self.batch_id, record_id, model.provider,
                model.id, prompt_tokens, max_output_tokens, worst)
            self._write("reserve", reservation,
                        (prompt_tokens, max_output_tokens, None), worst, True)
            self._open[reservation.call_id] = reservation
            return reservation

    def settle(self, reservation, usage, *, request_id=None):
        """Record what a reserved call cost and return the :class:`Charge`.

        Call it for every outcome, including failed, refused and truncated
        calls. Pass the :class:`Usage` the provider reported, or None if there
        is none: without both input and output counts the call is charged at its
        worst case (more if a reported count is above the estimate). If this
        raises, the reservation still counts.
        """
        if usage is None:
            usage = Usage()
        if not isinstance(usage, Usage):
            raise LedgerError("usage: must be a Usage or None")
        tokens = (usage.input, usage.output, usage.reasoning)
        if not all(count is None or _is_count(count) for count in tokens):
            raise LedgerError(
                f"usage: counts must be whole numbers of at least 0: {usage}")
        if type(usage.reasoning_in_output) is not bool:
            raise LedgerError("usage: reasoning_in_output must be True or False")
        if request_id is not None and not _is_word(request_id):
            raise LedgerError(
                f"request_id: must be text with no spaces, not {request_id!r}")
        with self._mutex:
            self._require_usable()
            if (not isinstance(reservation, Reservation)
                    or self._open.get(reservation.call_id) is not reservation):
                raise LedgerError("this reservation is not open in this ledger")
            estimated = usage.input is None or usage.output is None
            input_tokens = usage.input or 0
            output_tokens = _billed_output(
                usage.output or 0, usage.reasoning, usage.reasoning_in_output)
            if estimated:
                input_tokens = max(input_tokens, reservation.prompt_tokens)
                output_tokens = max(output_tokens, reservation.max_output_tokens)
            cost = call_cost(self._model(reservation.model_id),
                             input_tokens, output_tokens)
            self._write("charge", reservation, tokens, cost, estimated,
                        request_id)
            del self._open[reservation.call_id]
            return Charge(reservation.call_id, cost, estimated,
                          cost > reservation.worst_case_usd)


# --- Command line ----------------------------------------------------------------


def _table(rows):
    """Lines of the totals table, with a sum per batch and overall."""
    header = ("batch", "model", "calls", "estimated", "input", "output",
              "reasoning", "cost_usd")
    counted = ("calls", "estimated_calls", "input_tokens", "output_tokens",
               "reasoning_tokens")

    def cells(batch, model, group):
        counts = (str(sum(getattr(row, name) for row in group))
                  for name in counted)
        return (batch, model, *counts, _text(_sum(r.cost_usd for r in group)))

    table = [header]
    for batch in sorted({row.batch_id for row in rows}):
        group = [row for row in rows if row.batch_id == batch]
        table += [cells(batch, row.model_id, [row]) for row in group]
        table.append(cells(batch, "total", group))
    table.append(cells("all", "total", rows))
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    return ["  ".join(cell.ljust(width) for cell, width in zip(row, widths))
            .rstrip() for row in table]


def main(argv=None):
    """Print totals by batch and model; exit 1 if the file has bad lines."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1 or any(arg.startswith("-") for arg in args):
        print("usage: python -m runner.ledger [FILE.jsonl]")
        return 2
    path = Path(args[0]) if args else DEFAULT_PATH
    try:
        found = read_ledger(path)
    except OSError as error:
        print(f"{path}: cannot read: {error}")
        return 1
    for problem in found.problems:
        for message in problem.errors:
            print(f"{path}: line {problem.line}: {message}")
    if found.truncated_tail:
        print(f"{path}: line {found.truncated_tail.line}: "
              f"{found.truncated_tail.errors[0]} (ignored)")
    print("\n".join(_table(totals(found.entries))))
    if found.problems:
        print("The totals leave out the bad lines.")
    return 0 if found.ok else 1


if __name__ == "__main__":
    sys.exit(main())
