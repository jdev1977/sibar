"""The cost ledger and hard budget cap (task X3). No network, no keys."""

import decimal
import json
import subprocess
import sys
import threading
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from runner import ledger as ledger_module
from runner.ledger import (
    DEFAULT_PATH, BudgetExceeded, Ledger, LedgerError, Usage, call_cost,
    estimate_prompt_tokens, main, read_ledger, totals,
)
from runner.models import Defaults, Model, ModelList, PriceTier, load_models

ROOT = Path(__file__).resolve().parents[1]


def fake_model(model_id, input_price=1.0, output_price=10.0, max_output=1000,
               tiers=()):
    return Model(
        id=model_id, provider="example", tier="main", display_name=model_id,
        input_price_per_mtok_usd=input_price,
        output_price_per_mtok_usd=output_price,
        defaults=Defaults(None, None, None, max_output, None, None),
        retirement_date=None, retirement_not_before=None,
        api_key_env="EXAMPLE_API_KEY", sources=(), date_checked=None,
        notes={}, price_tiers=tiers,
    )


MODELS = ModelList(1, False, (), (
    fake_model("m"),
    fake_model("cheap", 0.1, 0.1),
    fake_model("tiered", tiers=(PriceTier(1000, 2.0, 20.0),
                                PriceTier(5000, 3.0, 30.0))),
    fake_model("no-input-price", input_price=None),
    fake_model("no-output-price", output_price=None),
    fake_model("no-max", max_output=None),
))

# Model "m" with 1000 prompt tokens and 1000 output tokens at most:
# 1000 * $1/M + 1000 * $10/M.
WORST = Decimal("0.011")


def open_ledger(tmp_path, cap="1", batch="b1", **kwargs):
    return Ledger(tmp_path / "ledger.jsonl", batch_id=batch,
                  batch_cap_usd=cap, models=MODELS, **kwargs)


def reserve(ledger, model="m", prompt=1000, max_output=1000, record_id=None):
    return ledger.reserve(model_id=model, record_id=record_id or str(uuid.uuid4()),
                          prompt_tokens=prompt, max_output_tokens=max_output)


def lines(tmp_path):
    text = (tmp_path / "ledger.jsonl").read_text(encoding="ascii")
    return [json.loads(line) for line in text.splitlines()]


# The done-when.

def fake_run(ledger, calls):
    """A stand-in for the runner: stops at the first refused call."""
    sent = 0
    for _ in range(calls):
        try:
            reservation = reserve(ledger)
        except BudgetExceeded as refusal:
            return sent, refusal
        sent += 1  # the "provider call" happens here
        ledger.settle(reservation, Usage(input=1000, output=500))
    return sent, None


def test_a_run_stops_at_a_deliberately_low_cap(tmp_path):
    # Each call costs 0.006 and needs 0.011 free: calls fit while
    # spent + 0.011 <= 0.025, that is after 0, 1 and 2 calls.
    with open_ledger(tmp_path, cap="0.025") as ledger:
        sent, refusal = fake_run(ledger, 100)

        assert sent == 3
        assert ledger.spent_usd == Decimal("0.018")
    assert refusal.scope == "batch"
    assert refusal.cap_usd == Decimal("0.025")
    assert refusal.spent_usd == Decimal("0.018")
    assert refusal.worst_case_usd == WORST
    assert "cap" in str(refusal)
    assert len(lines(tmp_path)) == 6  # nothing written for the refused call


def test_a_restarted_run_cannot_reset_the_cap(tmp_path):
    with open_ledger(tmp_path, cap="0.025") as ledger:
        fake_run(ledger, 100)
    with open_ledger(tmp_path, cap="0.025") as ledger:
        assert ledger.spent_usd == Decimal("0.018")
        sent, refusal = fake_run(ledger, 100)

    assert sent == 0
    assert refusal is not None


# Lines written.

