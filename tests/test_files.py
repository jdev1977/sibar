"""Files extracted from a response's text (T0.5). No network."""

import hashlib
import os

import pytest

from runner.files import MAX_FILES, extract_files, safe_path, write_files
from runner.record import _is_relative_path, check_files

FENCE = "`" * 3


def fenced(lang, body, fence=FENCE):
    if not body.endswith("\n"):
        body += "\n"
    return f"{fence}{lang}\n{body}{fence}\n"


def names(text):
    return [f.path for f in extract_files(text)]


# --- Finding blocks -------------------------------------------------------------


def test_fenced_blocks_are_extracted_in_order_with_generic_names():
    text = ("Here is the page.\n\n" + fenced("html", "<p>hi</p>\n")
            + "\nAnd the style:\n\n" + fenced("css", "p { color: red; }\n")
            + fenced("", "plain\n"))
    files = extract_files(text)
    assert [f.path for f in files] == ["block-01.html", "block-02.css",
                                       "block-03.txt"]
    assert files[0].content == "<p>hi</p>\n"
    assert files[1].content == "p { color: red; }\n"


@pytest.mark.parametrize("lang,ext", [
    ("python", "py"), ("Python3", "py"), ("js", "js"), ("javascript", "js"),
    ("typescript", "ts"), ("bash", "sh"), ("shell", "sh"), ("yaml", "yaml"),
    ("json", "json"), ("markdown", "md"), ("svg", "svg"), ("weird-lang", "txt"),
    ("../../x", "txt"),
])
def test_the_language_gives_the_extension(lang, ext):
    assert names(fenced(lang, "x\n")) == [f"block-01.{ext}"]


@pytest.mark.parametrize("info", [
    "html index.html", "html:index.html", 'html title="index.html"',
    "html filename=index.html", "html file='index.html'",
])
def test_a_file_name_in_the_info_string_is_used(info):
    assert names(fenced(info, "<p></p>\n")) == ["index.html"]


@pytest.mark.parametrize("line", [
    "**index.html**", "`index.html`:", "### index.html", "### `index.html`",
    "File: index.html", "**File: `index.html`**", "index.html:", "1. `index.html`",
    "- **index.html**",
])
def test_a_file_name_on_the_line_before_the_fence_is_used(line):
    assert names(f"{line}\n{fenced('html', '<p></p>')}") == ["index.html"]
    assert names(f"{line}\n\n{fenced('html', '<p></p>')}") == ["index.html"]


@pytest.mark.parametrize("line", [
    "Here is the code:", "Save this as index.html in a folder:", "See https://x.example/a.html",
    "**Note**", "version 1.2", "",
])
def test_prose_before_a_fence_is_not_a_file_name(line):
    assert names(f"{line}\n{fenced('html', '<p></p>')}") == ["block-01.html"]


def test_a_hint_two_blank_lines_away_is_ignored():
    assert names(f"index.html\n\n\n{fenced('html', 'x')}") == ["block-01.html"]


def test_paths_with_folders_are_kept():
    text = fenced("js src/app.js", "1\n") + "**src/lib/util.js**\n" + fenced("js", "2\n")
    assert names(text) == ["src/app.js", "src/lib/util.js"]


def test_tilde_fences_and_longer_fences_hold_inner_fences():
    inner = fenced("python", "print(1)\n")
    text = fenced("markdown README.md", inner, fence="````") + fenced("txt", "a\n", "~~~")
    files = extract_files(text)
    assert [f.path for f in files] == ["README.md", "block-02.txt"]
    assert files[0].content == inner


def test_a_closing_fence_needs_the_same_character_and_length():
    text = "````md\n```\nstill inside\n~~~~\n````\n"
    files = extract_files(text)
    assert len(files) == 1
    assert files[0].content == "```\nstill inside\n~~~~\n"


def test_an_unclosed_fence_is_not_extracted():
    assert names("Intro\n" + FENCE + "html\n<p>cut off") == []


def test_an_indented_fence_loses_that_indentation():
    text = "  ```py\n  x = 1\n    y = 2\n  ```\n"
    assert extract_files(text)[0].content == "x = 1\n  y = 2\n"


def test_whitespace_only_blocks_are_skipped():
    assert names(fenced("txt", "\n  \n")) == []


def test_windows_line_endings_are_understood():
    text = "**a.py**\r\n```python\r\nx = 1\r\n```\r\n"
    files = extract_files(text)
    assert [f.path for f in files] == ["a.py"]
    assert files[0].content == "x = 1\r\n"


def test_a_complete_html_document_outside_fences_is_extracted():
    doc = "<!DOCTYPE html>\n<html lang=\"en\"><body>Hi</body></html>"
    files = extract_files(f"Sure! Here it is:\n\n{doc}\n\nEnjoy.")
    assert [(f.path, f.content) for f in files] == [("document-01.html", doc)]


def test_an_html_document_without_doctype_is_extracted():
    assert names("<html><body>x</body></HTML >") == ["document-01.html"]


def test_html_inside_a_fence_is_not_extracted_twice():
    doc = "<!doctype html><html><body>x</body></html>\n"
    assert names(fenced("html", doc)) == ["block-01.html"]
    assert names(FENCE + "html\n" + doc) == []  # unclosed: all of it is code


def test_an_unfinished_html_document_is_not_extracted():
    assert names("<!DOCTYPE html><html><body>cut") == []


def test_many_unclosed_html_tags_do_not_take_quadratic_time():
    import time
    text = "<html>" * 50_000 + "</html>" + "<html>" * 50_000
    started = time.perf_counter()
    files = extract_files(text)
    assert time.perf_counter() - started < 2
    assert [f.path for f in files] == ["document-01.html"]


