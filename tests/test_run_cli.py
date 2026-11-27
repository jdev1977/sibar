"""The command line (``python -m runner.run``), with a fake transport only."""

import json
import re
from pathlib import Path

import pytest
import yaml

from fakes import FakeTransport, anthropic_stream, ok_stream
from runner.ledger import DEFAULT_PATH, read_ledger
from runner.models import load_models
from runner.record import read_records, validate_record
from runner.run import main

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "tests" / "fixtures" / "prompts" / "example" / "tiny-task.yaml"
MODELS = load_models(ROOT / "models.yaml")
ONE = ["--prompts", str(PROMPT), "--levels", "L0", "--wordings", "A"]


@pytest.fixture
def env():
    """Fake keys for every provider, built at run time."""
    return {model.api_key_env: f"fake-{model.provider}-" + "y" * 30
            for model in MODELS.models}


def models_file(tmp_path, value):
    """A copy of models.yaml with confirmed_by_human set to ``value``, whatever
    the committed file says."""
    text = (ROOT / "models.yaml").read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^confirmed_by_human:.*$",
                          f"confirmed_by_human: {str(value).lower()}", text)
    assert count == 1
    path = tmp_path / f"models-{str(value).lower()}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def confirmed(tmp_path):
    """A copy of models.yaml with confirmed_by_human set to true."""
    return models_file(tmp_path, True)


@pytest.fixture
def unconfirmed(tmp_path):
    """A copy of models.yaml with confirmed_by_human set to false."""
    return models_file(tmp_path, False)


def no_network(request, number):
    raise AssertionError("no request may be sent")


def good(request, number):
    body = json.loads(request.body)
    model = MODELS.get(body["model"])
    return ok_stream(model.provider, "A poem about bread.", model.id)


def run(argv, transport=None, environ=None):
    output = []
    code = main(argv, transport=transport or FakeTransport(no_network),
                environ=environ or {}, out=output.append)
    return code, "\n".join(output)


def paid(tmp_path, confirmed, *extra, batch="b1"):
    return ONE + ["--batch-id", batch, "--paid", "--batch-cap", "20",
                  "--total-cap", "50", "--ledger", str(tmp_path / "ledger.jsonl"),
                  "--out", str(tmp_path / "out" / "records.jsonl"),
                  "--models-file", str(confirmed), "--rpm", "anthropic=100000",
                  "--rpm", "openai=100000", "--rpm", "google=100000",
                  "--rpm", "deepseek=100000", *extra]


# --- Mode ------------------------------------------------------------------------------


def test_a_mode_is_required(tmp_path):
    with pytest.raises(SystemExit) as exit_:
        run(ONE + ["--batch-id", "b1"])
    assert exit_.value.code == 2


def test_dry_run_and_paid_cannot_be_combined():
    with pytest.raises(SystemExit):
        run(ONE + ["--batch-id", "b1", "--dry-run", "--paid"])


# --- Dry run ---------------------------------------------------------------------------


def test_a_dry_run_shows_cells_and_worst_case_and_sends_nothing(tmp_path):
    code, output = run(ONE + ["--batch-id", "b1", "--dry-run",
                              "--ledger", str(tmp_path / "ledger.jsonl"),
                              "--out", str(tmp_path / "records.jsonl")])
    assert code == 0
    assert "no request is sent" in output.lower()
    for model in MODELS.models:
        assert f"{model.id} example/tiny-task L0A run 1" in output
    # Opus 5.5: (1031 * 4 + 128000 * 20) / 1e6
    assert "$2.5641" in output
    assert "worst case for 8 cells" in output.lower()
    assert "no key" in output.lower()  # keys are reported, not required
    assert not (tmp_path / "records.jsonl").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