def test_each_call_writes_a_reservation_then_a_charge(tmp_path):
    record_id = str(uuid.uuid4())
    with open_ledger(tmp_path) as ledger:
        reservation = reserve(ledger, record_id=record_id)
        before = lines(tmp_path)
        charge = ledger.settle(reservation, Usage(input=900, output=100),
                               request_id="req_1")
    held, charged = lines(tmp_path)

    assert before == [held]  # on disk before the call is sent
    assert held["type"] == "reserve"
    assert held["cost_usd"] == "0.011"
    assert held["estimated"] is True
    assert held["tokens"] == {"input": 1000, "output": 1000, "reasoning": None}
    assert held["request_id"] is None
    assert charged["type"] == "charge"
    assert charged["call_id"] == held["call_id"] == reservation.call_id
    assert charged["record_id"] == record_id
    assert charged["batch_id"] == "b1"
    assert charged["request_id"] == "req_1"
    assert charged["provider"] == "example"
    assert charged["model_id"] == "m"
    assert charged["tokens"] == {"input": 900, "output": 100, "reasoning": None}
    assert charged["cost_usd"] == "0.0019"
    assert charged["estimated"] is False
    assert charged["timestamp"].endswith("Z")
    assert charge.cost_usd == Decimal("0.0019")
    assert charge.estimated is False
    assert charge.over_reservation is False


def test_the_ledger_directory_is_created(tmp_path):
    path = tmp_path / "new" / "dir" / "ledger.jsonl"
    with Ledger(path, batch_id="b", batch_cap_usd=1, models=MODELS) as ledger:
        reserve(ledger)

    assert path.is_file()


def test_the_default_path_is_under_data_in_the_repository():
    assert DEFAULT_PATH == ROOT / "data" / "ledger.jsonl"


# The cap.

def test_a_call_that_exactly_fills_the_cap_is_allowed(tmp_path):
    with open_ledger(tmp_path, cap=WORST) as ledger:
        reserve(ledger)
        assert ledger.remaining_usd == 0
        with pytest.raises(BudgetExceeded):
            reserve(ledger, model="cheap", prompt=1, max_output=1)


def test_a_cap_below_the_first_call_refuses_it_and_writes_nothing(tmp_path):
    with open_ledger(tmp_path, cap="0.010999") as ledger:
        with pytest.raises(BudgetExceeded):
            reserve(ledger)
        assert ledger.spent_usd == 0
    assert not (tmp_path / "ledger.jsonl").exists()


def test_open_reservations_count_against_the_cap(tmp_path):
    with open_ledger(tmp_path, cap="0.02") as ledger:
        reserve(ledger)
        with pytest.raises(BudgetExceeded):
            reserve(ledger)


def test_settling_frees_the_unused_part_of_a_reservation(tmp_path):
    with open_ledger(tmp_path, cap="0.015") as ledger:
        ledger.settle(reserve(ledger), Usage(input=1000, output=0))

        assert ledger.spent_usd == Decimal("0.001")
        assert ledger.remaining_usd == Decimal("0.014")
        reserve(ledger)


@pytest.mark.parametrize("cap", [None, "", "lots", -1, "-0.01", float("nan"),
                                 float("inf"), "NaN", "Infinity", True])
def test_a_missing_or_bad_batch_cap_is_an_error(tmp_path, cap):
    with pytest.raises(LedgerError, match="cap"):
        open_ledger(tmp_path, cap=cap)


def test_leaving_out_the_batch_cap_is_an_error(tmp_path):
    with pytest.raises(LedgerError, match="cap"):
        Ledger(tmp_path / "ledger.jsonl", batch_id="b", models=MODELS)


@pytest.mark.parametrize("cap", ["lots", -1, float("inf"), False])
def test_a_bad_total_cap_is_an_error(tmp_path, cap):
    with pytest.raises(LedgerError, match="cap"):
        open_ledger(tmp_path, total_cap_usd=cap)


