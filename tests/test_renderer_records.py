"""Renders stored in run records, and the renderer's command line (T1.3)."""

import json
import shutil

import pytest

from renderer.__main__ import main
from renderer.browser import (
    VARIANTS, BrowserUnavailable, PageResult, Settings, VariantResult, render_page,
)
from renderer.process import Run
from renderer.records import RenderRefused, render_directory, render_file
from renderer_support import PAGES, require_chromium
from runner.files import save_files
from runner.ledger import _lock, _unlock
from runner.record import (
    append_record, build_record, check_files, file_entry, files_dir, read_records,
    write_records,
)

PAGE = "```html index.html\n<!doctype html><html><body>hello</body></html>\n```\n"


def add(path, text=PAGE, **fields):
    """A record in ``path`` whose files are extracted from ``text``."""
    values = dict(project_type="website", task_id="bakery-landing", prompt_text="p",
                  provider="anthropic", model_id="m", status="ok", level="L0",
                  wording="A", run_index=1, prompt_set_version="1", raw_response=text)
    values.update(fields)
    record = build_record(**values)
    if text:
        entries = save_files(files_dir(path, record["record_id"]), text)
        record["files"] = entries
    append_record(path, record)
    return record


class FakeRender:
    """Stands in for the browser: writes small files and notes its calls."""

    def __init__(self, outcome="ok", error=None):
        self.calls, self.outcome, self.error = [], outcome, error

    def __call__(self, root, entry, out, settings, files=None):
        self.calls.append((root, entry))
        if self.error:
            raise self.error
        out.mkdir(parents=True, exist_ok=True)
        variants = []
        for variant in settings.variants:
            if self.outcome == "ok":
                name = f"{variant.name}.png"
                (out / name).write_bytes(variant.name.encode())
                variants.append(VariantResult(variant.name, "ok", file=name, width=1,
                                              height=1, content_width=1,
                                              content_height=1))
            else:
                variants.append(VariantResult(variant.name, self.outcome, error="no"))
        return PageResult(variants=variants, blocked=["https://example.com/a.css"],
                          browser_version="1.2", command_line="C:/secret/path")


def run(path, render=None, **options):
    said = []
    counts = render_file(path, render=render or FakeRender(), say=said.append,
                         **options)
    return counts, said


def checks(path):
    result = read_records(path)
    assert result.ok and not result.truncated_tail
    return [record["checks"] for record in result.records]


