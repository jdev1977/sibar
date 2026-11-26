"""Sandbox checks stored in run records, and the sandbox's command line (T2.7)."""

import json

import pytest

from runner.files import save_files
from runner.ledger import lock_file, unlock_file
from runner.record import append_record, build_record, files_dir, read_records
from sandbox.__main__ import main
from sandbox.records import RunRefused, make_check, run_directory, run_file
from sandbox.run import Settings

CODE = "```python main.py\nprint('hi')\n```\n"


def add(path, text=CODE, **fields):
    values = dict(project_type="pipeline", task_id="log-aggregation", prompt_text="p",
                  provider="anthropic", model_id="m", status="ok", level="L2",
                  wording="A", run_index=1, prompt_set_version="1", raw_response=text)
    values.update(fields)
    record = build_record(**values)
    if text:
        record["files"] = save_files(files_dir(path, record["record_id"]), text)
    append_record(path, record)
    return record


class FakeRun:
    """Stands in for run_folder: notes its calls and answers ``result``."""

    def __init__(self, result="ran", error=None):
        self.calls, self.result, self.error = [], result, error

    def __call__(self, root, paths, settings):
        self.calls.append((root, paths, settings))
        if self.error:
            raise self.error
        return {"result": self.result, "reason": None, "files": len(paths or [])}


def checks(path):
    found = read_records(path)
    assert found.ok and not found.truncated_tail
    return [record["checks"] for record in found.records]


def test_the_check_is_stored_with_the_records_task(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    fake = FakeRun()
    said = []
    counts = run_file(path, run=fake, say=said.append)
    assert counts == {"ran": 1}
    root, paths, settings = fake.calls[0]
    assert root == files_dir(path, record["record_id"]) / "extracted"
    assert paths == ["main.py"]
    assert settings.task == ("pipeline", "log-aggregation", "L2")
    (check,), = checks(path)
    assert check["name"] == "sandbox" and check["tool"] == "sandbox"
    assert check["outcome"] == "ok" and check["files"] == []
    assert said == [f"{record['record_id']}: ran"]


def test_only_code_types_are_run_by_default(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path, project_type="website", task_id="bakery-landing")
    add(path, status="failed", raw_response=None, text=None, error="x")
    add(path, project_type="math", task_id="loan-amortization")
    fake = FakeRun()
    assert run_file(path, run=fake, say=lambda _: None) == {"ran": 1}


def test_done_records_are_skipped_unless_forced_and_errors_are_redone(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    run_file(path, run=FakeRun("failed"), say=lambda _: None)
    assert run_file(path, run=FakeRun(), say=lambda _: None) == {"skipped": 1}
    assert run_file(path, run=FakeRun(), force=True, say=lambda _: None) == {"ran": 1}
    run_file(path, run=FakeRun("error"), force=True, say=lambda _: None)
    assert run_file(path, run=FakeRun(), say=lambda _: None) == {"ran": 1}
    (only,), = checks(path)  # replaced each time, never added
    assert only["detail"]["result"] == "ran"


def test_a_record_with_changed_files_gets_an_error_and_is_not_run(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    (files_dir(path, record["record_id"]) / "extracted" / "main.py").write_text("changed")
    fake = FakeRun()
    run_file(path, run=fake, say=lambda _: None)
    assert fake.calls == []
    (check,), = checks(path)
    assert check["outcome"] == "error" and "main.py" in check["detail"]["reason"]


def test_a_failing_record_does_not_end_the_batch(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    add(path)
    counts = run_file(path, run=FakeRun(error=RuntimeError("boom")), say=lambda _: None)
    assert counts == {"error": 2}


def test_a_busy_record_file_is_refused(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    lock = lock_file(path.with_name(path.name + ".lock"))
    try:
        with pytest.raises(RunRefused, match="in use"):
            run_file(path, run=FakeRun(), say=lambda _: None)
    finally:
        unlock_file(lock)


def test_check_outcome_follows_the_tests(tmp_path):
    assert make_check({"result": "ran", "tests": {"ran": True, "failed": 2,
                                                  "exit_code": 1}})["outcome"] == "failed"


def test_a_directory_result_is_written_beside_it(tmp_path):
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "main.py").write_text("print(1)")
    with pytest.raises(RunRefused, match="inside"):
        run_directory(folder, folder / "result.json", run=FakeRun())
    check = run_directory(folder, tmp_path / "result.json", run=FakeRun())
    assert json.loads((tmp_path / "result.json").read_text()) == check


def test_command_line_runs_a_folder(tmp_path, capsys, monkeypatch):
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "main.py").write_text("print(1)")
    calls = []

    def fake(root, paths, settings):
        calls.append(settings)
        return {"result": "ran", "reason": None}

    monkeypatch.setattr("sandbox.records.run_folder", fake)
    monkeypatch.setattr("sandbox.records.run_directory.__defaults__",
                        (Settings(), fake))
    code = main(["run", "--dir", str(folder), "--task", "pipeline/log-aggregation/L2",
                 "--memory-mb", "256", "--command", "python main.py --x 1"])
    assert code == 0
    settings = calls[0]
    assert settings.task == ("pipeline", "log-aggregation", "L2")
    assert settings.limits.memory_mb == 256
    assert settings.command == ("python", "main.py", "--x", "1")
    assert (tmp_path / "out-sandbox.json").exists()
    assert capsys.readouterr().out.startswith("ran")


def test_command_line_refuses_bad_options(tmp_path, capsys):
    assert main(["run", "--dir", str(tmp_path), "--memory-mb", "0"]) == 2
    assert main(["run", "--dir", str(tmp_path), "--task", "pipeline"]) == 2
    with pytest.raises(SystemExit):
        main(["run", "--records", str(tmp_path / "r.jsonl"), "--task", "a/b/c"])


@pytest.mark.sandbox
def test_a_record_runs_in_the_real_sandbox(tmp_path):
    from sandbox_support import require_runtime

    require_runtime()
    path = tmp_path / "records.jsonl"
    text = ("```python validate.py\nimport sys\nprint(open(sys.argv[1] + '/OV-014.jsonl')"
            ".read().count(chr(10)))\n```\n")
    add(path, text=text, task_id="data-validation")
    counts = run_file(path, say=lambda _: None)
    assert counts == {"ran": 1}
    (check,), = checks(path)  # read_records validated the record
    detail = check["detail"]
    assert detail["entry"]["stdout"].strip() == "2"
    assert detail["task"]["rejects_files"] == []
    assert check["outcome"] == "ok"
