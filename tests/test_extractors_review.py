"""Readings that review round 1 of T2.8 found wrong, each on a fixture with the
value worked out by reading it (tests/fixtures/<type>/)."""

import time
from pathlib import Path

import pytest

from extractors.base import InputFile, Inputs, run_extractors
from extractors.registry import extractors_for
from runner.files import extract_files

FIXTURES = Path(__file__).parent / "fixtures"


def features(kind, inputs):
    """``{<extractor short name>.<feature>: value}``."""
    results = run_extractors(extractors_for(kind), inputs)
    return {f"{name.split('.', 1)[1]}.{feature}": value
            for name, (_, values) in results.items()
            for feature, value in values.items()}


def reply(kind, text):
    files = [InputFile(f.path, f.content.encode()) for f in extract_files(text)]
    record = {"raw_response": text, "prompt_text": "p", "files": []}
    return features(kind, Inputs(files, record=record))


def source(text, name="a.py"):
    record = {"raw_response": "code", "prompt_text": "p", "files": []}
    return features("pipeline", Inputs([InputFile(name, text.encode())], record=record))


def check(values, expected):
    assert {key: values.get(key, "<missing>") for key in expected} == expected


CASES = {
    "pipeline/log-for-open": {
        "operations.file_reading": "streaming",
        "operations.read_calls": ["line-loop"]},
    "pipeline/log-fileinput": {
        "operations.file_reading": "streaming",
        "operations.read_calls": ["line-loop"]},
    "pipeline/log-split-lines": {
        "operations.file_reading": "whole-file",
        "operations.read_calls": ["read"]},
    "pipeline/image-manual-orient": {
        "images.metadata_handling": "unmentioned",
        "images.orientation_handling": "present",
        "operations.output_formats": ["image", "printed"],
        "operations.file_reading": "none"},
    "pipeline/image-saved-under-other-name": {
        "operations.output_formats": ["image", "printed"],
        "operations.file_reading": "none",
        "images.orientation_handling": "present"},
    "pipeline/api-urllib3-warnings": {
        "operations.retry_present": False, "operations.retry_libraries": []},
    "pipeline/api-asyncio-run": {"operations.parallel_work": []},
    "math/titration-subscripts": {
        "constants.ka_value": "1.8e-05", "constants.pka_value": "4.74",
        "constants.kw_value": "1e-14"},
    "engineering/cantilever-plot-labels": {
        "units.unit_system": "metric", "units.us_mentions": 0,
        "safety.safety_factor": "1.5"},
    "engineering/spring-given-factor": {"safety.safety_factor": "1.5"},
    "engineering/bracket-fractions": {"units.unit_system": "us-customary"},
    "engineering/pipe-velocity-head": {"safety.safety_factor": "1.2"},
    # round 2
    "pipeline/config-object-paths": {
        "operations.file_reading": "whole-file",
        "operations.read_calls": ["json-load", "read-text"]},
    "math/titration-decimal-exponent": {
        "constants.ka_value": "1.74e-05", "constants.pka_value": "4.76",
        "constants.kw_value": "1e-14"},
    "engineering/spec-in-data-blocks": {
        "units.unit_system": "metric",
        "quantities.quantities": ["200 N", "300 mm", "4 mm", "5 mm", "5.5 mm", "6 mm"]},
    "engineering/slashed-ratings": {
        "quantities.quantities": ["0.375 in", "1.25 in", "200 mm", "24 V"]},
    "pipeline/image-multiline-default": {
        "images.metadata_handling": "unmentioned", "images.metadata_calls": [],
        "images.orientation_handling": "absent"},
}


@pytest.mark.parametrize("fixture", sorted(CASES))
def test_reviewed_fixture(fixture):
    values = features(fixture.split("/")[0], Inputs.from_directory(FIXTURES / fixture))
    check(values, CASES[fixture])


def test_fractions_are_read_whole():
    found = features("engineering", Inputs.from_directory(
        FIXTURES / "engineering" / "bracket-fractions"))["quantities.quantities"]
    assert "0.125 in" in found and "8 in" not in found
    found = reply("engineering", "A strip 1 1/2 in wide.")["quantities.quantities"]
    assert found == ["1.5 in"]


def test_twice_g_is_not_two_grams():
    found = reply("engineering", "h = f (L/D) V²/2g = 1.49 m, and 2g of grease.")
    assert found["quantities.quantities"] == ["1.49 m"]
    assert reply("engineering", "A 145g ball.")["quantities.quantities"] == ["145 g"]


# --- C1: YAML that does not load ----------------------------------------------


def test_a_broken_workflow_of_repeated_headings_is_read_in_bounded_time():
    text = "{\n" + "on:\njobs:\n" * 9000
    start = time.perf_counter()
    out = source(text, "ci.yml")
    assert time.perf_counter() - start < 2
    assert out["ci.ci_service"] is None