@pytest.mark.parametrize("value", [True, False])
def test_a_dry_run_reports_the_flag_of_the_models_file_in_use(tmp_path, value):
    path = models_file(tmp_path, value)
    code, output = run(ONE + ["--batch-id", "b1", "--dry-run", "--models-file",
                              str(path), "--ledger", str(tmp_path / "l.jsonl")])
    assert code == 0
    assert f"confirmed_by_human: {str(value).lower()}" in output


def test_a_dry_run_prints_the_default_ledger_path():
    code, output = run(ONE + ["--batch-id", "b1", "--dry-run", "--models",
                              "claude-haiku-5-5"])
    assert code == 0
    assert str(DEFAULT_PATH) in output and "(default)" in output


def test_a_dry_run_compares_the_worst_case_with_the_caps(tmp_path):
    code, output = run(ONE + ["--batch-id", "b1", "--dry-run", "--batch-cap", "1",
                              "--total-cap", "5", "--models", "claude-opus-5-5",
                              "--ledger", str(tmp_path / "l.jsonl")])
    assert code == 0
    assert "more than the batch cap" in output


# --- Refusals before a paid run ---------------------------------------------------------


def test_a_paid_run_is_refused_while_the_model_list_is_unconfirmed(
        tmp_path, unconfirmed, env):
    argv = paid(tmp_path, unconfirmed)
    code, output = run(argv, environ=env)
    assert code == 2
    assert "confirmed_by_human" in output
    assert not (tmp_path / "ledger.jsonl").exists()


@pytest.mark.parametrize("drop", ["--batch-cap", "--total-cap"])
def test_a_paid_run_needs_both_caps(tmp_path, confirmed, env, drop):
    argv = paid(tmp_path, confirmed)
    index = argv.index(drop)
    del argv[index:index + 2]
    code, output = run(argv, environ=env)
    assert code == 2 and drop in output


def test_a_paid_run_refuses_missing_keys_naming_them(tmp_path, confirmed, env):
    del env["DEEPSEEK_API_KEY"]
    code, output = run(paid(tmp_path, confirmed), environ=env)
    assert code == 2
    assert "DEEPSEEK_API_KEY" in output and "--models" in output


def test_a_key_with_spaces_or_line_breaks_is_refused_without_showing_it(
        tmp_path, confirmed, env):
    name = MODELS.get("gpt-6-luna").api_key_env
    env[name] = "fake-openai-" + "q" * 20 + "\nextra"
    code, output = run(paid(tmp_path, confirmed), environ=env)
    assert code == 2
    assert name in output and "q" * 20 not in output


@pytest.mark.parametrize("args,message", [
    (["--models", "nope-1"], "nope-1"),
    (["--levels", "L9"], "L9"),
    (["--wordings", "C"], "C"),
    (["--runs", "0"], "runs"),
    (["--rerun", "ok"], "ok"),
    (["--rpm", "anthropic"], "PROVIDER=N"),
    (["--rpm", "anthropic=-3"], "anthropic"),
    (["--workers", "0"], "workers"),
    (["--max-attempts", "0"], "max_attempts"),
    (["--read-timeout", "0"], "--read-timeout"),
    (["--max-consecutive-429", "0"], "--max-consecutive-429"),
    (["--total-timeout", "inf"], "--total-timeout"),
])
def test_bad_options_are_refused(tmp_path, confirmed, env, args, message):
    code, output = run(paid(tmp_path, confirmed, *args), environ=env)
    assert code == 2 and message in output


@pytest.mark.parametrize("batch", ["has space", "../up", "a/b", ""])
def test_a_batch_id_must_be_safe_for_a_folder_name(tmp_path, env, batch):
    code, output = run(ONE + ["--batch-id", batch, "--dry-run"], environ=env)
    assert code == 2 and "batch" in output


# --- Paid runs (fake transport) -----------------------------------------------------------