def test_the_render_is_stored_in_the_record(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    render = FakeRender()
    counts, _ = run(path, render)
    directory = files_dir(path, record["record_id"])
    assert render.calls == [(directory / "extracted", "index.html")]
    assert counts == {"ok": 1}
    ((check,),) = checks(path)
    assert (check["name"], check["tool"], check["tool_version"],
            check["outcome"]) == ("render", "renderer", "1", "ok")
    assert [f["path"] for f in check["files"]] == [
        "render/desktop-light.png", "render/desktop-dark.png",
        "render/phone-light.png", "render/phone-dark.png"]
    assert check_files(read_records(path).records[0], directory) == []
    detail = check["detail"]
    assert detail["entry"] == "index.html"
    assert detail["candidates"] == ["index.html"]
    assert detail["blocked"] == ["https://example.com/a.css"]
    assert detail["settings"]["clock"] == "2027-03-09T12:00:00+00:00"
    assert (detail["settings"]["timezone"], detail["settings"]["locale"]) == (
        "UTC", "en-US")
    assert detail["browser"] == "1.2"
    assert detail["variants"]["phone-dark"]["viewport"] == [390, 844]
    assert "secret" not in json.dumps(check)


@pytest.mark.browser
def test_a_later_image_cannot_load_an_earlier_one(tmp_path):
    # Files stored outside extracted/: the page's folder then holds render/ too.
    require_chromium()
    path = tmp_path / "records.jsonl"
    record = add(path, None, raw_response="imported")
    directory = files_dir(path, record["record_id"])
    directory.mkdir(parents=True)
    (directory / "index.html").write_text(
        "<!doctype html><script>fetch('render/desktop-light.png')"
        ".then((r) => alert(r.status))</script>", encoding="utf-8")
    record["files"] = [file_entry(directory, "index.html")]
    write_records(path, [record])
    settings = Settings(variants=VARIANTS[:2], timeout=120, memory_mb=1536)
    said = []
    assert render_file(path, settings, say=said.append) == {"ok": 1}
    detail = checks(path)[0][0]["detail"]
    assert detail["dialogs"] == [{"type": "alert", "message": "404"}]
    assert detail["missing"] == ["render/desktop-light.png"]


def test_other_checks_are_kept(tmp_path):
    path = tmp_path / "records.jsonl"
    other = {"name": "html-valid", "tool": "x", "tool_version": "1", "outcome": "ok",
             "detail": None, "files": []}
    add(path, checks=[other])
    run(path)
    assert [c["name"] for c in checks(path)[0]] == ["html-valid", "render"]


def test_a_rendered_record_is_not_rendered_again_unless_forced(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    run(path, FakeRender("failed"))
    again = FakeRender()
    counts, _ = run(path, again)
    assert (again.calls, counts) == ([], {"skipped": 1})
    counts, _ = run(path, again, force=True)
    assert counts == {"ok": 1}
    ((check,),) = checks(path)  # replaced, not added
    assert check["outcome"] == "ok"


def test_a_render_that_errored_is_tried_again(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    counts, said = run(path, FakeRender(error=OSError(28, "No space left", "C:/x/y")))
    assert counts == {"error": 1}
    ((check,),) = checks(path)
    assert check["detail"]["error"] == "OSError: No space left"
    assert check["files"] == []
    assert run(path)[0] == {"ok": 1}


def test_a_failed_page_keeps_no_images(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    run(path, FakeRender("failed"))
    ((check,),) = checks(path)
    assert (check["outcome"], check["files"]) == ("failed", [])
    assert check["detail"]["variants"]["desktop-light"]["error"] == "no"


@pytest.mark.parametrize("text", [None, "```python\nprint(1)\n```\n"],
                         ids=["no files", "no html"])
def test_a_website_record_with_no_page_fails_the_check(tmp_path, text):
    path = tmp_path / "records.jsonl"
    add(path, text, raw_response="no page here")
    render = FakeRender()
    assert run(path, render)[0] == {"failed": 1}
    assert render.calls == []
    ((check,),) = checks(path)
    assert check["detail"]["error"] == "no HTML file"


def test_changed_or_missing_files_are_an_error(tmp_path):
    path = tmp_path / "records.jsonl"
    record = add(path)
    (files_dir(path, record["record_id"]) / "extracted" / "index.html").write_text("x")
    render = FakeRender()
    assert run(path, render)[0] == {"error": 1}
    assert render.calls == []
    assert "extracted/index.html" in checks(path)[0][0]["detail"]["error"]


def test_which_records_are_rendered(tmp_path):
    path = tmp_path / "records.jsonl"
    math = add(path, project_type="math")
    add(path, None, status="failed", error="e", raw_response=None)
    add(path, None, status="refused", raw_response="no")
    cut = add(path, status="truncated")
    render = FakeRender()
    assert run(path, render)[0] == {"ok": 1}
    assert [c[0].parent.name for c in render.calls] == [cut["record_id"]]
    # A record named on the command line is rendered whatever its type.
    assert run(path, render, record_ids=[math["record_id"]])[0] == {"ok": 1}


def test_an_unknown_record_id_is_refused(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    with pytest.raises(RenderRefused, match="no record"):
        run(path, record_ids=["00000000-0000-0000-0000-000000000000"])


def test_a_bad_record_file_is_refused_before_rendering(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    with open(path, "ab") as handle:
        handle.write(b"{not json}\n")
    render = FakeRender()
    with pytest.raises(RenderRefused, match="line 2"):
        run(path, render)
    assert render.calls == []


def test_a_record_file_in_use_is_refused(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    held = _lock(tmp_path / "records.jsonl.lock")
    try:
        with pytest.raises(RenderRefused, match="in use"):
            run(path)
    finally:
        _unlock(held)


def test_each_render_is_saved_at_once(tmp_path):
    path = tmp_path / "records.jsonl"
    add(path)
    add(path, run_index=2)
    first = FakeRender()

    def stop_at_the_second(*arguments, **named):
        if first.calls:
            raise BrowserUnavailable("gone")
        return first(*arguments, **named)

    with pytest.raises(BrowserUnavailable):
        run(path, stop_at_the_second)
    assert [len(c) for c in checks(path)] == [1, 0]


# --- when the render process gives no result ------------------------------------


@pytest.mark.parametrize("run, outcome, words", [
    (dict(timed_out=True), "failed", "did not finish within 30 seconds"),
    (dict(exit_code=7), "error", "without a result (exit code 7)"),
    (dict(exit_code=7, refused_memory=True), "failed", "memory cap of 4096 MB"),
    (dict(reply={"error": "Error: Connection closed"}), "error",
     "Connection closed"),
    (dict(reply={"error": "MemoryError: "}, refused_memory=True), "failed",
     "memory cap"),
], ids=["hung", "died", "died over the cap", "our error", "error over the cap"])
def test_what_a_lost_render_is_called(tmp_path, monkeypatch, run, outcome, words):
    values = dict(reply=None, timed_out=False, exit_code=0, memory_limited=True,
                  peak_mb=10, refused_memory=False)
    values.update(run)
    monkeypatch.setattr("renderer.browser.run_worker",
                        lambda *arguments: Run(**values))
    (tmp_path / "index.html").write_text("x")
    out = tmp_path / "out"
    result = render_page(tmp_path, "index.html", out)
    assert [v.outcome for v in result.variants] == [outcome] * 4
    assert words in result.variants[0].error
    assert result.peak_memory_mb == 10


# --- a single directory -------------------------------------------------------


def test_a_directory_render_is_described_in_render_json(tmp_path):
    site, out = tmp_path / "site", tmp_path / "out"
    shutil.copytree(PAGES / "bakery", site)
    check = render_directory(site, out, render=FakeRender())
    assert check == json.loads((out / "render.json").read_text(encoding="utf-8"))
    assert (check["outcome"], check["detail"]["entry"]) == ("ok", "index.html")
    assert [f["path"] for f in check["files"]][0] == "desktop-light.png"


def test_the_output_may_not_be_inside_the_page_folder(tmp_path):
    shutil.copytree(PAGES / "bakery", tmp_path / "site")
    with pytest.raises(RenderRefused, match="inside"):
        render_directory(tmp_path / "site", tmp_path / "site" / "shots",
                         render=FakeRender())


def test_an_entry_can_be_named(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    for name in ("index.html", "other.html"):
        (site / name).write_text("x")
    render = FakeRender()
    render_directory(site, tmp_path / "out", entry="other.html", render=render)
    assert render.calls[0][1] == "other.html"
    for bad in ("../x.html", "gone.html"):
        with pytest.raises(RenderRefused, match="entry"):
            render_directory(site, tmp_path / "out", entry=bad, render=render)


# --- the command line ------------------------------------------------------------


@pytest.mark.parametrize("arguments, message", [
    (["--dir", "nowhere"], "not a directory"),
    (["--records", "nowhere.jsonl"], "nowhere.jsonl"),
    (["--dir", ".", "--clock", "2027-03-09T12:00:00"], "time zone"),
    (["--dir", ".", "--clock", "soon"], "clock"),
    (["--dir", ".", "--timeout", "0"], "timeout"),
    (["--records", "x.jsonl", "--out", "y"], "--out"),
    (["--dir", ".", "--force"], "--force"),
])
def test_command_line_refusals(tmp_path, monkeypatch, capsys, arguments, message):
    monkeypatch.chdir(tmp_path)
    try:
        code = main(arguments)
    except SystemExit as stop:
        code = stop.code
    captured = capsys.readouterr()
    assert code == 2
    assert message in captured.out + captured.err


def test_command_line_reports_a_page_it_cannot_serve(tmp_path, monkeypatch, capsys):
    def cannot(*arguments, **named):
        raise ValueError("'x.html' is not a file in the page's folder")

    monkeypatch.setattr("renderer.__main__.render_directory", cannot)
    assert main(["--dir", str(tmp_path)]) == 2
    assert "not a file" in capsys.readouterr().out


@pytest.mark.browser
def test_command_line_on_a_record_file_and_a_directory(tmp_path, capsys):
    require_chromium()
    path = tmp_path / "records.jsonl"
    record = add(path)
    assert main(["--records", str(path), "--clock", "2027-03-09T12:00:00Z"]) == 0
    stored = read_records(path).records[0]
    assert len(stored["checks"][0]["files"]) == 4
    assert check_files(stored, files_dir(path, record["record_id"])) == []

    site = tmp_path / "bakery"
    shutil.copytree(PAGES / "bakery", site)
    assert main(["--dir", str(site)]) == 0
    out = tmp_path / "bakery-render"
    assert len(list(out.glob("*.png"))) == 4
    assert (out / "render.json").is_file()
    assert "ok" in capsys.readouterr().out
