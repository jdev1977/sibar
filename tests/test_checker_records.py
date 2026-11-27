"""The ``checker`` check entry of a run record and the command line (T2.10)."""

import json

import pytest

from checker.__main__ import main
from checker.records import CHECK, run_file
from runner.record import (append_record, build_record, file_entry, files_dir,
                           read_records, validate_record)

RIGHT = "Monthly payment: $178.21\nTotal interest: $1,692.65\n"


def record(text=RIGHT, task="loan-amortization", level="L0", **fields):
    values = dict(project_type="math", task_id=task, prompt_text="p", provider="x",
                  model_id="m", status="ok", level=level, wording="A", run_index=1,
                  prompt_set_version="1", raw_response=text)
    values.update(fields)
    return build_record(**values)


def written(tmp_path, *records):
    path = tmp_path / "records.jsonl"
    for item in records:
        append_record(path, item)
    return path


def checks(path):
    found = read_records(path)
    assert not found.problems
    return {r["record_id"]: [c for c in r["checks"] if c["name"] == CHECK]
            for r in found.records}


def test_a_record_gets_one_checker_entry(tmp_path):
    other = {"name": "render", "tool": "renderer", "tool_version": "1",
             "outcome": "ok", "detail": {}, "files": []}
    item = record(checks=[other])
    path = written(tmp_path, item)
    counts = run_file(path)
    assert counts == {"correct": 1}
    [entry] = checks(path)[item["record_id"]]
    assert entry["outcome"] == "ok"
    assert entry["detail"]["verdict"] == "correct"
    assert entry["detail"]["task"] == "math/loan-amortization"
    assert len(entry["detail"]["reference_sha256"]) == 64
    after = read_records(path).records[0]
    assert [c["name"] for c in after["checks"]] == ["render", CHECK]
    assert validate_record(after) == []
    first = path.read_bytes()
    run_file(path)                               # replaced, and byte for byte
    assert path.read_bytes() == first


def test_only_math_and_engineering_answers_are_checked(tmp_path):
    website = record(project_type="website", task="landing")
    failed = record(status="failed", error="x", raw_response=None)
    path = written(tmp_path, website, failed)
    assert run_file(path) == {}
    assert all(not found for found in checks(path).values())


@pytest.mark.parametrize("fields,reason", [
    ({"task": "unknown-task"}, "no reference"),
    ({"prompt_set_version": "2"}, "prompt set version"),
    ({"level": None, "wording": None, "run_index": None, "prompt_set_version": None,
      "source": "uncontrolled_import"}, "level"),
])
def test_what_cannot_be_graded_is_an_error_entry(tmp_path, fields, reason):
    item = record(**fields)
    path = written(tmp_path, item)
    assert run_file(path) == {"error": 1}
    [entry] = checks(path)[item["record_id"]]
    assert entry["outcome"] == "error"
    assert reason in entry["detail"]["reason"]


def test_supplied_answers_override_the_found_ones(tmp_path):
    item = record("Monthly payment: $202.50\n")
    path = written(tmp_path, item)
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        f"record_id: {item['record_id']}\nquantities:\n"
        "  monthly_payment: {value: 178.21, unit: USD}\n"
        "  total_interest: {value: 1692.65, unit: USD}\n", encoding="utf-8")
    assert run_file(path, answers_path=answers) == {"correct": 1}
    [entry] = checks(path)[item["record_id"]]
    assert entry["detail"]["answers_from"] == ["extracted", "supplied"]
    assert run_file(path) == {"suspected_wrong": 1}
    assert run_file(path, answers_path=answers, extract=False) == {"correct": 1}


def test_a_suspected_answer_is_counted_apart_until_a_reader_rules(tmp_path, capsys):
    item = record("Monthly payment: $202.50\nTotal interest: $1,692.65\n")
    path = written(tmp_path, item)
    assert main(["--records", str(path)]) == 0
    out = capsys.readouterr().out
    assert "suspected_wrong 1" in out and "review" in out
    assert "correct" not in out.replace("suspected_wrong", "")
    [entry] = checks(path)[item["record_id"]]
    assert entry["detail"]["verdict"] == "suspected_wrong"
    answers = tmp_path / "answers.yaml"
    for ruling, verdict in (("confirmed", "wrong"), ("rejected", "could_not_determine")):
        answers.write_text(f"record_id: {item['record_id']}\n"
                           f"review: {{monthly_payment: {ruling}}}\n", encoding="utf-8")
        assert run_file(path, answers_path=answers) == {verdict: 1}


def test_a_named_markdown_file_of_the_output_is_read(tmp_path):
    item = record("The answer is in the file.", record_id=None)
    path = tmp_path / "records.jsonl"
    directory = files_dir(path, item["record_id"]) / "extracted"
    directory.mkdir(parents=True)
    (directory / "answer.md").write_text(RIGHT, encoding="utf-8")
    item["files"] = [file_entry(directory.parent, "extracted/answer.md")]
    append_record(path, item)
    assert run_file(path) == {"correct": 1}


def test_a_truncated_record_is_never_wrong(tmp_path):
    item = record("Monthly payment: $202.50", status="truncated")
    path = written(tmp_path, item)
    assert run_file(path) == {"suspected_wrong": 1}


@pytest.mark.parametrize("text", [
    "record_id: nobody\nquantities: {}\n",
    "quantities: {nonsense: {value: 1}}\n",
    "a: &x [1]\nb: *x\n",
    "quantities: [",
])
def test_a_bad_answers_file_writes_nothing(tmp_path, text, capsys):
    path = written(tmp_path, record())
    before = path.read_bytes()
    answers = tmp_path / "answers.yaml"
    answers.write_text(text, encoding="utf-8")
    assert main(["--records", str(path), "--answers", str(answers)]) == 2
    assert path.read_bytes() == before
    assert "refused" in capsys.readouterr().out


def test_an_answers_file_without_a_record_id_needs_one_record(tmp_path):
    first, second = record(), record(run_index=2)
    path = written(tmp_path, first, second)
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"quantities": {}, "complete": True}))
    assert main(["--records", str(path), "--answers", str(answers)]) == 2
    assert main(["--records", str(path), "--answers", str(answers),
                 "--record-id", first["record_id"]]) == 0
    assert checks(path)[first["record_id"]][0]["detail"]["verdict"] == "incomplete"
    assert not checks(path)[second["record_id"]]


def test_one_response_on_the_command_line(tmp_path, capsys):
    response = tmp_path / "response.md"
    response.write_text(RIGHT, encoding="utf-8")
    assert main(["--task", "math/loan-amortization", "--level", "L0",
                 "--response", str(response)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["verdict"] == "correct"


def test_an_engineering_result_carries_the_study_note(tmp_path, capsys):
    answers = tmp_path / "answers.yaml"
    answers.write_text("complete: true\n", encoding="utf-8")
    assert main(["--task", "engineering/heat-sink", "--level", "L2",
                 "--answers", str(answers)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert "not a design" in shown["study_data_note"]
    assert shown["verdict"] == "incomplete"


@pytest.mark.parametrize("arguments", [
    ["--task", "math/none", "--level", "L0", "--answers", "x"],
    ["--task", "math/loan-amortization", "--level", "L0"],
    ["--task", "../references/math/loan-amortization", "--level", "L0",
     "--response", "x"],
    ["--records", "no-such-file.jsonl"],
])
def test_refusals(arguments):
    assert main(arguments) == 2
