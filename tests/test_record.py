"""The run record format from task T0.4 and its validator."""

import copy
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from runner.record import (
    SCHEMA_VERSION,
    CellKey,
    RecordError,
    append_record,
    build_record,
    cell_key,
    check_files,
    dumps_record,
    file_entry,
    files_dir,
    read_records,
    repair_tail,
    validate_record,
    with_features,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "record-good.json"


@pytest.fixture
def good():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def errors_for(record):
    errors = validate_record(record)
    assert errors, "expected the record to be rejected"
    return "\n".join(errors)


def minimal(**changes):
    fields = dict(
        project_type="website",
        task_id="bakery",
        prompt_set_version="1",
        level="L0",
        wording="A",
        run_index=1,
        prompt_text="Make a website for a bakery.",
        provider="example",
        model_id="example-model-1",
        status="ok",
        raw_response="<html></html>",
    )
    fields.update(changes)
    return build_record(**fields)


# --- The hand-made good record -------------------------------------------


def test_fixture_is_not_under_a_data_directory():
    assert "data" not in FIXTURE.relative_to(ROOT).parts


def test_hand_made_good_record_is_accepted(good):
    assert validate_record(good) == []


def test_schema_version_is_one(good):
    assert SCHEMA_VERSION == 1 == good["schema_version"]


# --- Five (and more) bad records, each rejected for its reason -------------


def test_rejects_unknown_field(good):
    good["temperature"] = 1.0
    assert "unknown field 'temperature'" in errors_for(good)


def test_rejects_missing_field(good):
    del good["prompt_text"]
    assert "missing field 'prompt_text'" in errors_for(good)


@pytest.mark.parametrize(
    "path, value",
    [
        (("tokens", "input"), "14"),
        (("run_index",), 1.0),
        (("run_index",), True),
        (("settings",), []),
        (("files",), {}),
        (("prompt_text",), 7),
        (("cost_usd",), "0.04"),
    ],
)
def test_rejects_wrong_type(good, path, value):
    target = good
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert ".".join(path) + ":" in errors_for(good)


@pytest.mark.parametrize("level", ["L3", "l0", "0", None])
def test_rejects_bad_level(good, level):
    good["level"] = level
    assert "level:" in errors_for(good)


@pytest.mark.parametrize("surface", ["web", "API", "", None])
def test_rejects_bad_surface(good, surface):
    good["surface"] = surface
    assert "surface:" in errors_for(good)


@pytest.mark.parametrize("status", ["done", "OK", "error", None])
def test_rejects_bad_status(good, status):
    good["status"] = status
    assert "status:" in errors_for(good)


@pytest.mark.parametrize("wording", ["C", "a", 1])
def test_rejects_bad_wording(good, wording):
    good["wording"] = wording
    assert "wording:" in errors_for(good)


@pytest.mark.parametrize("source", ["imported", "", None])
def test_rejects_bad_source(good, source):
    good["source"] = source
    assert "source:" in errors_for(good)


def test_rejects_naive_timestamp(good):
    good["timestamp"] = "2026-11-25T14:03:07"
    assert "timestamp: has no time zone" in errors_for(good)


@pytest.mark.parametrize(
    "timestamp, reason",
    [
        ("2026-11-25T15:03:07+01:00", "must be in UTC"),
        ("2026-11-25", "must be an ISO 8601"),
        ("2026-02-30T10:00:00Z", "not a real date"),
        ("yesterday", "must be an ISO 8601"),
    ],
)
def test_rejects_other_bad_timestamps(good, timestamp, reason):
    good["timestamp"] = timestamp
    assert reason in errors_for(good)


@pytest.mark.parametrize("key", ["input", "output", "reasoning"])
def test_rejects_negative_tokens(good, key):
    good["tokens"][key] = -1
    assert f"tokens.{key}: must be a whole number of at least 0" in errors_for(good)


def test_rejects_negative_cost(good):
    good["cost_usd"] = -0.01
    assert "cost_usd:" in errors_for(good)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "C:/Users/x/index.html",
        "C:index.html",
        "\\\\server\\share\\index.html",
        "src\\index.html",
    ],
)
def test_rejects_absolute_or_non_portable_file_path(good, path):
    good["files"][0]["path"] = path
    assert "files[0].path: must be a relative path" in errors_for(good)


@pytest.mark.parametrize("path", ["../index.html", "src/../../x", "a/./b", "a//b", "a/", ""])
def test_rejects_file_path_with_parent_or_empty_parts(good, path):
    good["files"][0]["path"] = path
    assert "files[0].path:" in errors_for(good)


