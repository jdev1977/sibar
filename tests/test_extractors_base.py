"""The extractor interface, registry and command line (T1.4)."""

import json

import pytest

from extractors import base
from extractors.__main__ import main
from extractors.base import Extractor, Inputs, InputFile, run_extractor, run_extractors
from extractors.records import ExtractRefused, extract_file, extract_record
from extractors.registry import all_extractors, extractors_for
from runner.files import save_files
from runner.record import (
    append_record, build_record, files_dir, read_records, validate_record,
)

PAGE = ("```html index.html\n<!doctype html><html lang=\"en\"><head>"
        "<style>body{color:#336699}</style></head><body><h1>Hi</h1></body></html>\n"
        "```\n")


def add(path, text=PAGE, **fields):
    values = dict(project_type="website", task_id="bakery-landing", prompt_text="p",
                  provider="anthropic", model_id="m", status="ok", level="L0",
                  wording="A", run_index=1, prompt_set_version="1", raw_response=text)
    values.update(fields)
    record = build_record(**values)
    if text and "```" in text:
        record["files"] = save_files(files_dir(path, record["record_id"]), text)
    append_record(path, record)
    return record


def counting(name="test.count", version="1"):
    return Extractor(name=name, version=version, project_type="website",
                     extract=lambda inputs: {"files": len(inputs.files)})


def failing(inputs):
    raise ValueError("boom at C:\\Users\\someone\\x")


# --- Inputs ------------------------------------------------------------------


def test_inputs_from_a_directory_are_sorted_and_relative(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "z.css").write_text("a{}")
    (tmp_path / "a.html").write_text("<p>")
    inputs = Inputs.from_directory(tmp_path)
    assert [f.path for f in inputs.files] == ["a.html", "b/z.css"]
    assert inputs.files[0].text == "<p>"
    assert inputs.files[1].suffix == "css"
    assert inputs.skipped == ()


def test_large_files_and_too_many_files_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "MAX_FILE_BYTES", 10)
    monkeypatch.setattr(base, "MAX_FILES", 2)
    (tmp_path / "a.html").write_text("x" * 11)
    (tmp_path / "b.css").write_text("ok")
    (tmp_path / "c.js").write_text("ok")
    (tmp_path / "d.js").write_text("ok")
    inputs = Inputs.from_directory(tmp_path)
    assert [f.path for f in inputs.files] == ["b.css", "c.js"]
    assert inputs.skipped == (("a.html", "too large"), ("d.js", "too many files"))


def test_total_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "MAX_TOTAL_BYTES", 5)
    (tmp_path / "a.css").write_text("abc")
    (tmp_path / "b.css").write_text("abc")
    inputs = Inputs.from_directory(tmp_path)
    assert [f.path for f in inputs.files] == ["a.css"]
    assert inputs.skipped == (("b.css", "total size limit"),)


def test_bad_bytes_decode_with_replacement():
    file = InputFile("a.html", b"caf\xe9 \xff")
    assert file.text == "caf\ufffd \ufffd"


