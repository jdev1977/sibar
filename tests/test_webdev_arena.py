"""The WebDev Arena importer (T5.2). Every row here is invented for the test;
nothing comes from the dataset."""

import json

import pytest

from analysis import runs, spec as analysis_spec
from importers import webdev_arena as wa
from runner.record import check_files, files_dir, read_records

EPOCH = 1736942400.5  # 2025-01-15T12:00:00.500Z
PAGE = "<!DOCTYPE html>\n<html><body><h1>Invented page</h1></body></html>"


def turn(role, content):
    return {"role": role, "content": content}


def structured(path="app/page.tsx", code="export default () => <main>x</main>"):
    return json.dumps({"title": "Invented", "file_path": path, "code": code})


def row(question_id="q-1", **changes):
    base = {
        "question_id": question_id,
        "tstamp": EPOCH,
        "model_a": "claude-invented-1",
        "model_b": "mystery-model",
        "conversation_a": [turn("user", "Make an invented page."),
                           turn("assistant", structured())],
        "conversation_b": [turn("user", "Make an invented page."),
                           turn("assistant", f"```html\n{PAGE}\n```")],
        "winner": "model_a",
        "anony": True,
    }
    base.update(changes)
    return base


def write_array(path, rows):
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return path


def run(tmp_path, rows, **options):
    source = write_array(tmp_path / "in.json", rows)
    out = tmp_path / "out" / "arena.jsonl"
    counts = wa.import_file(source, out, revision="rev-test", **options)
    records = read_records(out)
    assert records.ok
    return counts, records.records, out


def test_imported_records_validate_and_carry_the_source_flag(tmp_path):
    counts, records, out = run(tmp_path, [row()])
    assert counts.rows == 1 and counts.records == 2
    for record in records:
        assert record["source"] == "uncontrolled_import"
        assert "lmarena-ai/webdev-arena-preference-10k" in record["source_note"]
        assert "rev-test" in record["source_note"]
        assert "q-1" in record["source_note"]
        assert record["project_type"] == "website"
        assert record["timestamp"] == "2025-01-15T12:00:00.500Z"
        assert record["surface"] == "product"
        assert record["status"] == "ok"
        assert check_files(record, files_dir(out, record["record_id"])) == []
    a, b = records
    assert a["model_id"] == "claude-invented-1"
    assert a["provider"] == "anthropic"
    assert b["provider"] == "unknown"
    assert a["raw_response"] == structured()


def test_fields_the_source_does_not_give_are_null(tmp_path):
    _, records, _ = run(tmp_path, [row()])
    record = records[0]
    for name in ("batch_id", "prompt_set_version", "level", "wording",
                 "run_index", "gateway", "model_id_returned", "system_prompt",
                 "cost_usd", "stop_reason", "request_id"):
        assert record[name] is None, name
    assert record["tokens"] == {"input": None, "output": None, "reasoning": None}
    assert record["settings"] == {}
    assert record["features"] == [] and record["checks"] == []
    assert "null" in record["source_note"]


def test_structured_and_text_responses_give_files(tmp_path):
    _, records, out = run(tmp_path, [row()])
    a, b = records
    assert [f["path"] for f in a["files"]] == ["extracted/app/page.tsx"]
    assert [f["path"] for f in b["files"]] == ["extracted/block-01.html"]
    written = files_dir(out, a["record_id"]) / "extracted/app/page.tsx"
    assert written.read_text(encoding="utf-8") == "export default () => <main>x</main>"


@pytest.mark.parametrize("name", ["../../../escape.html", "C:\\Windows\\evil.html",
                                  "/etc/passwd", "CON", "..", "a" * 600])
def test_hostile_file_names_stay_inside(tmp_path, name):
    conversation = [turn("user", "p"), turn("assistant", structured(name, "body"))]
    _, records, out = run(tmp_path, [row(conversation_a=conversation)])
    record = records[0]
    assert len(record["files"]) == 1
    assert record["files"][0]["path"].startswith("extracted/")
    assert check_files(record, files_dir(out, record["record_id"])) == []
    allowed = [files_dir(out, r["record_id"]) / "extracted" for r in records]
    written = [path for path in tmp_path.rglob("*")
               if path.is_file() and path not in (tmp_path / "in.json", out)]
    assert len(written) == 2
    assert all(any(path.is_relative_to(a) for a in allowed) for path in written)