def test_no_blocks_no_files():
    assert extract_files("Just prose, no code.") == []


# --- Unsafe names -----------------------------------------------------------------


@pytest.mark.parametrize("hint,expected", [
    ("../../etc/passwd", "etc/passwd"),
    ("..\\..\\Windows\\win.ini", "Windows/win.ini"),
    ("/etc/shadow", "etc/shadow"),
    ("C:\\Windows\\System32\\x.dll", "C_/Windows/System32/x.dll"),
    ("\\\\server\\share\\x.txt", "server/share/x.txt"),
    ("a:b.txt", "a_b.txt"),
    ("CON.html", "_CON.html"),
    ("con", "_con"),
    ("nul.tar.gz", "_nul.tar.gz"),
    ("COM1", "_COM1"),
    ("lpt9.js", "_lpt9.js"),
    ("aux/index.html", "_aux/index.html"),
    ("x.html. . ", "x.html"),
    ("my page?.html", "my_page_.html"),
    ("evil\u202egnp.js", "evil_gnp.js"),
    ("tab\there.txt", "tab_here.txt"),
    ("caf\u00e9.html", "caf_.html"),
    ("a/./b/../c.txt", "a/b/c.txt"),
    (".gitignore", ".gitignore"),
    ("deep/a/b/c/d/e/f.txt", "b/c/d/e/f.txt"),
])
def test_unsafe_names_are_made_safe(hint, expected):
    assert safe_path(hint) == expected
    assert _is_relative_path(expected)


@pytest.mark.parametrize("hint", ["", "..", ".", "/", "\\", "../..", "...", " . ",
                                  "\x00", "a" * 0])
def test_names_with_nothing_left_are_refused(hint):
    assert safe_path(hint) is None


def test_long_names_are_shortened():
    path = safe_path("x" * 300 + ".html")
    assert path is not None and len(path) <= 120
    assert _is_relative_path(path)


def test_unsafe_hints_fall_back_or_are_cleaned_in_extraction():
    text = (fenced("html ../../../escape.html", "a\n")
            + fenced("html ..", "b\n")
            + "**C:\\temp\\x.js**\n" + fenced("js", "c\n"))
    assert names(text) == ["escape.html", "block-02.html", "C_/temp/x.js"]


def test_repeated_names_get_a_number_ignoring_case():
    text = (fenced("html index.html", "1\n") + fenced("html Index.html", "2\n")
            + fenced("html INDEX.HTML", "3\n"))
    assert names(text) == ["index.html", "Index-2.html", "INDEX-3.HTML"]


def test_a_file_and_a_folder_of_the_same_name_do_not_collide():
    text = fenced("txt a", "1\n") + fenced("js a/b.js", "2\n")
    text += fenced("js c/d.js", "3\n") + fenced("txt C", "4\n")
    assert names(text) == ["a", "a_b.js", "c/d.js", "C-2"]


def test_generated_names_do_not_collide_with_hinted_ones():
    text = fenced("html block-02.html", "1\n") + fenced("html", "2\n")
    assert names(text) == ["block-02.html", "block-02-2.html"]


def test_the_number_of_files_is_capped():
    text = "".join(fenced("txt", f"{n}\n") for n in range(MAX_FILES + 5))
    assert len(extract_files(text)) == MAX_FILES


# --- Writing ----------------------------------------------------------------------


def test_files_are_written_under_the_prefix_with_sha256_and_size(tmp_path):
    text = fenced("html index.html", "<p>caf\u00e9</p>\n") + fenced("js src/app.js", "x\n")
    entries = write_files(tmp_path, extract_files(text))
    assert [e["path"] for e in entries] == ["extracted/index.html",
                                           "extracted/src/app.js"]
    data = "<p>caf\u00e9</p>\n".encode("utf-8")
    assert (tmp_path / "extracted" / "index.html").read_bytes() == data
    assert entries[0]["sha256"] == hashlib.sha256(data).hexdigest()
    assert entries[0]["size"] == len(data)
    record = {"files": entries, "checks": []}
    assert check_files(record, tmp_path) == []


def test_every_attack_ends_up_inside_the_directory(tmp_path):
    hints = ["../../outside.txt", "..\\..\\outside2.txt", "/abs.txt", "C:\\x\\y.txt",
             "CON", "aux.js", "a:stream.txt", "x. ", "\u202eevil.txt", "....//x.txt"]
    text = "".join(fenced(f"txt {h}", f"{n}\n") for n, h in enumerate(hints))
    base = tmp_path / "files" / "rec"
    entries = write_files(base, extract_files(text))
    assert len(entries) == len(hints)
    written = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    assert len(written) == len(hints)
    for path in written:
        assert path.resolve().is_relative_to((base / "extracted").resolve())
    for entry in entries:
        assert _is_relative_path(entry["path"])


def test_an_existing_file_is_never_overwritten(tmp_path):
    files = extract_files(fenced("txt a.txt", "new\n"))
    (tmp_path / "extracted").mkdir()
    (tmp_path / "extracted" / "a.txt").write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_files(tmp_path, files)
    assert (tmp_path / "extracted" / "a.txt").read_text(encoding="utf-8") == "old"


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_written_names_are_valid_on_windows(tmp_path):
    text = "".join(fenced(f"txt {h}", "x\n") for h in ["CON", "a<b>.txt", "q?.js", "p|.c"])
    entries = write_files(tmp_path, extract_files(text))
    for entry in entries:
        assert (tmp_path / entry["path"]).is_file()


def test_lone_surrogates_do_not_stop_writing(tmp_path):
    files = extract_files(fenced("txt a.txt", "bad \ud800 char\n"))
    entries = write_files(tmp_path, files)
    assert entries[0]["size"] > 0