@pytest.mark.parametrize("cap", [1, 0.011, "0.011", Decimal("0.011")])
def test_caps_may_be_numbers_or_text(tmp_path, cap):
    with open_ledger(tmp_path, cap=cap) as ledger:
        reserve(ledger)


@pytest.mark.parametrize("batch", [None, "", "two words", 3])
def test_a_bad_batch_id_is_an_error(tmp_path, batch):
    with pytest.raises(LedgerError, match="batch_id"):
        open_ledger(tmp_path, batch=batch)


def test_a_batch_cap_covers_only_its_batch(tmp_path):
    with open_ledger(tmp_path, cap=WORST, batch="b1") as ledger:
        reserve(ledger)
    with open_ledger(tmp_path, cap=WORST, batch="b2") as ledger:
        assert ledger.spent_usd == 0
        assert ledger.total_spent_usd == WORST
        reserve(ledger)


def test_a_total_cap_covers_all_batches(tmp_path):
    with open_ledger(tmp_path, batch="b1") as ledger:
        reserve(ledger)
    with open_ledger(tmp_path, batch="b2", total_cap_usd="0.02") as ledger:
        assert ledger.remaining_usd == Decimal("0.009")
        with pytest.raises(BudgetExceeded) as caught:
            reserve(ledger)

    assert caught.value.scope == "total"
    assert caught.value.spent_usd == WORST
    assert caught.value.cap_usd == Decimal("0.02")


def test_threads_cannot_overshoot_the_cap(tmp_path):
    allowed, refused = [], []
    with open_ledger(tmp_path, cap=WORST * 5) as ledger:
        start = threading.Barrier(20)

        def worker():
            start.wait()
            try:
                allowed.append(reserve(ledger))
            except BudgetExceeded:
                refused.append(1)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        settlers = [threading.Thread(target=ledger.settle,
                                     args=(r, Usage(input=1000, output=1000)))
                    for r in allowed]
        for thread in settlers:
            thread.start()
        for thread in settlers:
            thread.join()

        assert (len(allowed), len(refused)) == (5, 15)
        assert ledger.spent_usd == WORST * 5
    result = read_ledger(tmp_path / "ledger.jsonl")
    assert result.ok
    assert len(result.entries) == 10


# Money.

def test_money_does_not_drift(tmp_path):
    with open_ledger(tmp_path) as ledger:
        for _ in range(100):
            ledger.settle(reserve(ledger, model="cheap", prompt=1, max_output=1),
                          Usage(input=1, output=0))
        assert ledger.spent_usd == Decimal("0.00001")
    assert lines(tmp_path)[1]["cost_usd"] == "0.0000001"  # no exponent form
    with open_ledger(tmp_path) as ledger:
        assert ledger.spent_usd == Decimal("0.00001")


def test_a_coarse_decimal_context_cannot_round_money(tmp_path):
    with decimal.localcontext(decimal.Context(prec=2)):
        with open_ledger(tmp_path, cap="0.022001") as ledger:
            reserve(ledger)
            reserve(ledger)
            assert ledger.spent_usd == Decimal("0.022")
            assert ledger.remaining_usd == Decimal("0.000001")
            with pytest.raises(BudgetExceeded):
                reserve(ledger, model="cheap", prompt=6, max_output=5)
        assert call_cost(MODELS.get("m"), 1001, 1000) == Decimal("0.011001")


@pytest.mark.parametrize("prompt,expected", [
    (1000, "0.011"),     # at the threshold: base rate
    (1001, "0.022002"),  # over it: the whole call at the higher rate
    (5000, "0.03"),
    (5001, "0.045003"),
])
def test_price_tiers_apply_to_the_whole_call(prompt, expected):
    assert call_cost(MODELS.get("tiered"), prompt, 1000) == Decimal(expected)


def test_the_tier_of_the_actual_prompt_is_charged(tmp_path):
    with open_ledger(tmp_path) as ledger:
        reservation = reserve(ledger, model="tiered", prompt=900)
        charge = ledger.settle(reservation, Usage(input=1001, output=0))

    assert charge.cost_usd == Decimal("0.002002")


