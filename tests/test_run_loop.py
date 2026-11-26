"""The generation run loop (T0.5), with a fake transport only.

Covers the done-when (one prompt, every listed model, a valid record each),
retries, errors that must not be retried, resuming after a crash, the budget
stop, billing rules and key scrubbing. No request leaves the machine.
"""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from fakes import (FakeResponse, FakeTransport, NotSentError, SendError,
                   anthropic_stream, error_response, ok_stream, openai_stream, sse)
from runner.ledger import Ledger, read_ledger
from runner.loop import Runner, RunError, pending_cells, plan_cells
from runner.models import load_models
from runner.prompts import load_prompt_file
from runner.record import check_files, files_dir, read_records, validate_record
from runner.retry import RetryPolicy

ROOT = Path(__file__).resolve().parents[1]
MODELS = load_models(ROOT / "models.yaml")
TASK = load_prompt_file(ROOT / "tests" / "fixtures" / "prompts" / "example"
                        / "tiny-task.yaml")
PAGE = ("Here is your page.\n\n**index.html**\n```html\n<!DOCTYPE html>\n"
        "<html><body>Bread</body></html>\n```\n")


def make_keys():
    return {model.api_key_env: f"test-key-{model.provider}-" + "z" * 24
            for model in MODELS.models}


KEYS = make_keys()


def by_provider(text=PAGE):
    """A handler answering each request with a good stream for its provider."""
    def handler(request, number):
        body = json.loads(request.body)
        model = MODELS.get(body["model"])
        return ok_stream(model.provider, text, model.id)
    return handler


class Harness:
    def __init__(self, tmp_path, handler, cap="100", total="1000", models=MODELS,
                 **options):
        self.tmp_path = tmp_path
        self.records = tmp_path / "run" / "records.jsonl"
        self.ledger_path = tmp_path / "ledger.jsonl"
        self.transport = FakeTransport(handler)
        self.output = []
        self.sleeps = []
        self.models = models
        self.cap, self.total = cap, total
        self.options = dict(retry=RetryPolicy(max_attempts=3), rpm=None,
                            sleep=self.sleeps.append, out=self.output.append)
        self.options.update(options)

    def run(self, cells, batch="b1", keys=KEYS):
        with Ledger(self.ledger_path, batch_id=batch, batch_cap_usd=self.cap,
                    total_cap_usd=self.total, models=self.models) as ledger:
            runner = Runner(batch_id=batch, records_path=self.records, ledger=ledger,
                            transport=self.transport, keys=keys, **self.options)
            todo, _ = pending_cells(cells, self.records, batch,
                                    runner.rerun_statuses, out=self.output.append)
            return runner.run(todo)

    def records_found(self):
        found = read_records(self.records)
        assert found.ok and found.truncated_tail is None
        return found.records

    def ledger_entries(self):
        found = read_ledger(self.ledger_path)
        assert found.ok
        return found.entries


def one_prompt_cells(models=MODELS.models, runs=1):
    return plan_cells([TASK], models, runs, levels=("L0",), wordings=("A",))


# --- The done-when ------------------------------------------------------------------


def test_one_prompt_runs_against_every_listed_model_and_saves_a_valid_record_each(
        tmp_path):
    harness = Harness(tmp_path, by_provider())
    summary = harness.run(one_prompt_cells())

    records = harness.records_found()
    assert sorted(r["model_id"] for r in records) == sorted(
        m.id for m in MODELS.models)
    assert summary.finished == {"ok": len(MODELS.models)}
    for record in records:
        assert validate_record(record) == []
        model = MODELS.get(record["model_id"])
        assert record["status"] == "ok"
        assert record["provider"] == model.provider
        assert record["source"] == "controlled" and record["surface"] == "api"
        assert record["system_prompt"] is None
        assert record["prompt_text"] == TASK.text("L0", "A")
        assert (record["task_id"], record["level"], record["wording"],
                record["run_index"]) == ("tiny-task", "L0", "A", 1)
        assert record["prompt_set_version"] == "0" and record["batch_id"] == "b1"
        assert record["raw_response"] == PAGE
        assert record["model_id_returned"] == model.id
        assert record["request_id"]
        assert record["tokens"]["output"] >= record["tokens"]["reasoning"] > 0
        assert record["cost_usd"] > 0
        assert record["settings"]["stream"] is True
        assert [f["path"] for f in record["files"]] == ["extracted/index.html"]
        assert check_files(record, files_dir(harness.records, record["record_id"])) == []
    opus = next(r for r in records if r["model_id"] == "claude-opus-5-5")
    assert opus["settings"]["max_tokens"] == 128000
    assert len(harness.transport.requests) == len(MODELS.models)