def test_inputs_from_a_record_strip_the_extracted_prefix(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    inputs = Inputs.from_record(record, path)
    assert [f.path for f in inputs.files] == ["index.html"]
    assert inputs.record["record_id"] == record["record_id"]


def test_a_changed_or_missing_file_is_skipped(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    stored = files_dir(path, record["record_id"]) / "extracted" / "index.html"
    stored.write_text("changed")
    assert Inputs.from_record(record, path).skipped == (("index.html", "changed"),)
    stored.unlink()
    assert Inputs.from_record(record, path).skipped == (("index.html", "missing"),)


def test_the_cache_builds_once():
    inputs = Inputs([])
    calls = []
    assert inputs.cached("k", lambda: calls.append(1) or 5) == 5
    assert inputs.cached("k", lambda: calls.append(1) or 6) == 5
    assert calls == [1]


# --- Running -------------------------------------------------------------------


def test_values_are_sorted_with_a_status():
    extractor = Extractor("test.x", "1", "website",
                          lambda inputs: {"zeta": 1, "alpha": [2]})
    assert list(run_extractor(extractor, Inputs([])).items()) == [
        ("alpha", [2]), ("status", "ok"), ("zeta", 1)]


def test_a_failing_extractor_records_an_error_and_others_still_run():
    results = run_extractors(
        [Extractor("test.bad", "2", "website", failing), counting()],
        Inputs([InputFile("a.html", b"")]))
    assert results["test.bad"] == ("2", {"error": "ValueError: boom at <path>",
                                         "status": "error"})
    assert results["test.count"] == ("1", {"files": 1, "status": "ok"})


@pytest.mark.parametrize("values", [
    {"Bad Name": 1}, {"x": float("nan")}, {"x": {1, 2}}, "not a mapping",
])
def test_values_that_are_not_countable_json_are_an_error(values):
    extractor = Extractor("test.x", "1", "website", lambda inputs: values)
    result = run_extractor(extractor, Inputs([]))
    assert result["status"] == "error"


def test_skipped_input_makes_a_result_partial():
    inputs = Inputs([InputFile("a.html", b"")], skipped=[("b.css", "too large")])
    assert run_extractor(counting(), inputs) == {
        "files": 1, "skipped_files": 1, "status": "partial"}


def test_an_extractor_may_report_no_input():
    extractor = Extractor("test.x", "1", "website",
                          lambda inputs: {"status": "no-input"})
    assert run_extractor(extractor, Inputs([])) == {"status": "no-input"}


def test_an_unknown_status_is_an_error():
    extractor = Extractor("test.x", "1", "website", lambda inputs: {"status": "meh"})
    assert run_extractor(extractor, Inputs([]))["status"] == "error"


def test_extractor_names_and_versions_are_checked():
    with pytest.raises(ValueError):
        Extractor("Bad Name", "1", "website", failing)
    with pytest.raises(ValueError):
        Extractor("ok", "1 2", "website", failing)
    with pytest.raises(ValueError):
        Extractor("ok", "1", "Web Site", failing)


# --- Registry ------------------------------------------------------------------


WEBSITE = {
    "website.palette", "website.fonts", "website.libraries", "website.layout",
    "website.corners-shadows", "website.gradients", "website.icons-emoji",
    "website.stock-phrases", "website.file-structure", "website.responsiveness",
    "website.dark-mode", "website.accessibility",
}


def test_the_registry_holds_the_twelve_website_extractors():
    names = [extractor.name for extractor in extractors_for("website")]
    assert set(names) == WEBSITE and len(names) == 12
    assert len({e.name for e in all_extractors()}) == len(all_extractors())
    assert extractors_for("no-such-type") == ()


# --- Records and the command line ------------------------------------------------


def test_extract_record_adds_every_extractor(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    updated = extract_record(record, path, [counting(), Extractor(
        "test.bad", "1", "website", failing)])
    assert validate_record(updated) == []
    assert updated["extractors"] == [
        {"extractor": "test.count", "extractor_version": "1"},
        {"extractor": "test.bad", "extractor_version": "1"}]
    names = {(f["extractor"], f["name"]): f["value"] for f in updated["features"]}
    assert names[("test.count", "files")] == 1
    assert names[("test.bad", "status")] == "error"


def test_extract_file_runs_website_records_and_is_deterministic(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    add(path, status="failed", raw_response=None, error="no", text=None)
    add(path, project_type="pipeline", task_id="csv-clean")
    said = []
    counts = extract_file(path, say=said.append)
    assert counts["records"] == 1 and counts["error"] == 0
    first = path.read_bytes()
    extract_file(path, say=said.append)
    assert path.read_bytes() == first
    records = read_records(path).records
    assert {e["extractor"] for e in records[0]["extractors"]} == WEBSITE
    assert records[1]["extractors"] == [] and records[2]["extractors"] == []


def test_extract_file_with_only_runs_named_extractors(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    extract_file(path, only=["website.palette"], say=lambda text: None)
    record = read_records(path).records[0]
    assert record["extractors"] == [
        {"extractor": "website.palette",
         "extractor_version": extractors_by_name()["website.palette"].version}]


def extractors_by_name():
    return {e.name: e for e in all_extractors()}


def test_extract_file_refuses_unknown_names_and_bad_files(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    with pytest.raises(ExtractRefused):
        extract_file(path, only=["nope"])
    with pytest.raises(ExtractRefused):
        extract_file(path, record_ids=["0" * 8 + "-0000-4000-8000-" + "0" * 12])
    with open(path, "ab") as handle:
        handle.write(b"{bad}\n")
    with pytest.raises(ExtractRefused):
        extract_file(path)
    with pytest.raises(ExtractRefused):
        extract_file(tmp_path / "missing.jsonl")


def test_command_line_on_records_and_on_a_directory(tmp_path, capsys):
    path = tmp_path / "records.jsonl"
    add(path)
    assert main(["--records", str(path)]) == 0
    assert "1 records" in capsys.readouterr().out
    page = tmp_path / "page"
    page.mkdir()
    (page / "index.html").write_text("<style>a{color:red}</style>")
    assert main(["--dir", str(page), "--only", "website.palette"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["website.palette"]["values"]["colors"] == ["#ff0000"]
    assert main(["--list"]) == 0
    assert "website.fonts" in capsys.readouterr().out
    assert main(["--records", str(tmp_path / "none.jsonl")]) == 2