def test_only_the_first_turn_is_taken_and_noted(tmp_path):
    conversation = [turn("system", "Invented system text."), turn("user", "first"),
                    turn("assistant", "one"), turn("user", "again"),
                    turn("assistant", "two")]
    _, records, _ = run(tmp_path, [row(conversation_a=conversation)])
    record = records[0]
    assert record["prompt_text"] == "first"
    assert record["raw_response"] == "one"
    assert record["system_prompt"] == "Invented system text."
    assert "first of 2 user turns" in record["source_note"]


def test_text_parts_are_joined_and_other_prompt_parts_noted(tmp_path):
    conversation = [
        turn("user", [{"type": "text", "text": "Copy this "},
                      {"type": "image_url", "image_url": {"url": "x"}},
                      {"type": "text", "text": "design."}]),
        turn("assistant", [{"type": "text", "text": "done"}])]
    _, records, _ = run(tmp_path, [row(conversation_a=conversation)])
    assert records[0]["prompt_text"] == "Copy this design."
    assert records[0]["raw_response"] == "done"
    assert "1 non-text prompt part" in records[0]["source_note"]


@pytest.mark.parametrize("changes, reason", [
    ({"question_id": None}, "no question_id"),
    ({"tstamp": None}, "no usable tstamp"),
    ({"tstamp": 1736942400500}, "no usable tstamp"),  # milliseconds: not guessed
    ({"tstamp": "2025-01-15T12:00:00"}, "no usable tstamp"),  # no time zone
    ({"tstamp": True}, "no usable tstamp"),
])
def test_malformed_rows_are_skipped_with_counts(tmp_path, changes, reason):
    counts, records, _ = run(tmp_path, [row(**changes), row("q-2")])
    assert counts.rows == 2 and counts.records == 2
    assert counts.skipped_rows == {reason: 1}


@pytest.mark.parametrize("changes, reason", [
    ({"model_a": None}, "no usable model name"),
    ({"model_a": "two words"}, "no usable model name"),
    ({"conversation_a": None}, "unrecognised conversation"),
    ({"conversation_a": "text"}, "unrecognised conversation"),
    ({"conversation_a": [{"who": "user"}]}, "unrecognised conversation"),
    ({"conversation_a": [turn("assistant", "x")]}, "no prompt text"),
    ({"conversation_a": [turn("user", "p")]}, "no response text"),
    ({"conversation_a": [turn("user", "p"), turn("assistant", "  ")]},
     "no response text"),
    ({"conversation_a": [turn("user", "p"), turn("assistant", {"code": "x"})]},
     "unrecognised conversation"),
])
def test_a_bad_side_is_skipped_and_the_other_kept(tmp_path, changes, reason):
    counts, records, _ = run(tmp_path, [row(**changes)])
    assert [r["model_id"] for r in records] == ["mystery-model"]
    assert counts.skipped_sides == {reason: 1}


def test_iso_utc_timestamp_text_is_read(tmp_path):
    _, records, _ = run(tmp_path, [row(tstamp="2025-01-15T12:00:00+00:00")])
    assert records[0]["timestamp"] == "2025-01-15T12:00:00.000Z"


def test_repeated_rows_are_not_imported_twice(tmp_path):
    counts, records, _ = run(tmp_path, [row(), row()])
    assert len(records) == 2
    assert counts.skipped_sides == {"repeats an earlier question_id and side": 2}