@pytest.mark.parametrize("model_id,threshold,at_cost,over_cost", [
    # 100000 * 0.10 + 100000 * 0.50; 100001 * 0.50 + 100000 * 2.50
    ("claude-haiku-5-5", 100000, "0.06", "0.3000005"),
    # 272000 * 2 + 100000 * 10; 272001 * 4 + 100000 * 15
    ("gpt-6.2-sol", 272000, "1.544", "2.588004"),
    # 272000 * 0.10 + 100000 * 0.50; 272001 * 0.20 + 100000 * 0.75
    ("gpt-6-luna", 272000, "0.0772", "0.1294002"),
])
def test_committed_models_use_their_long_prompt_rates(
        model_id, threshold, at_cost, over_cost):
    model = load_models(ROOT / "models.yaml").get(model_id)

    assert call_cost(model, threshold, 100000) == Decimal(at_cost)
    assert call_cost(model, threshold + 1, 100000) == Decimal(over_cost)


def test_every_committed_model_can_be_priced():
    for model in load_models(ROOT / "models.yaml").models:
        assert call_cost(model, 1000, 1000) > 0


def test_the_committed_list_is_used_by_default(tmp_path):
    with Ledger(tmp_path / "l.jsonl", batch_id="b", batch_cap_usd=10) as ledger:
        reservation = ledger.reserve(
            model_id="claude-opus-5-5", record_id=str(uuid.uuid4()),
            prompt_tokens=1000)

    # no limit given: the model's maximum output, 128000 * $20/M, plus input
    assert reservation.max_output_tokens == 128000
    assert reservation.worst_case_usd == Decimal("2.564")


@pytest.mark.parametrize("model_id,match", [
    ("nope", "unknown model"),
    ("no-input-price", "price"),
    ("no-output-price", "price"),
])
def test_an_unknown_model_or_missing_price_is_an_error(tmp_path, model_id, match):
    with open_ledger(tmp_path) as ledger:
        with pytest.raises(LedgerError, match=match):
            reserve(ledger, model=model_id)
        assert ledger.spent_usd == 0


def test_no_output_limit_and_no_known_maximum_is_an_error(tmp_path):
    with open_ledger(tmp_path) as ledger:
        with pytest.raises(LedgerError, match="max_output_tokens"):
            reserve(ledger, model="no-max", max_output=None)
        reserve(ledger, model="no-max", max_output=10)


@pytest.mark.parametrize("key,value", [
    ("prompt_tokens", None), ("prompt_tokens", 0), ("prompt_tokens", 1.5),
    ("prompt_tokens", True), ("max_output_tokens", 0),
    ("max_output_tokens", -5), ("max_output_tokens", "100"),
    ("record_id", None), ("record_id", "r1"),
])
def test_bad_reserve_arguments_are_errors(tmp_path, key, value):
    arguments = {"model_id": "m", "record_id": str(uuid.uuid4()),
                 "prompt_tokens": 10, "max_output_tokens": 10, key: value}
    with open_ledger(tmp_path) as ledger:
        with pytest.raises(LedgerError, match=key):
            ledger.reserve(**arguments)
        assert ledger.spent_usd == 0


def test_the_prompt_estimate_is_at_least_one_token_per_byte():
    assert estimate_prompt_tokens("") == ledger_module.PROMPT_OVERHEAD_TOKENS
    assert (estimate_prompt_tokens("abcd", "é")
            == 6 + ledger_module.PROMPT_OVERHEAD_TOKENS)


# Usage: known, unknown, partial, reasoning.

def test_reasoning_is_added_to_output_unless_said_to_be_included(tmp_path):
    with open_ledger(tmp_path) as ledger:
        added = ledger.settle(reserve(ledger),
                              Usage(input=0, output=100, reasoning=50))
        included = ledger.settle(
            reserve(ledger),
            Usage(input=0, output=100, reasoning=50, reasoning_in_output=True))

    assert added.cost_usd == Decimal("0.0015")
    assert included.cost_usd == Decimal("0.001")


