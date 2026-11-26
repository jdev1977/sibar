"""Tagging runs against fake batch APIs (T2.6): the repeat-tagging test, money
safety, resuming after a crash, retries. No network, no keys, no spending."""

import argparse
import json
from decimal import Decimal

import pytest
import yaml

from runner.ledger import Ledger, read_ledger
from runner.models import load_models
from runner.record import read_records, write_records
from runner.transport import NotSentError, SendError
from tagger import run
from tagger.models import ledger_models, load_taggers
from tagger.store import JobLog
from tests.fakes import FakeTransport
from tests.tagger_fakes import FakeAnthropic, FakeOpenAI, first_answers, json_response
from tests.tagger_support import record

# Fake keys, assembled at run time (docs/secrets.md).
FAKE_ANTHROPIC = "sk-" + "ant-" + "t" * 24
FAKE_OPENAI = "sk-" + "o" * 28
ENV = dict(zip(("ANTHROPIC" + "_API_KEY", "OPENAI" + "_API_KEY"),
               (FAKE_ANTHROPIC, FAKE_OPENAI)))


class Setup:
    def __init__(self, tmp_path, n=3, project_type="pipeline", task="csv-to-database"):
        self.tmp = tmp_path
        raw = yaml.safe_load(open("tagger/taggers.yaml", encoding="utf-8"))
        raw["confirmed_by_human"] = True
        self.taggers = tmp_path / "taggers.yaml"
        self.taggers.write_text(yaml.safe_dump(raw), encoding="utf-8")
        self.records = [record(project_type=project_type, task=task,
                               text=f"Output number {i}.\n```python\nx = {i}\n```\n")
                        for i in range(n)]
        self.records.append(record(status="failed"))  # never tagged, still copied
        self.records_path = tmp_path / "records.jsonl"
        write_records(self.records_path, self.records)
        self.ledger = tmp_path / "ledger.jsonl"
        self.cache = tmp_path / "cache.jsonl"
        self.project_type = project_type
        self.lines = []

    def args(self, *extra, tagger="claude-haiku-5-5", run_name="r1", paid=True,
             cache=None, caps=("5", "10")):
        parser = argparse.ArgumentParser()
        run.add_arguments(parser)
        argv = ["--records", str(self.records_path), "--type", self.project_type,
                "--tagger", tagger, "--run", run_name,
                "--run-dir", str(self.tmp / run_name), "--ledger", str(self.ledger),
                "--cache", str(cache or self.cache),
                "--taggers-file", str(self.taggers)]
        if paid:
            argv += ["--paid"]
            if caps:
                argv += ["--batch-cap", caps[0], "--total-cap", caps[1]]
        else:
            argv += ["--dry-run"]
        return parser.parse_args(argv + list(extra))

    def tag(self, fake, *extra, environ=ENV, wait=True, **kwargs):
        """Run the command; with ``wait`` (the default) it polls until done,
        each poll returning at once."""
        transport = fake if isinstance(fake, FakeTransport) else FakeTransport(fake.handler)
        extra = extra + (("--wait",) if wait else ())
        code = run.run_tag(self.args(*extra, **kwargs), environ=environ,
                           out=self.lines.append, transport=transport,
                           sleep=lambda seconds: None)
        return code, transport

    def output(self, tagger="claude-haiku-5-5", run_name="r1"):
        found = read_records(self.tmp / run_name / f"records.{tagger}.jsonl")
        assert found.ok
        return found.records

    def ledger_lines(self):
        return read_ledger(self.ledger).entries


def tags_of(records, extractor="rubric.pipeline"):
    return {r["record_id"]: {f["name"]: f["value"] for f in r["features"]
                             if f["extractor"] == extractor}
            for r in records if r["status"] == "ok"}


# --- the done-when: the same output tagged twice gives the same tags ---------------