def test_record_costs_match_the_ledger(tmp_path):
    harness = Harness(tmp_path, by_provider())
    harness.run(one_prompt_cells())
    charges = {e["record_id"]: e for e in harness.ledger_entries()
               if e["type"] == "charge"}
    for record in harness.records_found():
        charge = charges[record["record_id"]]
        assert not charge["estimated"]
        assert Decimal(charge["cost_usd"]) == Decimal(str(record["cost_usd"]))
        assert charge["tokens"]["output"] == record["tokens"]["output"]


def test_each_attempt_is_reserved_before_sending(tmp_path):
    seen = []

    def handler(request, number):
        seen.append(len([e for e in read_ledger(tmp_path / "ledger.jsonl").entries
                         if e["type"] == "reserve"]))
        return anthropic_stream()
    harness = Harness(tmp_path, handler)
    harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")], runs=3))
    assert seen == [1, 2, 3]


# --- Retries ------------------------------------------------------------------------


def overloaded(headers=None):
    return error_response(529, {"type": "overloaded_error", "message": "Overloaded"},
                          headers=headers)


def test_retryable_errors_are_retried_with_a_separate_reservation_each(tmp_path):
    answers = [overloaded(), overloaded({"retry-after": "9"}), anthropic_stream()]
    harness = Harness(tmp_path, lambda request, n: answers[n - 1])
    summary = harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")]))

    records = harness.records_found()
    assert [r["status"] for r in records] == ["failed", "failed", "ok"]
    assert "HTTP 529" in records[0]["error"]
    assert len({r["record_id"] for r in records}) == 3
    entries = harness.ledger_entries()
    assert [e["type"] for e in entries] == ["reserve", "charge"] * 3
    assert [e["record_id"] for e in entries if e["type"] == "reserve"] == [
        r["record_id"] for r in records]
    assert len(harness.sleeps) == 2
    assert 1.0 <= harness.sleeps[0] <= 2.0  # backoff with jitter
    assert harness.sleeps[1] >= 9.0  # Retry-After is honoured
    assert summary.finished == {"ok": 1} and summary.attempts == 3


def test_retries_stop_at_the_attempt_limit_and_resume_tries_again(tmp_path):
    harness = Harness(tmp_path, lambda request, n: overloaded())
    cells = one_prompt_cells([MODELS.get("claude-haiku-5-5")])
    summary = harness.run(cells)
    assert [r["status"] for r in harness.records_found()] == ["failed"] * 3
    assert summary.finished == {"failed": 1}

    harness.transport.handler = lambda request, n: anthropic_stream(model="claude-haiku-5-5")
    summary = harness.run(cells)
    assert [r["status"] for r in harness.records_found()] == ["failed"] * 3 + ["ok"]
    assert summary.finished == {"ok": 1}


def test_a_retry_after_beyond_the_limit_is_not_waited_for(tmp_path):
    harness = Harness(tmp_path, lambda request, n: overloaded({"retry-after": "3600"}),
                      retry=RetryPolicy(max_attempts=5, max_retry_after=600))
    harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")]))
    assert len(harness.records_found()) == 1 and harness.sleeps == []


