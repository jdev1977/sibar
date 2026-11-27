"""The shared readers of the pipeline, math and engineering extractors (T2.8):
the response document, code splitting and numbers."""

import hashlib

from extractors.base import InputFile, Inputs
from extractors.common import code, numbers
from extractors.common.reply import reply_values
from extractors.common.response import MAX_TEXT, get_doc

REPLY = """# Title

Some words here, and a price of 5 items.

- one
- two

| a | b |
|---|---|
| 1 | 2 |
| 3 | 4 |

```python
# a comment | not a table
import csv
```

```text
x = 3 m
```

~~~
unclosed
"""


def record(text, files=()):
    return {"raw_response": text, "prompt_text": "p", "files": []}


def doc_of(text, files=()):
    return get_doc(Inputs(files, record=record(text)))


def test_prose_leaves_out_fenced_blocks_closed_or_not():
    doc = doc_of(REPLY)
    assert "price of 5 items" in doc.prose
    assert "import csv" not in doc.prose and "unclosed" not in doc.prose
    assert [block.language for block in doc.blocks] == ["python", "text", ""]


def test_working_text_keeps_plain_blocks_but_not_code():
    doc = doc_of(REPLY)
    assert "x = 3 m" in doc.working and "import csv" not in doc.working


def test_record_files_are_read_with_their_language_and_name():
    files = [InputFile("block-01.py", b"import csv\n"),
             InputFile("load.py", b"import sqlite3\n"),
             InputFile("block-02.txt", b"def f(x):\n    return x\n"),
             InputFile("block-03.txt", b"Loaded 3 rows\n")]
    doc = doc_of("hello", files)
    assert [(f.path, f.language, f.named) for f in doc.files] == [
        ("block-01.py", "python", False), ("block-02.txt", "python", False),
        ("block-03.txt", None, False), ("load.py", "python", True)]


def test_a_folder_with_response_md_takes_its_files_from_the_fences(tmp_path):
    (tmp_path / "response.md").write_text(
        "Run it.\n\n**load.py**\n```python\nprint(1)\n```\n", encoding="utf-8")
    doc = get_doc(Inputs.from_directory(tmp_path))
    assert doc.text.startswith("Run it.")
    assert [(f.path, f.language) for f in doc.files] == [("load.py", "python")]
    assert doc.prompt == ""


def test_a_long_response_is_cut_and_marked():
    doc = doc_of("a " * MAX_TEXT)
    assert doc.truncated and len(doc.text) <= MAX_TEXT


def test_reply_shape():
    values = reply_values(Inputs((), record=record(REPLY)))
    assert values == {"status": "ok", "words": 13, "headings": 1, "list_items": 2,
                      "code_blocks": 3, "tables": 1, "largest_table_rows": 2}


def test_reply_without_text_is_no_input():
    assert reply_values(Inputs(())) == {"status": "no-input"}


def test_python_split_separates_comments_docstrings_and_strings():
    source = ('"""Module doc."""\nimport os  # why\n\ndef f():\n    """Doc."""\n'
              '    s = "# not a comment"\n    t = """\nnot a docstring"""\n')
    parts = code.split("python", source)
    assert parts.docstrings == 2 and parts.comment_lines == 1
    assert "# why" not in parts.code and '"# not a comment"' in parts.code
    assert "not a comment" not in parts.bare and "not a docstring" not in parts.bare
    assert "import os" in parts.bare


def test_c_like_split():
    source = 'package main\n// a\n/* b\n c */\nvar s = "// no" // d\n'
    parts = code.split("go", source)
    assert parts.comment_lines == 4
    assert "// no" in parts.code and "// no" not in parts.bare
    assert "c */" not in parts.code


def test_languages_from_names_and_sniffing():
    assert code.language_of("a/b.py", "") == "python"
    assert code.language_of(".github/workflows/ci.yml", "") == "yaml"
    assert code.language_of("Dockerfile", "") == "dockerfile"
    assert code.language_of("block-01.txt", "package main\n\nfunc main() {}\n") == "go"
    assert code.language_of("block-01.txt", "cube([1,2,3]);\ndifference() {}\n") == "openscad"
    assert code.language_of("block-01.txt", "Rows read: 6\n") is None


def test_numbers_and_significant_figures():
    text = numbers.normalise(r"$K_a = 1.8 \times 10^{-5}$ and 1,692.65 and 6.0×10⁻³")
    found = [numbers.parse(m) for m in numbers.NUMBER.finditer(text)]
    assert [n.value for n in found] == [1.8e-5, 1692.65, 0.006]
    assert [n.sig_figs for n in found] == [2, 6, 2]
    assert numbers.sig_figs("1200") is None and numbers.sig_figs("0.00620") == 3
    assert numbers.sig_figs("55.20") == 4 and numbers.sig_figs("0") is None
    assert numbers.canonical(0.1450000001) == "0.145"