def test_a_broken_workflow_is_still_recognised():
    out = source("{\non:\n  push:\njobs:\n  a:\n    runs-on: x\n", "block-01.yaml")
    assert out["ci.ci_service"] == "github-actions" and out["ci.triggers"] is None


def test_many_unclosed_jenkins_pipelines_are_read_in_bounded_time():
    start = time.perf_counter()
    source("pipeline {\n" * 9000, "block-01.groovy")
    source("pipeline {\n" * 9000, "Jenkinsfile")
    assert time.perf_counter() - start < 2


# --- I1: how files are read ---------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("for line in open('a'):\n    pass\n", "streaming"),
    ("for line in gzip.open(p, 'rt'):\n    pass\n", "streaming"),
    ("for n, line in enumerate(open(p, encoding='utf-8'), 1):\n    pass\n",
     "streaming"),
    ("for row in path.open():\n    pass\n", "streaming"),
    ("for x in fileinput.input():\n    pass\n", "streaming"),
    ("for x in sys.stdin:\n    pass\n", "streaming"),
    ("for line in open(p).read().split():\n    pass\n", "whole-file"),
    ("with open(p) as f:\n    lines = f.read().splitlines()\n"
     "for line in lines:\n    pass\n", "whole-file"),
    ("with open(p) as f:\n    rows = f.readlines()\nfor line in rows:\n    pass\n",
     "whole-file"),
    ("data = Path(p).read_text()\nfor line in data:\n    pass\n", "whole-file"),
    ("with open('config.json') as f:\n    c = json.load(f)\n", "none"),
    ("with open(path) as cfg:\n    c = json.load(cfg)\n", "none"),
    ("with open(p) as f:\n    settings = json.load(f)\n", "none"),
    ("c = json.loads(Path('config.json').read_text())\n", "none"),
    ("with open('data.json') as f:\n    data = json.load(f)\n", "whole-file"),
    ("for line in open(p):\n    pass\nc = json.load(open('rules.json'))\n",
     "streaming"),
    ("img = Image.open(p)\nimg.save(q)\n", "none"),
])
def test_how_files_are_read(text, expected):
    assert source(text)["operations.file_reading"] == expected


# --- I2, I3: images -------------------------------------------------------------


@pytest.mark.parametrize("line, expected", [
    ("exif = img.getexif()\nimg.save(q)", "unmentioned"),
    ("exif = img.info.get('exif')\nimg.save(q, exif=exif)", "keeps"),
    ("img.save(q, quality=85,\n         exif=original)", "keeps"),
    ("params['exif'] = exif_bytes\nimg.save(q, **params)", "keeps"),
    ("exif = None\nimg.save(q)", "unmentioned"),
    ("img.save(q, exif=None)", "strips"),
    ("def f(img, exif=None):\n    pass", "unmentioned"),
])
def test_metadata_needs_a_keyword_argument(line, expected):
    out = source(f"from PIL import Image\nimg = Image.open(p)\n{line}\n")
    assert out["images.metadata_handling"] == expected


@pytest.mark.parametrize("text", [
    "from PIL import Image\nImage.open(p).convert('RGB').save(q)\n",
    "from PIL import Image\nwith Image.open(p) as source:\n    small = source.resize(s)\n"
    "    small.save(q)\n",
    "from PIL import Image, ImageOps\nframe = Image.open(p)\n"
    "upright = ImageOps.exif_transpose(frame)\nflat = upright.convert('RGB')\n"
    "flat.save(q)\n",
    "from PIL import Image\ndef store(pic: Image.Image, q):\n    pic.save(q)\n",
])
def test_a_saved_image_is_an_output_whatever_its_name(text):
    assert "image" in source(text)["operations.output_formats"]


def test_saving_something_else_is_not_an_image():
    out = source("from PIL import Image\nimg = Image.open(p)\nworkbook.save('a.xlsx')\n")
    assert "image" not in out["operations.output_formats"]


def test_image_readings_are_provisional():
    from analysis.spec import load_spec
    spec = load_spec("pipeline")
    for name in ("metadata_handling", "orientation_handling"):
        assert spec.variables[f"pipeline.images.{name}"].role == "provisional"


# --- I4: how constants are spelled ----------------------------------------------


@pytest.mark.parametrize("text, feature, value", [
    ("Kₐ = 1.8 × 10⁻⁵", "ka_value", "1.8e-05"),
    ("The Ka of acetic acid is 1.8 × 10⁻⁵.", "ka_value", "1.8e-05"),
    ("Ka (acetic acid) = 1.8e-5", "ka_value", "1.8e-05"),
    (r"$K_a$ for acetic acid: $1.8 \times 10^{-5}$", "ka_value", "1.8e-05"),
    ("K_a for CH3COOH is 1.75 × 10^-5", "ka_value", "1.75e-05"),
    (r"$K_\text{a} = 1.8 \times 10^{-5}$", "ka_value", "1.8e-05"),
    ("The pKa of acetic acid is 4.76.", "pka_value", "4.76"),
    (r"$\text{p}K_\text{a} = 4.74$", "pka_value", "4.74"),
    (r"$K_w = 10^{-14}$", "kw_value", "1e-14"),
    ("Kw = 10⁻¹⁴", "kw_value", "1e-14"),
    ("Kb = Kw/Ka = 5.6 × 10⁻¹⁰", "ka_value", "not-stated"),
])
def test_acid_constant_spellings(text, feature, value):
    out = reply("math", "Titration. " + text)
    assert out[f"constants.{feature}"] == value