@pytest.mark.parametrize("failure", [
    SendError("read timed out"),
    lambda: FakeResponse(200, {}, sse(("message_start", {"type": "message_start",
                                                         "message": {}})),
                         error_after=1),
])
def test_a_request_that_may_have_been_billed_is_charged_at_worst_case(
        tmp_path, failure):
    answers = [failure if isinstance(failure, Exception) else failure(),
               anthropic_stream()]
    harness = Harness(tmp_path, lambda request, n: answers[n - 1])
    harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")]))

    first, second = harness.records_found()
    assert first["status"] == "failed" and first["cost_usd"] is None
    assert second["status"] == "ok"
    charges = [e for e in harness.ledger_entries() if e["type"] == "charge"]
    assert charges[0]["estimated"] is True
    # Opus 5.5: prompt estimate at $4/M plus 128000 output tokens at $20/M
    assert Decimal(charges[0]["cost_usd"]) > Decimal("2.56")
    assert charges[1]["estimated"] is False


def test_a_request_that_never_left_the_machine_costs_nothing(tmp_path):
    answers = [NotSentError("could not connect"), anthropic_stream()]
    harness = Harness(tmp_path, lambda request, n: answers[n - 1])
    harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")]))
    first, second = harness.records_found()
    assert first["status"] == "failed" and first["cost_usd"] == 0
    assert "not sent" in first["error"]
    charges = [e for e in harness.ledger_entries() if e["type"] == "charge"]
    assert charges[0]["cost_usd"] == "0" and not charges[0]["estimated"]


# --- Errors that must not be retried -------------------------------------------------


def test_an_auth_error_is_not_retried_and_stops_that_provider_only(tmp_path):
    def handler(request, number):
        body = json.loads(request.body)
        if body["model"].startswith("claude"):
            return error_response(401, {"type": "authentication_error",
                                        "message": "invalid x-api-key"})
        return by_provider()(request, number)
    harness = Harness(tmp_path, handler)
    summary = harness.run(one_prompt_cells())

    records = harness.records_found()
    claude = [r for r in records if r["provider"] == "anthropic"]
    assert len(claude) == 1 and claude[0]["status"] == "failed"
    assert "HTTP 401" in claude[0]["error"]
    assert sum(1 for r in records if r["status"] == "ok") == len(MODELS.models) - 2
    assert summary.skipped == 1  # the second Anthropic model was not called
    assert harness.sleeps == []
    assert any("anthropic" in line and "stop" in line for line in harness.output)


def test_a_validation_error_stops_that_model_only(tmp_path):
    def handler(request, number):
        if json.loads(request.body)["model"] == "gpt-6-luna":
            return error_response(400, {"message": "bad request",
                                        "type": "invalid_request_error"})
        return by_provider()(request, number)
    harness = Harness(tmp_path, handler)
    cells = one_prompt_cells([MODELS.get("gpt-6-luna"), MODELS.get("gpt-6.2-sol")],
                             runs=2)
    summary = harness.run(cells)
    statuses = [(r["model_id"], r["status"]) for r in harness.records_found()]
    assert statuses == [("gpt-6-luna", "failed"), ("gpt-6.2-sol", "ok"),
                        ("gpt-6.2-sol", "ok")]
    assert summary.skipped == 1


def test_an_unreadable_response_is_not_retried(tmp_path):
    bad = FakeResponse(200, {}, ["data: {oops\n", "\n"])
    harness = Harness(tmp_path, lambda request, n: bad)
    harness.run(one_prompt_cells([MODELS.get("deepseek-flash")], runs=2))
    records = harness.records_found()
    assert len(records) == 1 and "unreadable" in records[0]["error"]
    charge = [e for e in harness.ledger_entries() if e["type"] == "charge"][0]
    assert charge["estimated"]


# --- Statuses and resuming ------------------------------------------------------------


def test_refused_and_truncated_count_as_done_unless_asked(tmp_path):
    answers = {"claude-opus-5-5": anthropic_stream(stop_reason="max_tokens"),
               "gpt-6.2-sol": openai_stream(text="", refusal="No.")}

    def handler(request, number):
        return answers[json.loads(request.body)["model"]]
    harness = Harness(tmp_path, handler)
    cells = one_prompt_cells([MODELS.get("claude-opus-5-5"), MODELS.get("gpt-6.2-sol")])
    summary = harness.run(cells)
    assert summary.finished == {"truncated": 1, "refused": 1}

    todo, done = pending_cells(cells, harness.records, "b1", ("failed",))
    assert (todo, done) == ([], 2)
    todo, done = pending_cells(cells, harness.records, "b1", ("failed", "truncated"))
    assert [cell.model.id for cell in todo] == ["claude-opus-5-5"] and done == 1