@pytest.mark.parametrize("chunk", [7, 1 << 16])
def test_json_array_with_a_bad_element_continues(tmp_path, chunk):
    source = tmp_path / "in.json"
    source.write_text(
        '[\n' + json.dumps(row("q-1")) + ',\n{"broken": tru},\n[1, "]"],\n'
        + json.dumps(row('q-"}]\\')) + '\n]\n', encoding="utf-8")
    rows = list(wa.iter_rows(source, chunk_size=chunk))
    assert [isinstance(r, wa.BadRow) for r in rows] == [False, True, False, False]
    counts = wa.import_file(source, tmp_path / "o.jsonl", revision="r")
    assert counts.records == 4
    assert counts.skipped_rows == {"not valid JSON": 1, "not a JSON object": 1}


def test_json_lines_input(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_bytes(json.dumps(row()).encode() + b"\n\n{oops\n\xff\xfe\n")
    counts = wa.import_file(source, tmp_path / "o.jsonl", revision="r")
    assert counts.records == 2
    assert counts.skipped_rows == {"not valid JSON": 2}


@pytest.mark.parametrize("suffix", ["array", "lines"])
def test_an_oversized_row_is_skipped_without_being_held(tmp_path, suffix):
    big = json.dumps(row("big", model_a="m" * 5000))
    small = json.dumps(row("small"))
    source = tmp_path / "in"
    text = f"[{big},{small}]" if suffix == "array" else f"{big}\n{small}\n"
    source.write_text(text, encoding="utf-8")
    rows = list(wa.iter_rows(source, chunk_size=64, max_row=2000))
    assert isinstance(rows[0], wa.BadRow) and rows[0].reason == "row too large"
    assert rows[1]["question_id"] == "small"
    assert len(rows) == 2


@pytest.mark.parametrize("text", ["", "   ", '[{"a": 1}', '[{"a": "', '{"a":1}'])
def test_a_cut_off_or_empty_file(tmp_path, text):
    source = tmp_path / "in.json"
    source.write_text(text, encoding="utf-8")
    rows = list(wa.iter_rows(source))
    if text.startswith("["):
        assert [r.reason for r in rows] == ["file ends inside the array"]
    elif text.startswith("{"):
        assert rows == [{"a": 1}]
    else:
        assert rows == []


def test_limit_stops_reading(tmp_path):
    counts, records, _ = run(tmp_path, [row("q-1"), row("q-2")], limit=1)
    assert counts.rows == 1 and len(records) == 2


def test_an_existing_output_is_refused(tmp_path):
    source = write_array(tmp_path / "in.json", [row()])
    out = tmp_path / "o.jsonl"
    out.write_text("", encoding="utf-8")
    with pytest.raises(wa.ImportRefused):
        wa.import_file(source, out, revision="r")


def test_output_inside_a_repository_must_be_in_an_ignored_folder(tmp_path):
    (tmp_path / ".git").mkdir()
    source = write_array(tmp_path / "in.json", [row()])
    with pytest.raises(wa.ImportRefused):
        wa.import_file(source, tmp_path / "tests" / "o.jsonl", revision="r")
    assert not (tmp_path / "tests").exists()
    counts = wa.import_file(source, tmp_path / "data" / "x" / "o.jsonl", revision="r")
    assert counts.records == 2


def test_command_line_prints_counts(tmp_path, capsys):
    source = write_array(tmp_path / "in.json", [row(), row(question_id=None)])
    out = tmp_path / "o.jsonl"
    assert wa.main([str(source), str(out), "--revision", "r"]) == 0
    printed = capsys.readouterr().out
    assert "rows read: 2" in printed and "records written: 2" in printed
    assert "no question_id: 1" in printed
    assert "Invented" not in printed  # no dataset content on the console
    assert wa.main([str(source), str(out), "--revision", "r"]) == 2


def test_metrics_leave_imported_records_out(tmp_path):
    _, records, _ = run(tmp_path, [row()])
    website = analysis_spec.load_spec("website")
    assert runs.select(records, website, [None]).runs == []
    # Even one given a batch id is not taken into a table.
    batched = [dict(r, batch_id="pilot-1") for r in records]
    selection = runs.select(batched, website, ["pilot-1"])
    assert selection.runs == []
    assert any("2 records that are not controlled API runs" in note
               for note in selection.notes)