def test_rejects_bad_path_in_check_files(good):
    good["checks"][0]["files"][0]["path"] = "../shot.png"
    assert "checks[0].files[0].path:" in errors_for(good)


@pytest.mark.parametrize("raw", [None, ""])
def test_rejects_ok_record_without_raw_response(good, raw):
    good["raw_response"] = raw
    assert "raw_response: an ok record needs the raw response" in errors_for(good)


def test_returns_all_errors_not_only_the_first(good):
    good["level"] = "L9"
    good["surface"] = "web"
    good["tokens"]["output"] = -5
    good["timestamp"] = "2026-11-25T14:03:07"
    good["bogus"] = 1
    errors = validate_record(good)
    assert len(errors) == 5
    joined = "\n".join(errors)
    for reason in ("level:", "surface:", "tokens.output:", "timestamp:", "'bogus'"):
        assert reason in joined


# --- Further rules ---------------------------------------------------------


def test_rejects_non_object():
    assert validate_record([]) == ["record: must be a JSON object"]


def test_rejects_other_schema_version(good):
    good["schema_version"] = 2
    assert "schema_version: must be 1" in errors_for(good)


def test_rejects_bad_record_id(good):
    good["record_id"] = "not-a-uuid"
    assert "record_id:" in errors_for(good)


def test_rejects_failed_record_without_error(good):
    good["status"] = "failed"
    good["raw_response"] = None
    assert "error: a failed record needs an error message" in errors_for(good)


def test_failed_record_with_error_is_accepted(good):
    good.update(status="failed", raw_response=None, error="HTTP 529 overloaded",
                files=[], checks=[], features=[])
    assert validate_record(good) == []


def test_rejects_ok_record_with_error(good):
    good["error"] = "something"
    assert "error: must be null for an ok record" in errors_for(good)


def test_refused_and_truncated_records_need_no_raw_response(good):
    for status in ("refused", "truncated"):
        record = copy.deepcopy(good)
        record.update(status=status, raw_response=None)
        assert validate_record(record) == []


def test_rejects_controlled_record_off_the_api_surface(good):
    good["surface"] = "product"
    assert "surface: a controlled record must be on the api surface" in errors_for(good)


def test_rejects_controlled_record_with_system_prompt(good):
    good["system_prompt"] = "You are helpful."
    assert "system_prompt: must be null for a controlled record" in errors_for(good)


def test_manual_product_record_is_accepted(good):
    good.update(source="manual", surface="product",
                source_note="typed by hand into a consumer chat product",
                tokens={"input": None, "output": None, "reasoning": None},
                cost_usd=None, settings={})
    assert validate_record(good) == []


def test_uncontrolled_import_may_leave_grid_fields_null(good):
    good.update(source="uncontrolled_import", source_note="historical set v1, id 123",
                surface="product", system_prompt="historical system prompt",
                level=None, wording=None, run_index=None, prompt_set_version=None)
    assert validate_record(good) == []


@pytest.mark.parametrize("key", ["level", "wording", "run_index", "prompt_set_version"])
def test_rejects_null_grid_field_on_controlled_record(good, key):
    good[key] = None
    assert f"{key}:" in errors_for(good)


def test_rejects_run_index_below_one(good):
    good["run_index"] = 0
    assert "run_index:" in errors_for(good)


def test_rejects_unknown_token_key(good):
    good["tokens"]["cached"] = 3
    assert "tokens: unknown field 'cached'" in errors_for(good)


def test_rejects_non_finite_number_in_settings(good):
    good["settings"]["temperature"] = float("nan")
    assert "settings.temperature: must be JSON" in errors_for(good)


def test_rejects_bad_sha256_and_size(good):
    good["files"][0]["sha256"] = "ABC"
    good["files"][0]["size"] = -1
    joined = errors_for(good)
    assert "files[0].sha256:" in joined
    assert "files[0].size:" in joined


def test_rejects_repeated_file_path_across_files_and_checks(good):
    good["checks"][0]["files"][0]["path"] = "index.html"
    assert "repeats the file path 'index.html'" in errors_for(good)


def test_rejects_bad_check_outcome(good):
    good["checks"][0]["outcome"] = "passed"
    assert "checks[0].outcome:" in errors_for(good)


def test_rejects_feature_without_extractor_version(good):
    del good["features"][0]["extractor_version"]
    assert "features[0]: missing field 'extractor_version'" in errors_for(good)


def test_rejects_repeated_feature(good):
    good["features"][1]["name"] = "fonts"
    assert "features[1]: repeats feature 'fonts' from extractor 'website-css'" in errors_for(good)