def test_a_truncated_record_keeps_its_files(tmp_path):
    harness = Harness(tmp_path, lambda r, n: anthropic_stream(
        text=PAGE, stop_reason="max_tokens"))
    harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")]))
    (record,) = harness.records_found()
    assert record["status"] == "truncated" and record["files"]


def test_a_crash_mid_run_resumes_without_redoing_finished_cells(tmp_path):
    class Crash(BaseException):
        pass

    def crashing(request, number):
        if number == 4:
            raise Crash()
        return by_provider()(request, number)
    harness = Harness(tmp_path, crashing)
    cells = one_prompt_cells()
    with pytest.raises(Crash):
        harness.run(cells)
    assert len(harness.records_found()) == 3
    # The crash also left half a line at the end of the record file.
    with open(harness.records, "ab") as handle:
        handle.write(b'{"schema_version": 1, "record_id": "cut')
    entries = read_ledger(harness.ledger_path).entries
    reserves = [e for e in entries if e["type"] == "reserve"]
    assert len(reserves) == 4
    # The crashed call counts at its worst case, settled or not.
    last_line = [e for e in entries if e["call_id"] == reserves[-1]["call_id"]][-1]
    assert last_line["estimated"]

    harness.transport.handler = by_provider()
    summary = harness.run(cells)
    records = harness.records_found()
    assert len(records) == len(MODELS.models)
    assert len({(r["model_id"], r["run_index"]) for r in records}) == len(records)
    assert summary.cells == len(MODELS.models) - 3
    assert any("unfinished" in line for line in harness.output)


def test_a_changed_prompt_with_the_same_version_is_refused(tmp_path):
    harness = Harness(tmp_path, by_provider())
    cells = one_prompt_cells([MODELS.get("claude-opus-5-5")])
    harness.run(cells)
    changed = replace(TASK, texts={**TASK.texts, ("L0", "A"): "Something else."})
    with pytest.raises(RunError, match="prompt_set_version"):
        pending_cells(plan_cells([changed], [MODELS.get("claude-opus-5-5")], 1,
                                 levels=("L0",), wordings=("A",)),
                      harness.records, "b1", ("failed",))


def test_a_new_batch_does_not_count_old_records(tmp_path):
    harness = Harness(tmp_path, by_provider())
    cells = one_prompt_cells([MODELS.get("claude-opus-5-5")])
    harness.run(cells)
    todo, done = pending_cells(cells, harness.records, "b2", ("failed",))
    assert len(todo) == 1 and done == 0