# --- safety factor --------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("Given a safety factor of 2, the stress is limited.", "2"),
    ("Take FS = 2.0 here.", "2"),
    ("The safety factor >= 2 is required.", "2"),
    ("Use a safety factor ≥ 1.5.", "1.5"),
    ("Choose a safety factor, n = 2.", "2"),
    ("So FS ≥ 1.3, which is fine.", None),
    ("This is given by a safety factor of 2.", "2"),
])
def test_more_ways_to_state_a_safety_factor(text, expected):
    assert reply("engineering", text)["safety.safety_factor"] == expected


# --- inches ----------------------------------------------------------------------


def test_a_quote_mark_in_a_code_string_is_not_inches():
    text = ('The beam is 1.5 m long.\n\n```python\nplt.title("Deflection, case 2")\n'
            'plt.legend(["Tip load 4"])  # span 1500 mm\n```\n')
    out = reply("engineering", text)
    assert out["units.us_mentions"] == 0 and out["units.metric_mentions"] == 2


@pytest.mark.parametrize("text, expected", [
    ("with open(config.input_path) as f:\n    data = json.load(f)\n", "whole-file"),
    ("with open(config['input']) as f:\n    for line in f:\n        pass\n",
     "streaming"),
    ("with open(settings.INPUT_FILE) as f:\n    text = f.read()\n", "whole-file"),
    ("text = Path(cfg.input).read_text()\n", "whole-file"),
    ("with open(self.config.csv_path) as f:\n    rows = list(csv.DictReader(f))\n",
     "whole-file"),
    ("data = json.load(open(cfg.source))\n", "whole-file"),
    ("with open(CONFIG_PATH) as f:\n    c = json.load(f)\n", "none"),
    ("with open(args.config) as f:\n    c = json.load(f)\n", "none"),
    ("with open(paths['config']) as f:\n    c = json.load(f)\n", "none"),
    ("with open(base / 'config.json') as f:\n    c = json.load(f)\n", "none"),
    ("c = json.loads(config_path.read_text())\n", "none"),
])
def test_a_value_taken_from_a_config_object_is_data(text, expected):
    assert source(text)["operations.file_reading"] == expected


@pytest.mark.parametrize("text, value", [
    ("Ka = 10^-4.76", "1.74e-05"),
    (r"$K_a = 10^{-4.76} = 1.74 \times 10^{-5}$", "1.74e-05"),
    ("Ka = 10^(-4.76) ≈ 1.75e-5", "1.75e-05"),
    ("Ka = 10^-5", "1e-05"),
])
def test_a_decimal_power_of_ten(text, value):
    assert reply("math", "Titration. " + text)["constants.ka_value"] == value


@pytest.mark.parametrize("block", ["yaml", "csv", "markdown", "json", "toml", "text",
                                   "svg", "cron"])
def test_quantities_of_a_block_that_is_no_program(block):
    out = reply("engineering", f"See below.\n\n```{block}\nwidth = 40 mm\n```\n")
    assert out["quantities.quantities"] == ["40 mm"]


@pytest.mark.parametrize("text, expected", [
    ("a 12/24 V supply", ["24 V"]),
    ("a 100/200 mm range", ["200 mm"]),
    ("a 3/4 m rod", ["4 m"]),
    ("a 5/16 in hole.", ["0.3125 in"]),
    ("a 3/5 in hole.", ["5 in"]),
])
def test_only_inch_fractions_are_fractions(text, expected):
    assert reply("engineering", text)["quantities.quantities"] == expected


@pytest.mark.parametrize("line, present", [
    ("LOG_ORIENTATION = True", False),
    ("PAGE_ORIENTATION_NAME = 'x'", False),
    ("ORIENTATION = 274", True),
    ("EXIF_ORIENTATION_TAG = 274", True),
])
def test_an_orientation_constant(line, present):
    out = source(f"from PIL import Image\n{line}\n")
    assert out["images.orientation_handling"] == ("present" if present else "absent")


def test_a_urllib3_retry_object_is_still_a_retry():
    out = source("from urllib3.util.retry import Retry\nstrategy = Retry(total=3)\n")
    assert out["operations.retry_libraries"] == ["urllib3"]


def test_asyncio_gather_is_parallel_work():
    out = source("import asyncio\nasync def f():\n    await asyncio.gather(a(), b())\n")
    assert out["operations.parallel_work"] == ["asyncio"]