def test_included_reasoning_larger_than_output_is_added(tmp_path):
    with open_ledger(tmp_path) as ledger:
        charge = ledger.settle(
            reserve(ledger),
            Usage(input=0, output=10, reasoning=50, reasoning_in_output=True))

    assert charge.cost_usd == Decimal("0.0006")


@pytest.mark.parametrize("usage", [
    None, Usage(), Usage(input=10), Usage(output=10), Usage(reasoning=10),
])
def test_unknown_usage_is_charged_at_the_worst_case(tmp_path, usage):
    with open_ledger(tmp_path) as ledger:
        charge = ledger.settle(reserve(ledger), usage)

        assert charge.cost_usd == WORST
        assert charge.estimated is True
        assert ledger.spent_usd == WORST
    assert lines(tmp_path)[-1]["estimated"] is True


@pytest.mark.parametrize("usage,expected", [
    # known counts above the estimate raise the worst case
    (Usage(input=3000), "0.013"),
    (Usage(output=2000), "0.021"),
    (Usage(output=900, reasoning=900), "0.019"),
])
def test_partial_usage_above_the_estimate_is_not_ignored(tmp_path, usage, expected):
    with open_ledger(tmp_path) as ledger:
        charge = ledger.settle(reserve(ledger), usage)

    assert charge.cost_usd == Decimal(expected)
    assert charge.estimated is True


def test_a_cost_above_the_reservation_is_recorded_and_blocks_later_calls(tmp_path):
    with open_ledger(tmp_path, cap="0.012") as ledger:
        charge = ledger.settle(reserve(ledger), Usage(input=1000, output=5000))

        assert charge.over_reservation is True
        assert ledger.spent_usd == Decimal("0.051")
        assert ledger.remaining_usd == 0
        with pytest.raises(BudgetExceeded):
            reserve(ledger, model="cheap", prompt=1, max_output=1)


@pytest.mark.parametrize("usage,request_id", [
    (Usage(input=-1, output=1), None),
    (Usage(input=1.5, output=1), None),
    (Usage(input=1, output="2"), None),
    (Usage(input=1, output=1, reasoning=True), None),
    (Usage(input=1, output=1, reasoning_in_output="yes"), None),
    ({"input": 1, "output": 1}, None),
    (Usage(input=1, output=1), "has space"),
])
def test_a_bad_settlement_is_refused_and_the_reservation_stands(
        tmp_path, usage, request_id):
    with open_ledger(tmp_path) as ledger:
        reservation = reserve(ledger)
        with pytest.raises(LedgerError):
            ledger.settle(reservation, usage, request_id=request_id)

        assert ledger.spent_usd == WORST
        ledger.settle(reservation, Usage(input=1, output=1))  # can be retried
    assert len(lines(tmp_path)) == 2


def test_a_reservation_is_settled_once(tmp_path):
    with open_ledger(tmp_path) as ledger:
        reservation = reserve(ledger)
        ledger.settle(reservation, Usage(input=1, output=1))
        with pytest.raises(LedgerError, match="not open"):
            ledger.settle(reservation, Usage(input=1, output=1))

    assert len(lines(tmp_path)) == 2


# Crashes, damage and closing.

def test_an_unsettled_call_still_counts_after_a_restart(tmp_path):
    with open_ledger(tmp_path) as ledger:
        reserve(ledger)  # the process "dies" before settling
    with open_ledger(tmp_path) as ledger:
        assert ledger.spent_usd == WORST
        assert ledger.total_spent_usd == WORST