def test_a_record_file_with_bad_lines_is_refused(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(RunError, match="line 1"):
        pending_cells(one_prompt_cells(), path, "b1", ("failed",))


# --- Budget ---------------------------------------------------------------------------


def test_the_run_stops_cleanly_at_the_budget_cap(tmp_path):
    # Haiku 5.5 worst case: 1031 prompt tokens at $0.10/M + 128000 at $0.50/M
    # = $0.0641031 per call. Each fake call costs about $0.005 (10000 output
    # tokens), so the third reservation would pass a $0.07 cap.
    haiku = MODELS.get("claude-haiku-5-5")
    harness = Harness(tmp_path, lambda r, n: anthropic_stream(
        model=haiku.id, output_tokens=10_000, thinking_tokens=0), cap="0.07")
    summary = harness.run(one_prompt_cells([haiku], runs=5))
    assert summary.stopped == "budget"
    assert "cap" in summary.stop_message
    sent = len(harness.transport.requests)
    assert sent == 2
    assert len(harness.records_found()) == sent
    entries = harness.ledger_entries()
    assert sum(e["type"] == "reserve" for e in entries) == sent
    assert sum(e["type"] == "charge" for e in entries) == sent


def test_a_zero_cap_sends_nothing(tmp_path):
    harness = Harness(tmp_path, by_provider(), cap="0")
    summary = harness.run(one_prompt_cells())
    assert summary.stopped == "budget" and harness.transport.requests == []
    assert not harness.records.exists()


def test_a_call_that_costs_more_than_reserved_stops_the_run(tmp_path):
    huge = anthropic_stream(output_tokens=10_000_000, thinking_tokens=0)
    harness = Harness(tmp_path, lambda r, n: huge)
    summary = harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5")], runs=3))
    assert summary.stopped == "over_reservation"
    assert len(harness.transport.requests) == 1


# --- Keys -----------------------------------------------------------------------------


def test_keys_never_reach_records_ledger_files_or_output(tmp_path):
    key = KEYS["ANTHROPIC_API_KEY"]
    leaky_error = error_response(400, {"type": "invalid_request_error",
                                       "message": f"key {key} is not valid here"})
    leaky_text = f"Your key is {key}.\n\n```txt secret.txt\n{key}\n```\n"
    answers = [leaky_error, anthropic_stream(text=leaky_text, model="claude-haiku-5-5")]
    harness = Harness(tmp_path, lambda r, n: answers[n - 1])
    harness.run(one_prompt_cells([MODELS.get("claude-opus-5-5"),
                                  MODELS.get("claude-haiku-5-5")]))
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes(), path
    assert all(key not in line for line in harness.output)
    records = harness.records_found()
    assert "[redacted]" in records[0]["error"]
    assert "[redacted]" in records[1]["raw_response"]
    # the key went only into the request headers
    request = harness.transport.requests[0]
    assert key in request.headers["authorization"]
    assert key not in request.body.decode() and key not in request.url


def test_a_missing_key_is_refused_before_any_call(tmp_path):
    harness = Harness(tmp_path, by_provider())
    keys = {name: value for name, value in KEYS.items() if name != "GEMINI_API_KEY"}
    with pytest.raises(RunError, match="GEMINI_API_KEY"):
        harness.run(one_prompt_cells(), keys=keys)
    assert harness.transport.requests == []


# --- Interrupts -----------------------------------------------------------------------


def test_an_interrupt_lets_the_call_in_flight_finish_and_stops_the_run(
        tmp_path, monkeypatch):
    import threading
    release = threading.Event()

    def handler(request, number):
        release.wait(5)
        return anthropic_stream(model="claude-haiku-5-5")
    original = Runner._join
    calls = []

    def join(threads):
        calls.append(1)
        if len(calls) == 1:
            release.set()
            raise KeyboardInterrupt
        original(threads)
    monkeypatch.setattr(Runner, "_join", staticmethod(join))
    harness = Harness(tmp_path, handler)
    summary = harness.run(one_prompt_cells([MODELS.get("claude-haiku-5-5")], runs=3))
    assert summary.stopped == "interrupted"
    assert len(harness.transport.requests) == 1
    assert [r["status"] for r in harness.records_found()] == ["ok"]
    assert summary.not_started == 2
    assert [e["type"] for e in harness.ledger_entries()] == ["reserve", "charge"]


# --- Workers --------------------------------------------------------------------------


def test_several_workers_fill_every_cell_once(tmp_path):
    harness = Harness(tmp_path, by_provider(), workers=4)
    cells = plan_cells([TASK], MODELS.models, 2)  # 6 prompts x 2 runs x 8 models
    summary = harness.run(cells)
    records = harness.records_found()
    assert len(records) == len(cells) == 96
    keys = {(r["model_id"], r["level"], r["wording"], r["run_index"]) for r in records}
    assert len(keys) == 96
    assert summary.finished == {"ok": 96}
    entries = harness.ledger_entries()
    assert sum(e["type"] == "charge" for e in entries) == 96


def test_plan_orders_cells_prompt_by_prompt():
    cells = plan_cells([TASK], MODELS.models[:2], 2, levels=("L0", "L1"),
                       wordings=("A",))
    assert [(c.level, c.run_index, c.model.id) for c in cells] == [
        ("L0", 1, "claude-opus-5-5"), ("L0", 1, "claude-haiku-5-5"),
        ("L0", 2, "claude-opus-5-5"), ("L0", 2, "claude-haiku-5-5"),
        ("L1", 1, "claude-opus-5-5"), ("L1", 1, "claude-haiku-5-5"),
        ("L1", 2, "claude-opus-5-5"), ("L1", 2, "claude-haiku-5-5")]