def test_rejects_two_versions_of_one_extractor(good):
    good["features"][1]["extractor_version"] = "2"
    assert "features[1]: extractor 'website-css' appears with versions" in errors_for(good)


# --- Building records --------------------------------------------------------


def test_build_record_fills_defaults():
    record = minimal()
    assert validate_record(record) == []
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["source"] == "controlled"
    assert record["surface"] == "api"
    assert record["system_prompt"] is None
    assert record["settings"] == {}
    assert record["tokens"] == {"input": None, "output": None, "reasoning": None}
    assert record["files"] == record["checks"] == record["features"] == []
    assert record["timestamp"].endswith("Z")
    assert list(record) == list(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_build_record_gives_each_record_a_new_id():
    assert minimal()["record_id"] != minimal()["record_id"]


def test_build_record_merges_partial_tokens_and_takes_aware_datetime():
    moment = datetime.datetime(2026, 11, 25, 15, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
    record = minimal(tokens={"input": 3, "output": 9}, timestamp=moment)
    assert record["tokens"] == {"input": 3, "output": 9, "reasoning": None}
    assert record["timestamp"] == "2026-11-25T14:00:00.000Z"


def test_build_record_rejects_naive_datetime():
    with pytest.raises(RecordError, match="naive"):
        minimal(timestamp=datetime.datetime(2026, 11, 25, 14, 0))


def test_build_record_raises_with_every_error():
    with pytest.raises(RecordError) as caught:
        minimal(level="L5", surface="web")
    assert len(caught.value.errors) == 2  # cross-field rules skip invalid values
    assert "level:" in str(caught.value)


def test_build_record_copies_its_inputs():
    settings = {"max_tokens": 10}
    record = minimal(settings=settings)
    settings["max_tokens"] = 99
    assert record["settings"] == {"max_tokens": 10}


# --- Cell keys -----------------------------------------------------------------


def test_cell_key(good):
    assert cell_key(good) == CellKey(
        project_type="website", task_id="bakery", level="L0", wording="A",
        model_id="example-model-1", surface="api", run_index=1,
    )


def test_cell_key_ignores_fields_outside_the_cell(good):
    other = copy.deepcopy(good)
    other.update(record_id="00000000-0000-4000-8000-000000000000", status="failed",
                 timestamp="2027-01-01T00:00:00Z")
    assert cell_key(other) == cell_key(good)
    other["run_index"] = 2
    assert cell_key(other) != cell_key(good)


# --- JSON Lines files ----------------------------------------------------------


def test_append_and_read_back(tmp_path, good):
    path = tmp_path / "out" / "runs.jsonl"
    second = minimal(run_index=2)
    append_record(path, good)
    append_record(path, second)
    text = path.read_bytes()
    assert text.count(b"\n") == 2 and text.endswith(b"\n")
    result = read_records(path)
    assert result.records == [good, second]
    assert result.problems == () and result.truncated_tail is None and result.ok


def test_one_line_per_record_even_with_newlines_and_unicode(tmp_path):
    record = minimal(raw_response="line one\nline two\u2028caf\u00e9 \U0001f35e\r\n")
    path = tmp_path / "runs.jsonl"
    append_record(path, record)
    data = path.read_bytes()
    assert data.count(b"\n") == 1
    data.decode("ascii")  # non-ASCII is escaped, so no tool can split a record
    assert read_records(path).records == [record]
    assert dumps_record(record) + "\n" == data.decode("ascii")


def test_append_refuses_invalid_record(tmp_path, good):
    good["level"] = "L7"
    path = tmp_path / "runs.jsonl"
    with pytest.raises(RecordError, match="level:"):
        append_record(path, good)
    assert not path.exists()


def test_read_reports_truncated_last_line(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    append_record(path, good)
    with open(path, "ab") as handle:
        handle.write(dumps_record(minimal(run_index=2)).encode()[:40])
    result = read_records(path)
    assert result.records == [good]
    assert result.problems == ()
    assert result.truncated_tail is not None
    assert result.truncated_tail.line == 2
    assert result.ok  # a truncated tail is tolerated, not an error


def test_unterminated_complete_last_line_still_counts_as_truncated(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    path.write_text(dumps_record(good), encoding="ascii")
    result = read_records(path)
    assert result.records == []
    assert result.truncated_tail.line == 1


def test_append_refuses_after_a_truncated_line_until_repaired(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    append_record(path, good)
    with open(path, "ab") as handle:
        handle.write(b'{"schema_version": 1, "rec')
    with pytest.raises(RecordError, match="repair_tail"):
        append_record(path, minimal())
    assert repair_tail(path) == b'{"schema_version": 1, "rec'
    assert repair_tail(path) is None
    second = minimal(run_index=2)
    append_record(path, second)
    assert read_records(path).records == [good, second]


def test_repair_tail_of_file_with_only_a_partial_line(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_bytes(b'{"sche')
    assert repair_tail(path) == b'{"sche'
    assert path.read_bytes() == b""


def test_read_reports_bad_lines_in_the_middle(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    bad = copy.deepcopy(good)
    bad["record_id"] = "11111111-1111-4111-8111-111111111111"
    bad["surface"] = "web"
    nan = dumps_record(minimal(run_index=3)).replace('"settings":{}', '"settings":{"t":NaN}')
    lines = [
        dumps_record(good),
        "not json",
        json.dumps(bad),
        "",
        dumps_record(good),  # repeated record id
        nan,
        '{"a": 1, "a": 2}',
        "[1, 2]",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = read_records(path)
    assert result.records == [good]
    assert not result.ok
    found = {problem.line: " ".join(problem.errors) for problem in result.problems}
    assert sorted(found) == [2, 3, 4, 5, 6, 7, 8]
    assert "not valid JSON" in found[2]
    assert "surface:" in found[3]
    assert "blank line" in found[4]
    assert "repeats record_id" in found[5] and "line 1" in found[5]
    assert "NaN" in found[6]
    assert "repeated key 'a'" in found[7]
    assert "must be a JSON object" in found[8]


def test_read_of_empty_file(tmp_path):
    path = tmp_path / "runs.jsonl"
    path.write_bytes(b"")
    result = read_records(path)
    assert result.records == [] and result.ok and result.truncated_tail is None


# --- Files on disk -----------------------------------------------------------------


def test_files_dir_is_beside_the_jsonl_file(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    assert files_dir(path, good["record_id"]) == tmp_path / "files" / good["record_id"]
    with pytest.raises(RecordError):
        files_dir(path, "../escape")


def test_file_entry_and_check_files(tmp_path):
    directory = tmp_path / "files" / "x"
    (directory / "src").mkdir(parents=True)
    content = b"<!doctype html>\n"
    (directory / "src" / "index.html").write_bytes(content)
    entry = file_entry(directory, "src/index.html")
    assert entry == {
        "path": "src/index.html",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }
    record = minimal(files=[entry])
    assert check_files(record, directory) == []

    (directory / "src" / "index.html").write_bytes(b"changed!!!!!!!!!")
    problems = check_files(record, directory)
    assert len(problems) == 1 and "sha256 does not match" in problems[0]

    (directory / "src" / "index.html").unlink()
    assert "is missing" in check_files(record, directory)[0]


def test_file_entry_refuses_bad_path(tmp_path):
    with pytest.raises(RecordError, match="relative path"):
        file_entry(tmp_path, "/etc/passwd")
    with pytest.raises(RecordError):
        file_entry(tmp_path, "../x")


# --- Building on features ---------------------------------------------------------


def test_with_features_replaces_one_extractors_entries(good):
    updated = with_features(good, "website-css", "2", {"fonts": ["Inter"], "radius_px": 8})
    assert good["features"][0]["value"] == ["system-ui"]  # original untouched
    assert updated["features"] == [
        {"name": "fonts", "value": ["Inter"], "extractor": "website-css", "extractor_version": "2"},
        {"name": "radius_px", "value": 8, "extractor": "website-css", "extractor_version": "2"},
    ]
    both = with_features(updated, "website-html", "1", {"headings": 3})
    assert len(both["features"]) == 3
    assert validate_record(both) == []


def test_with_features_validates(good):
    with pytest.raises(RecordError, match="features"):
        with_features(good, "Bad Name", "1", {"x": 1})


# --- Command line ------------------------------------------------------------------


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "runner.record", *map(str, args)],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_cli_accepts_a_valid_file(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    append_record(path, good)
    result = run_cli(path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 valid record" in result.stdout


def test_cli_rejects_a_bad_file(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    append_record(path, good)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("garbage\n")
    result = run_cli(path)
    assert result.returncode == 1
    assert "line 2" in result.stdout


def test_cli_checks_files_on_disk_when_asked(tmp_path, good):
    path = tmp_path / "runs.jsonl"
    append_record(path, good)
    result = run_cli("--files", path)
    assert result.returncode == 1
    assert "index.html is missing" in result.stdout
