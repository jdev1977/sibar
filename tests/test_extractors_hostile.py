"""Hostile input to the pipeline, math and engineering extractors (T2.8):
long single tokens, unclosed delimiters and many near matches, at the size
limits. Every extractor must finish in bounded time without an error."""

import time
from pathlib import Path

import pytest

from extractors.base import InputFile, Inputs, run_extractors
from extractors.registry import extractors_for
from runner.files import extract_files

FIXTURES = Path(__file__).parent / "fixtures"

# Large enough that a quadratic reading takes minutes, small enough that the
# whole file runs in about a minute. Every piece was also timed once at the
# 1,000,000 character limit: no extractor took 2 seconds.
SIZE = 100_000
SECONDS = 10       # for all extractors of a type on one input

PIECES = {
    "digits": "1", "decimals": "1.", "grouped": "1,000", "spaces": " ",
    "tabs-and-words": "a \t", "letters": "a", "dollars": "$", "dollar-digits": "$1 ",
    "backslashes": "\\", "latex-open": "\\[ $$ \\( ", "begin": "\\begin{align}",
    "braces": "{", "boxed": "\\boxed{", "stars": "*", "bold": "**a ",
    "pipes": "|", "table": "|-|\n", "fences": "```\n", "backticks": "`",
    "quotes": '"', "triple-quotes": '"""\n', "single-quotes": "'",
    "comments": "/* ", "hashes": "# ", "newlines": "\n", "parens": "(",
    "units": "1 m ", "unit-chain": "1 N·m·m·m·m", "inches": '1" ',
    "iso": "ISO ", "safety": "safety factor ", "safety-open": "safety factor of (",
    "constants": "drag coefficient ", "ka": "K_a = ", "roughness": "roughness ",
    "water": "water ", "ends": "closed ends ", "declared": "ends: ",
    "open-call": "open(", "open-as": "with open(a) as f:\n",
    "for-line": "for line in ", "import": "import a, ", "from": "from a import ",
    "go-import": "import (\n", "require": 'require("', "assigned": 'api_key = "',
    "key-lines": "password ", "yaml": "- a: [", "pronouns": "you we ",
    "reader": "r = csv.reader(f)\n", "superscript": "⁻", "volts": "12 V ",
    "convert": "convert ", "markup": "<svg ",
    "on-jobs": "on:\njobs:\n", "pipeline-brace": "pipeline {\n",
    "key-token": "key token ", "for-open": "for line in open(",
    "open-method": "for x in a.b(c).", "open-nested": "open(a(",
    "config-name": "/config-", "save": ".save(", "image-chain": "Image.open(",
    "image-assign": "from PIL import Image\na = a.resize(",
    "in-memory": "a = b ", "acid": "Ka (", "acid-of": "Ka of ", "fraction": "1/",
    "mixed-fraction": "1 1/", "safety-n": "safety factor, n", "exif": "(exif = ",
    "definition": "def f(", "entry": "config[", "chain": "a.",
    "config-open": "with open(a.b[c].config.", "power": "Ka = 10^-4.",
}


def repeated(piece):
    return (piece * (SIZE // len(piece) + 1))[:SIZE]


@pytest.mark.parametrize("name", sorted(PIECES))
@pytest.mark.parametrize("project_type", ["pipeline", "math", "engineering"])
def test_a_long_run_of_one_piece_is_read_in_bounded_time(project_type, name):
    text = repeated(PIECES[name])
    record = {"raw_response": text, "prompt_text": text[:2000], "files": []}
    suffixes = ("py", "js", "go", "yaml", "scad") if project_type != "math" else ("py",)
    files = [InputFile(f"a.{suffix}", text[:SIZE // len(suffixes)].encode())
             for suffix in suffixes]
    start = time.perf_counter()
    results = run_extractors(extractors_for(project_type), Inputs(files, record=record))
    spent = time.perf_counter() - start
    errors = {key: values for key, (_, values) in results.items()
              if values["status"] == "error"}
    assert errors == {}
    assert spent < SECONDS


@pytest.mark.parametrize("project_type", ["pipeline", "math", "engineering"])
def test_windows_line_endings_read_the_same(project_type):
    for folder in sorted((FIXTURES / project_type).iterdir()):
        text = (folder / "response.md").read_bytes().decode().replace("\r\n", "\n")
        read = []
        for ending in ("\n", "\r\n"):
            changed = text.replace("\n", ending)
            files = [InputFile(f.path, f.content.encode())
                     for f in extract_files(changed)]
            record = {"raw_response": changed, "prompt_text": "p", "files": []}
            read.append(run_extractors(extractors_for(project_type),
                                       Inputs(files, record=record)))
        assert read[0] == read[1], folder.name


def test_files_with_windows_line_endings():
    source = (b"import cadquery as cq\r\nif __name__ == '__main__':\r\n    pass\r\n"
              b"thickness = 6\r\n")
    record = {"raw_response": "see file", "prompt_text": "p", "files": []}
    out = run_extractors(extractors_for("engineering"),
                         Inputs([InputFile("a.py", source)], record=record))
    assert out["engineering.cad"][1]["cad_parameters"] == ["thickness=6"]


def test_binary_and_empty_files():
    files = [InputFile("a.py", bytes(range(256)) * 2000), InputFile("b.yaml", b""),
             InputFile("c.txt", b"\xff\xfe\x00")]
    record = {"raw_response": "\x00\udcff junk", "prompt_text": "", "files": []}
    for project_type in ("pipeline", "math", "engineering"):
        results = run_extractors(extractors_for(project_type),
                                 Inputs(files, record=record))
        assert all(values["status"] in ("ok", "partial", "no-input")
                   for _, values in results.values()), project_type