def test_a_paid_run_writes_a_valid_record_for_every_model(tmp_path, confirmed, env):
    transport = FakeTransport(good)
    code, output = run(paid(tmp_path, confirmed), transport, env)
    assert code == 0, output
    found = read_records(tmp_path / "out" / "records.jsonl")
    assert found.ok and len(found.records) == len(MODELS.models)
    assert all(validate_record(r) == [] and r["status"] == "ok"
               for r in found.records)
    assert len(transport.requests) == len(MODELS.models)
    assert "new to the ledger" in output
    assert str(tmp_path / "ledger.jsonl") in output
    entries = read_ledger(tmp_path / "ledger.jsonl").entries
    assert len(entries) == 2 * len(MODELS.models)
    for value in env.values():
        assert value not in output


def test_a_second_run_of_the_batch_skips_done_cells_and_does_not_warn(
        tmp_path, confirmed, env):
    run(paid(tmp_path, confirmed), FakeTransport(good), env)
    transport = FakeTransport(no_network)
    code, output = run(paid(tmp_path, confirmed), transport, env)
    assert code == 0
    assert "new to the ledger" not in output
    assert "8 of 8 cells already done" in output
    assert transport.requests == []


def test_a_record_file_in_use_by_another_run_is_refused(tmp_path, confirmed, env):
    from runner.ledger import _lock, _unlock
    out = tmp_path / "out" / "records.jsonl"
    out.parent.mkdir(parents=True)
    handle = _lock(out.with_name(out.name + ".lock"))
    try:
        code, output = run(paid(tmp_path, confirmed), FakeTransport(no_network), env)
    finally:
        _unlock(handle)
    assert code == 2 and "in use by another run" in output


def test_the_budget_stop_has_its_own_exit_code(tmp_path, confirmed, env):
    argv = paid(tmp_path, confirmed, "--models", "claude-opus-5-5")
    argv[argv.index("--batch-cap") + 1] = "1"
    code, output = run(argv, FakeTransport(good), env)
    assert code == 3
    assert "cap" in output
    assert not (tmp_path / "out" / "records.jsonl").exists()


def test_failed_cells_give_exit_code_1(tmp_path, confirmed, env):
    from fakes import error_response
    transport = FakeTransport(lambda r, n: error_response(
        400, {"type": "invalid_request_error", "message": "bad"}))
    code, output = run(paid(tmp_path, confirmed, "--models", "claude-haiku-5-5"),
                       transport, env)
    assert code == 1
    assert "failed 1" in output


def test_models_can_be_chosen_by_id_or_as_the_pilot(tmp_path, confirmed, env):
    transport = FakeTransport(good)
    code, _ = run(paid(tmp_path, confirmed, "--models", "pilot"), transport, env)
    assert code == 0
    sent = sorted(json.loads(r.body)["model"] for r in transport.requests)
    assert sent == sorted(MODELS.pilot)


def test_the_anthropic_workspace_id_comes_from_the_environment(tmp_path, confirmed, env):
    env["ANTHROPIC_WORKSPACE_ID"] = "wrkspc_test"
    transport = FakeTransport(lambda r, n: anthropic_stream(model="claude-haiku-5-5"))
    code, _ = run(paid(tmp_path, confirmed, "--models", "claude-haiku-5-5"),
                  transport, env)
    assert code == 0
    assert transport.requests[0].headers["anthropic-workspace-id"] == "wrkspc_test"


def test_the_429_limit_reaches_the_run(tmp_path, confirmed, env):
    from fakes import error_response
    transport = FakeTransport(lambda r, n: error_response(
        429, {"code": "too_many_requests", "message": "daily quota"}))
    argv = paid(tmp_path, confirmed, "--models", "gemini-4-hydrogen", "--runs", "3",
                "--max-consecutive-429", "2", "--max-attempts", "4")
    code, output = run(argv, transport, env)
    assert code == 1
    assert len(transport.requests) == 2
    assert "2 HTTP 429 answers in a row" in output


def test_the_confirmed_flag_is_read_from_the_models_file(confirmed):
    assert yaml.safe_load(confirmed.read_text(encoding="utf-8"))["confirmed_by_human"]