def test_an_interrupted_write_is_cut_and_the_reservation_still_counts(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with open_ledger(tmp_path) as ledger:
        ledger.settle(reserve(ledger), Usage(input=1, output=1))
    data = path.read_bytes()
    path.write_bytes(data[:-20])  # the charge line is half written

    with open_ledger(tmp_path) as ledger:
        assert ledger.spent_usd == WORST
        assert ledger.repaired_tail
        reserve(ledger)
    assert read_ledger(path).ok
    assert len(lines(tmp_path)) == 2


def _damage(entry, **changes):
    return json.dumps({**entry, **changes}) + "\n"


def _new(entry, **changes):
    return _damage(entry, call_id=str(uuid.uuid4()), **changes)


@pytest.mark.parametrize("damage", [
    lambda held, charged: "not json\n",
    lambda held, charged: "\n",
    lambda held, charged: "\0\0\0\0\n",
    lambda held, charged: "[1]\n",
    lambda held, charged: _new(held, cost_usd=1),
    lambda held, charged: _new(held, cost_usd="-1"),
    lambda held, charged: _new(held, cost_usd="NaN"),
    lambda held, charged: _new(held, type="refund"),
    lambda held, charged: _new(held, schema_version=2),
    lambda held, charged: _new(held, batch_id=None),
    lambda held, charged: _new(held, extra=1),
    lambda held, charged: _new(held, tokens={"input": -1}),
    lambda held, charged: _damage(held),  # the same reservation twice
    lambda held, charged: _damage(charged),  # charged twice
    lambda held, charged: _new(charged),  # a charge with no reservation
])
def test_a_damaged_ledger_is_refused_and_left_alone(tmp_path, damage):
    path = tmp_path / "ledger.jsonl"
    with open_ledger(tmp_path) as ledger:
        ledger.settle(reserve(ledger), Usage(input=1, output=1))
    with open(path, "a", encoding="ascii", newline="") as handle:
        handle.write(damage(*lines(tmp_path)) + "{half")
    before = path.read_bytes()

    with pytest.raises(LedgerError, match="line 3"):
        open_ledger(tmp_path)

    assert path.read_bytes() == before
    path.write_bytes(b"")
    open_ledger(tmp_path).close()  # the failed open released the lock


def test_a_charge_must_match_its_reservation(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with open_ledger(tmp_path) as ledger:
        ledger.settle(reserve(ledger), Usage(input=1, output=1))
    held, charged = lines(tmp_path)
    path.write_text(_damage(held) + _damage(charged, batch_id="other"),
                    encoding="ascii", newline="")

    with pytest.raises(LedgerError, match="line 2.*batch_id"):
        open_ledger(tmp_path)


def test_a_failed_write_stops_the_ledger(tmp_path, monkeypatch):
    def full_disk(path, line):
        raise OSError("disk full")

    with open_ledger(tmp_path) as ledger:
        reservation = reserve(ledger)
        with monkeypatch.context() as patched:
            patched.setattr(ledger_module, "append_line", full_disk)
            with pytest.raises(OSError):
                ledger.settle(reservation, Usage(input=1, output=1))

        assert ledger.spent_usd == WORST
        with pytest.raises(LedgerError, match="write failed"):
            reserve(ledger)
    with open_ledger(tmp_path) as ledger:
        assert ledger.spent_usd == WORST


def test_a_closed_ledger_refuses_calls(tmp_path):
    ledger = open_ledger(tmp_path)
    reservation = reserve(ledger)
    ledger.close()
    ledger.close()  # harmless

    with pytest.raises(LedgerError, match="closed"):
        reserve(ledger)
    with pytest.raises(LedgerError, match="closed"):
        ledger.settle(reservation, None)


# One process at a time.

def test_a_ledger_cannot_be_opened_twice(tmp_path):
    with open_ledger(tmp_path):
        with pytest.raises(LedgerError, match="in use"):
            open_ledger(tmp_path, batch="b2")
    open_ledger(tmp_path).close()


HOLDER = """
import sys
from runner.ledger import Ledger
ledger = Ledger(sys.argv[1], batch_id="other", batch_cap_usd=1)
print("held", flush=True)
sys.stdin.readline()
"""


def test_another_process_is_refused_until_the_holder_dies(tmp_path):
    path = tmp_path / "ledger.jsonl"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(LedgerError, match="in use"):
            open_ledger(tmp_path)
    finally:
        # A venv launcher may run Python as a child process, so end it by
        # closing its input; the crash case is covered below.
        holder.communicate("\n", timeout=30)
    open_ledger(tmp_path).close()


CRASHER = """
import os, sys, uuid
from runner.ledger import Ledger
ledger = Ledger(sys.argv[1], batch_id="b1", batch_cap_usd=10)
ledger.reserve(model_id="claude-opus-5-5", record_id=str(uuid.uuid4()),
               prompt_tokens=1000)
os._exit(3)
"""


def test_a_crashed_process_leaves_its_spend_and_frees_the_lock(tmp_path):
    path = tmp_path / "ledger.jsonl"
    done = subprocess.run([sys.executable, "-c", CRASHER, str(path)], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 3, done.stderr

    with open_ledger(tmp_path) as ledger:
        assert ledger.spent_usd == Decimal("2.564")


# Totals and the command.

def sample(tmp_path):
    with open_ledger(tmp_path, batch="b1") as ledger:
        ledger.settle(reserve(ledger), Usage(input=100, output=10, reasoning=5))
        ledger.settle(reserve(ledger), None)
        ledger.settle(reserve(ledger, model="cheap"), Usage(input=10, output=10))
    with open_ledger(tmp_path, batch="b2") as ledger:
        reserve(ledger)  # never settled
    return tmp_path / "ledger.jsonl"


def test_totals_by_batch_and_model(tmp_path):
    rows = totals(read_ledger(sample(tmp_path)).entries)

    assert [(r.batch_id, r.model_id) for r in rows] == [
        ("b1", "cheap"), ("b1", "m"), ("b2", "m")]
    cheap, main_model, open_call = rows
    assert (cheap.calls, cheap.estimated_calls) == (1, 0)
    assert cheap.cost_usd == Decimal("0.000002")
    assert (main_model.calls, main_model.estimated_calls) == (2, 1)
    assert main_model.cost_usd == Decimal("0.00025") + WORST
    # estimated calls add no token counts that were never reported
    assert (main_model.input_tokens, main_model.output_tokens,
            main_model.reasoning_tokens) == (100, 10, 5)
    assert (open_call.calls, open_call.estimated_calls) == (1, 1)
    assert (open_call.input_tokens, open_call.output_tokens) == (0, 0)
    assert open_call.cost_usd == WORST


def test_the_command_prints_totals(tmp_path, capsys):
    assert main([str(sample(tmp_path))]) == 0
    out = capsys.readouterr().out.splitlines()

    assert any(line.split()[:3] == ["b1", "cheap", "1"] for line in out)
    assert any(line.split()[:2] == ["b1", "total"] and "0.011252" in line
               for line in out)
    assert any(line.split()[0] == "all" and "0.022252" in line for line in out)


def test_the_command_reports_problems(tmp_path, capsys):
    path = sample(tmp_path)
    with open(path, "ab") as handle:
        handle.write(b"junk\n{half")

    assert main([str(path)]) == 1
    out = capsys.readouterr().out
    assert "line 8" in out and "line 9" in out
    assert path.read_bytes().endswith(b"{half")  # reading changes nothing


def test_the_command_on_a_missing_file_or_bad_arguments(tmp_path, capsys):
    assert main([str(tmp_path / "absent.jsonl")]) == 1
    assert "cannot read" in capsys.readouterr().out
    assert main(["a", "b"]) == 2


def test_the_command_runs_as_a_module(tmp_path):
    done = subprocess.run(
        [sys.executable, "-m", "runner.ledger", str(sample(tmp_path))],
        cwd=ROOT, capture_output=True, text=True)

    assert done.returncode == 0, done.stderr
    assert "b1" in done.stdout
    assert done.stderr == ""