def test_repeat_tagging_gives_the_same_tags_and_sends_nothing(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    code, transport = setup.tag(fake)
    assert code == run.EXIT_OK
    first = tags_of(setup.output())
    assert len(first) == 3 and all(t["status"] == "ok" for t in first.values())
    assert fake.creates == 1
    sent = len(transport.requests)

    # Again, in the same run and in a new run: answered from the cache.
    code, again = setup.tag(fake)
    assert code == run.EXIT_OK and len(again.requests) == 0
    code, other = setup.tag(fake, run_name="r2")
    assert code == run.EXIT_OK and len(other.requests) == 0
    assert tags_of(setup.output()) == first == tags_of(setup.output(run_name="r2"))
    assert fake.creates == 1 and sent == len(transport.requests)
    # The two copies are byte for byte the same records.
    assert (tmp_path / "r1" / "records.claude-haiku-5-5.jsonl").read_bytes() == \
        (tmp_path / "r2" / "records.claude-haiku-5-5.jsonl").read_bytes()


def test_a_live_repeat_uses_its_own_cache_and_does_send(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    setup.tag(fake)
    code, transport = setup.tag(fake, run_name="repeat",
                                cache=tmp_path / "cache-repeat.jsonl")
    assert code == run.EXIT_OK and fake.creates == 2


def test_tags_are_stored_in_the_record_format(tmp_path):
    setup = Setup(tmp_path)
    setup.tag(FakeAnthropic())
    records = setup.output()
    assert len(records) == 4  # the failed record is copied untouched
    tagged = [r for r in records if r["status"] == "ok"]
    for rec in tagged:
        assert rec["extractors"] == [{"extractor": "rubric.pipeline",
                                      "extractor_version": "1@claude-haiku-5-5"}]
    failed = [r for r in records if r["status"] == "failed"][0]
    assert failed["extractors"] == [] and failed["features"] == []
    # The input file is not changed.
    assert read_records(setup.records_path).records == setup.records


def test_two_taggers_write_separate_copies(tmp_path):
    setup = Setup(tmp_path)
    setup.tag(FakeAnthropic())
    setup.tag(FakeOpenAI(), tagger="gpt-6-luna")
    haiku, luna = setup.output(), setup.output("gpt-6-luna")
    for records, version in ((haiku, "1@claude-haiku-5-5"), (luna, "1@gpt-6-luna")):
        for rec in records:
            if rec["status"] == "ok":
                assert [e["extractor_version"] for e in rec["extractors"]] == [version]


# --- dry run and refusals -------------------------------------------------------------

def test_a_dry_run_sends_and_writes_nothing(tmp_path):
    setup = Setup(tmp_path)
    code, transport = setup.tag(FakeAnthropic(), paid=False)
    assert code == run.EXIT_OK and transport.requests == []
    assert not setup.ledger.exists() and not setup.cache.exists()
    assert not (tmp_path / "r1").exists()
    text = "\n".join(setup.lines)
    assert "3 to send" in text and "Worst case for 3 requests" in text
    assert "batch price (x0.5)" in text


def test_the_dry_run_can_show_one_request(tmp_path):
    setup = Setup(tmp_path)
    rid = setup.records[0]["record_id"]
    setup.tag(FakeAnthropic(), "--show-prompt", rid, paid=False)
    shown = json.loads(next(line for line in setup.lines if line.startswith("{")))
    assert shown["model"] == "claude-haiku-5-5" and "Output number 0" in \
        shown["messages"][0]["content"]


@pytest.mark.parametrize("change, environ, message", [
    ("unconfirmed", ENV, "confirmed_by_human"),
    ("no caps", ENV, "--batch-cap"),
    (None, {}, "no key"),
])
def test_a_paid_run_is_refused_without_its_conditions(tmp_path, change, environ, message):
    setup = Setup(tmp_path)
    if change == "unconfirmed":
        raw = yaml.safe_load(setup.taggers.read_text(encoding="utf-8"))
        raw["confirmed_by_human"] = False
        setup.taggers.write_text(yaml.safe_dump(raw), encoding="utf-8")
    code, transport = setup.tag(FakeAnthropic(), environ=environ,
                                caps=None if change == "no caps" else ("5", "10"))
    assert code == run.EXIT_REFUSED and transport.requests == []
    assert message in setup.lines[-1]


# --- money ------------------------------------------------------------------------------

def test_every_request_is_reserved_before_the_job_is_created(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    seen = {}

    def handler(request, number):
        if request.method == "POST":
            seen["reserved"] = [e for e in setup.ledger_lines() if e["type"] == "reserve"]
            seen["charged"] = [e for e in setup.ledger_lines() if e["type"] == "charge"]
        return fake.handler(request, number)

    code, _ = setup.tag(FakeTransport(handler))
    assert code == run.EXIT_OK
    assert len(seen["reserved"]) == 3 and seen["charged"] == []
    assert {e["record_id"] for e in seen["reserved"]} == \
        {r["record_id"] for r in setup.records if r["status"] == "ok"}
    for entry in seen["reserved"]:
        assert entry["tokens"]["output"] == 16000 and entry["model_id"] == "claude-haiku-5-5"
        assert entry["batch_id"] == "tag-r1"
    # Settled from the reported usage: 3000 in, 400 out at the standard rate.
    charges = [e for e in setup.ledger_lines() if e["type"] == "charge"]
    assert len(charges) == 3
    assert all(Decimal(c["cost_usd"]) == Decimal("0.0005") and not c["estimated"]
               for c in charges)


def test_the_cap_stops_a_job_that_would_not_fit(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    code, transport = setup.tag(fake, caps=("0.0001", "10"))
    assert code == run.EXIT_BUDGET and fake.creates == 0
    assert transport.requests == [] and not [
        e for e in setup.ledger_lines() if e["type"] == "reserve"] if setup.ledger.exists() \
        else True


def test_a_cap_that_fits_some_requests_sends_only_those(tmp_path):
    setup = Setup(tmp_path, n=5)
    taggers = load_taggers(setup.taggers)
    from tagger.prompt import build_request
    from tests.tagger_support import rubric
    worst = run.call_cost(taggers.get("claude-haiku-5-5").model,
                          build_request(rubric(), taggers.get("claude-haiku-5-5"),
                                        setup.records[0]).prompt_tokens, 16000)
    cap = str(worst * 2 + worst / 2)
    fake = FakeAnthropic()
    code, _ = setup.tag(fake, caps=(cap, "10"))
    assert code == run.EXIT_BUDGET
    assert fake.creates == 1 and len(next(iter(fake.batches.values()))) == 2
    spent = sum(Decimal(e["cost_usd"]) for e in
                {e["call_id"]: e for e in setup.ledger_lines()}.values())
    assert spent <= Decimal(cap)


def test_unbilled_results_settle_at_zero(tmp_path):
    setup = Setup(tmp_path, n=2)
    fake = FakeAnthropic(reply=lambda cid, params, n: {
        "type": "errored", "error": {"type": "error", "error": {
            "type": "api_error", "message": "Internal server error"}}})
    setup.tag(fake)
    charges = [e for e in setup.ledger_lines() if e["type"] == "charge"]
    assert charges and all(Decimal(c["cost_usd"]) == 0 for c in charges)


# --- retries and faults --------------------------------------------------------------------

def test_a_faulty_answer_is_asked_once_more_then_marked(tmp_path):
    setup = Setup(tmp_path, n=1)

    def reply(cid, params, n):
        data = json.loads(first_answers(params))
        data["opening"]["answer"] = "flattery"
        return json.dumps(data)

    fake = FakeAnthropic(reply=reply)
    code, _ = setup.tag(fake)
    assert fake.creates == 2  # the first job and the retry
    tags = next(iter(tags_of(setup.output()).values()))
    assert tags["opening"] is None and tags["status"] == "partial"
    assert "opening" in tags["error"]
    assert code == run.EXIT_OK


def test_a_retry_that_succeeds_is_stored_as_given(tmp_path):
    setup = Setup(tmp_path, n=1)
    fake = FakeAnthropic(reply=lambda cid, params, n:
                         "not json" if n == 1 else first_answers(params))
    setup.tag(fake)
    tags = next(iter(tags_of(setup.output()).values()))
    assert tags["status"] == "ok" and fake.creates == 2


def test_two_refusals_store_an_error(tmp_path):
    setup = Setup(tmp_path, n=1)

    def refuse(cid, params, n):
        return {"type": "succeeded", "message": {
            "id": "m", "model": params["model"], "content": [{"type": "text",
                                                               "text": "No."}],
            "stop_reason": "refusal", "usage": {"input_tokens": 10, "output_tokens": 2}}}

    fake = FakeAnthropic(reply=refuse)
    code, _ = setup.tag(fake)
    tags = next(iter(tags_of(setup.output()).values()))
    assert tags == {"status": "error", "error": tags["error"]}
    assert "refused" in tags["error"] and code == run.EXIT_WAITING
    # --retry-errors tries once more.
    fake.reply = lambda cid, params, n: first_answers(params)
    code, _ = setup.tag(fake, "--retry-errors")
    assert next(iter(tags_of(setup.output()).values()))["status"] == "ok"


def test_expired_requests_are_sent_again_without_using_the_retry(tmp_path):
    setup = Setup(tmp_path, n=1)
    fake = FakeAnthropic(reply=lambda cid, params, n: {"type": "expired"}
                         if n == 1 else first_answers(params))
    code, _ = setup.tag(fake)
    assert code == run.EXIT_OK and fake.creates == 2
    jobs = JobLog(tmp_path / "r1" / "jobs.jsonl")
    attempts = [r["attempt"] for job in jobs.jobs.values() for r in job.results.values()]
    assert attempts == [1, 1]


def test_a_gate_that_stops_stores_only_the_gate(tmp_path):
    setup = Setup(tmp_path, n=1)
    fake = FakeAnthropic(reply=lambda cid, params, n: first_answers(params, gate="declines"))
    setup.tag(fake)
    tags = next(iter(tags_of(setup.output()).values()))
    assert tags == {"response_mode": "declines", "status": "ok"}


# --- jobs that take time, and crashes ------------------------------------------------------

def test_a_job_still_running_is_collected_by_a_later_run(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic(ended=False)
    code, _ = setup.tag(fake, wait=False)
    assert code == run.EXIT_WAITING and tags_of(setup.output()) == {
        r["record_id"]: {} for r in setup.records if r["status"] == "ok"}
    # Reserved, not settled, while the job runs.
    assert {e["type"] for e in setup.ledger_lines()} == {"reserve"}
    fake.ended = True
    code, transport = setup.tag(fake, wait=False)
    assert code == run.EXIT_OK and fake.creates == 1
    assert len([e for e in setup.ledger_lines() if e["type"] == "charge"]) == 3
    assert all(t["status"] == "ok" for t in tags_of(setup.output()).values())


def test_wait_polls_until_done(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic(ended=False)
    polls = []

    def sleep(seconds):
        polls.append(seconds)
        fake.ended = True

    code = run.run_tag(setup.args("--wait", "--poll-seconds", "5"), environ=ENV,
                       out=setup.lines.append, transport=FakeTransport(fake.handler),
                       sleep=sleep)
    assert code == run.EXIT_OK and polls == [5.0]


def test_a_create_without_an_answer_is_found_not_sent_twice(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    fake.lose_create = True  # the job is made, the answer is lost
    code, _ = setup.tag(fake)
    assert code == run.EXIT_BLOCKED and fake.creates == 1
    code, _ = setup.tag(fake)  # finds the job by size and time, collects it
    assert code == run.EXIT_OK and fake.creates == 1
    jobs = JobLog(tmp_path / "r1" / "jobs.jsonl")
    assert [j.reconciled for j in jobs.jobs.values()] == [True]


def test_a_lost_create_that_made_no_job_blocks_until_abandoned(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    fake.fail_create = SendError("dropped before the provider saw it (fake)")
    code, _ = setup.tag(fake)
    assert code == run.EXIT_BLOCKED and fake.creates == 0
    code, _ = setup.tag(fake)  # still not found: still blocked, nothing sent
    assert code == run.EXIT_BLOCKED and fake.creates == 0
    submission = next(iter(JobLog(tmp_path / "r1" / "jobs.jsonl").jobs))
    code, _ = setup.tag(fake, "--abandon", submission)
    assert code == run.EXIT_OK and fake.creates == 1
    # The abandoned job's reservations stay counted at their worst case.
    entries = setup.ledger_lines()
    open_calls = {e["call_id"] for e in entries if e["type"] == "reserve"} - \
        {e["call_id"] for e in entries if e["type"] == "charge"}
    assert len(open_calls) == 3


def test_a_create_that_certainly_failed_is_settled_at_zero(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    fake.fail_create = json_response({"error": {"type": "invalid_request_error",
                                                "message": "bad"}}, 400)
    code, _ = setup.tag(fake)
    assert code != run.EXIT_OK and fake.creates == 0
    charges = [e for e in setup.ledger_lines() if e["type"] == "charge"]
    assert len(charges) == 3 and all(Decimal(c["cost_usd"]) == 0 for c in charges)
    code, _ = setup.tag(fake)  # free to send again
    assert code == run.EXIT_OK and fake.creates == 1


def test_a_not_sent_create_is_settled_at_zero(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    fake.fail_create = NotSentError("could not connect (fake)")
    code, _ = setup.tag(fake)
    assert fake.creates == 0
    assert all(Decimal(e["cost_usd"]) == 0 for e in setup.ledger_lines()
               if e["type"] == "charge")


def test_a_job_prepared_but_never_sent_is_released(tmp_path):
    setup = Setup(tmp_path, n=1)
    # A run that stopped between reserving and sending.
    taggers = load_taggers(setup.taggers)
    models = ledger_models(load_models("models.yaml"), taggers)
    with Ledger(setup.ledger, batch_id="tag-r1", batch_cap_usd="5", models=models) as led:
        reservation = led.reserve(model_id="claude-haiku-5-5",
                                  record_id=setup.records[0]["record_id"],
                                  prompt_tokens=5000, max_output_tokens=16000)
    jobs = JobLog(tmp_path / "r1" / "jobs.jsonl")
    jobs.add("prepared", "sdead", requests=[{
        "custom_id": "sdead-0", "key": "k", "record_id": setup.records[0]["record_id"],
        "attempt": 1, "items": ["response_mode"], "call_id": reservation.call_id}])
    fake = FakeAnthropic()
    code, _ = setup.tag(fake)
    assert code == run.EXIT_OK and fake.creates == 1
    charge = [e for e in setup.ledger_lines()
              if e["type"] == "charge" and e["call_id"] == reservation.call_id]
    assert charge and Decimal(charge[0]["cost_usd"]) == 0


def test_a_found_job_with_foreign_results_is_refused(tmp_path):
    setup = Setup(tmp_path)
    fake = FakeAnthropic()
    fake.lose_create = True
    setup.tag(fake)
    # Someone else's job of the same size replaces ours at the provider.
    batch_id = next(iter(fake.batches))
    fake.batches[batch_id] = [(f"other-{i}", p) for i, (_, p) in
                              enumerate(fake.batches[batch_id])]
    code, _ = setup.tag(fake)
    assert code == run.EXIT_BLOCKED and "did not send" in setup.lines[-2]
    assert not [e for e in setup.ledger_lines() if e["type"] == "charge"]


# --- the non-Claude tagger, and other types ------------------------------------------------

def test_the_openai_tagger_uses_the_batch_api(tmp_path):
    setup = Setup(tmp_path, n=2)
    fake = FakeOpenAI()
    code, transport = setup.tag(fake, tagger="gpt-6-luna")
    assert code == run.EXIT_OK and fake.creates == 1
    batch = next(iter(fake.batches.values()))
    submission = batch["metadata"]["sibar_submission"]
    assert submission.startswith("s")
    upload = next(r for r in transport.requests if r.url.endswith("/v1/files"))
    assert b"claude-opus-5-5" not in upload.body  # the writer's model is not sent
    tags = tags_of(setup.output("gpt-6-luna"))
    assert all(t["status"] == "ok" for t in tags.values())
    charges = [e for e in setup.ledger_lines() if e["type"] == "charge"]
    assert all(c["tokens"]["input"] == 2000 for c in charges)


def test_an_openai_job_is_found_by_its_metadata(tmp_path):
    setup = Setup(tmp_path, n=1)
    fake = FakeOpenAI()
    original = fake.handler

    def lose_batch_answer(request, number):
        response = original(request, number)
        if request.method == "POST" and request.url.endswith("/v1/batches"):
            return SendError("dropped (fake)")
        return response

    code, _ = setup.tag(FakeTransport(lose_batch_answer), tagger="gpt-6-luna")
    assert code == run.EXIT_BLOCKED and fake.creates == 1
    code, _ = setup.tag(fake, tagger="gpt-6-luna")
    assert code == run.EXIT_OK and fake.creates == 1


def test_an_openai_job_that_failed_validation_settles_at_zero(tmp_path):
    setup = Setup(tmp_path, n=1)
    fake = FakeOpenAI(status="failed")
    code, _ = setup.tag(fake, tagger="gpt-6-luna")
    charges = [e for e in setup.ledger_lines() if e["type"] == "charge"]
    assert charges and all(Decimal(c["cost_usd"]) == 0 for c in charges)
    # A job that never runs is sent again a bounded number of times.
    assert fake.creates == run.MAX_SENDS and code == run.EXIT_WAITING
    tags = next(iter(tags_of(setup.output("gpt-6-luna")).values()))
    assert tags["status"] == "error" and "without being processed" in tags["error"]


@pytest.mark.parametrize("project_type, task", [
    ("website", "bakery-landing"), ("math", "loan-amortization"),
    ("engineering", "shelf-bracket")])
def test_every_rubric_type_can_be_tagged(tmp_path, project_type, task):
    setup = Setup(tmp_path, n=1, project_type=project_type, task=task)
    code, _ = setup.tag(FakeAnthropic())
    assert code == run.EXIT_OK
    tags = tags_of(setup.output(), f"rubric.{project_type}")
    assert all(t["status"] == "ok" for t in tags.values())


def test_api_keys_never_reach_stored_files(tmp_path):
    setup = Setup(tmp_path, n=1)
    key = FAKE_ANTHROPIC
    fake = FakeAnthropic(reply=lambda cid, params, n: "echo " + key)
    setup.tag(fake)
    for path in tmp_path.rglob("*.jsonl"):
        assert key not in path.read_text(encoding="utf-8"), path
