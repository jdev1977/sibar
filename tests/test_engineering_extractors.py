"""The engineering extractors on hand-made fixtures with known values (T2.8).

Fixtures are in tests/fixtures/engineering/. Each expected value was worked
out by reading the fixture.
"""

from pathlib import Path

import pytest

from extractors.base import InputFile, Inputs, run_extractors
from extractors.registry import extractors_for
from runner.files import extract_files

FIXTURES = Path(__file__).parent / "fixtures" / "engineering"
ENGINEERING = extractors_for("engineering")


def run_inputs(inputs):
    results = run_extractors(ENGINEERING, inputs)
    return {full.split(".", 1)[1]: values for full, (_, values) in results.items()}


def run(name):
    return run_inputs(Inputs.from_directory(FIXTURES / name))


def reply(text):
    record = {"raw_response": text, "prompt_text": "Design it.", "files": []}
    files = [InputFile(f.path, f.content.encode()) for f in extract_files(text)]
    return run_inputs(Inputs(files, record=record))


def check(values, expected):
    assert {key: values.get(key, "<missing>") for key in expected} == expected


def test_every_extractor_runs_on_every_fixture_twice_alike():
    for folder in sorted(FIXTURES.iterdir()):
        first, second = run(folder.name), run(folder.name)
        assert first == second, folder.name
        for name, values in first.items():
            assert values["status"] == "ok", (folder.name, name, values)


def test_cantilever():
    out = run("cantilever")
    check(out["units"], {"unit_system": "metric", "us_mentions": 0})
    check(out["safety"], {"safety_factor": "1.5", "safety_factor_mentioned": True,
                          "safety_factor_values": ["1.5"]})
    check(out["standards"], {
        "standards_cited": True, "standard_bodies": ["EN", "Eurocode"],
        "standards": ["EN 10025-2", "EN 1993-1-1", "Eurocode 3"]})
    check(out["checks"], {
        "checks": ["bending", "buckling", "deflection", "shear", "yield"],
        "spring_end_type": "no-spring", "stress_correction": "no-spring"})
    check(out["materials"], {"materials": ["steel"]})
    check(out["cad"], {"cad_format": "none", "cad_formats": []})
    check(out["quantities"], {"supply_voltage": "not-stated",
                              "pipe_roughness_mm": "not-relevant",
                              "water_temperature_c": "not-relevant"})
    check(out["reply"], {"tables": 1, "largest_table_rows": 3, "list_items": 3})


def test_spring():
    out = run("spring")
    check(out["units"], {"unit_system": "us-customary", "metric_mentions": 0})
    check(out["safety"], {"safety_factor": "1.5"})
    check(out["standards"], {"standards": ["ASTM A313"],
                             "standard_bodies": ["ASTM"]})
    check(out["checks"], {
        "checks": ["coil-bind", "fatigue", "shear"],
        "spring_end_type": "squared-and-ground", "stress_correction": "wahl"})
    check(out["materials"], {"materials": ["stainless-steel"]})


def test_bracket():
    out = run("bracket")
    check(out["cad"], {"cad_format": "openscad", "cad_formats": ["openscad"],
                       "code_languages": ["openscad"],
                       "cad_parameters": ["arm=150", "thickness=5", "wall=120",
                                          "width=30"]})
    check(out["units"], {"unit_system": "metric"})
    check(out["materials"], {"materials": ["petg"]})
    check(out["standards"], {"standards": ["ISO 4762"]})
    check(out["safety"], {"safety_factor": "none",
                          "safety_factor_mentioned": False})
    check(out["checks"], {"checks": ["bending", "deflection"]})


def test_pipe():
    out = run("pipe")
    check(out["quantities"], {"supply_voltage": "12",
                              "pipe_roughness_mm": "0.0015",
                              "water_temperature_c": "20"})
    check(out["materials"], {"materials": ["polyethylene"]})
    check(out["units"], {"unit_system": "metric", "us_mentions": 1})
    check(out["checks"], {"checks": ["cavitation"]})
    check(out["safety"], {"safety_factor": "none"})


def test_negative():
    out = run("negative")
    check(out["units"], {"unit_system": "none"})
    check(out["standards"], {"standards": [], "standards_cited": False})
    check(out["checks"], {"checks": [], "spring_end_type": "no-spring"})
    check(out["safety"], {"safety_factor": "none"})
    check(out["materials"], {"materials": []})


@pytest.mark.parametrize("text, expected", [
    ("Use a factor of safety of 2.", "2"),
    ("Safety factor: **2.5**", "2.5"),
    ("| Safety factor | 3 |", "3"),
    ("A 2× safety factor is applied.", "2"),
    ("Take a design factor n = 4.", "4"),
    (r"Safety factor $n = 3$ on yield.", "3"),
    (r"$SF = 1.5$", "1.5"),
    ("A safety factor of 1.5 to 2 is usual.", "range"),
    ("Safety factor of 2 on yield, and a safety factor of 3 for the screws.",
     "several"),
    ("The actual safety factor is 4.2.", None),
    ("SF = 275/92 = 2.99", None),
    ("Apply a safety factor.", None),
    ("The ratio is 2.", "none"),
    ("This is safe, by a factor of 2.", "none"),
])
def test_safety_factor(text, expected):
    assert reply(text)["safety"]["safety_factor"] == expected


@pytest.mark.parametrize("text, expected", [
    ("A plate 100 mm × 50 mm carrying 20 N.", "metric"),
    ('A 6" x 4" plate, 1/4 in thick, carries 40 lb.', "us-customary"),
    ("It is 6 in. long (152 mm) and carries 40 lb (178 N).", "both"),
    ("There are 3 in the box and 2 in a bag.", "none"),
    ('Set the value to "3" and run it.', "none"),
    ("The motor turns at 1725 rpm on 12 V.", "none"),
])
def test_unit_system(text, expected):
    assert reply(text)["units"]["unit_system"] == expected


@pytest.mark.parametrize("text, expected", [
    ("The spring coil has closed and ground ends.", "squared-and-ground"),
    ("Use squared ends on the spring wire.", "squared"),
    ("The spring coil has plain ends.", "plain"),
    ("The spring has squared and ground ends; plain ends were rejected.",
     "several"),
    ("Spring wire. End type: plain ground. Squared and ground is dearer.",
     "plain-and-ground"),
    ("A spring of 8 coils.", "not-stated"),
    ("A bracket.", "no-spring"),
])
def test_spring_end_type(text, expected):
    assert reply(text)["checks"]["spring_end_type"] == expected


@pytest.mark.parametrize("text, expected", [
    ("Made to DIN 2095 and ISO 10243.", ["DIN 2095", "ISO 10243"]),
    ("Chain to ANSI B29.1; motor frame NEMA 23.", ["ANSI B29.1", "NEMA 23"]),
    ("BS EN ISO 4017 bolts.", ["BS EN ISO 4017"]),
    ("AISI 1018 steel, 6061-T6, A36.", []),
    ("Open 3 items in section 2.", []),
])
def test_standard_designations(text, expected):
    assert reply(text)["standards"]["standards"] == expected


def test_cad_formats_from_python_and_untagged_blocks():
    out = reply("```python\nimport cadquery as cq\nthickness = 6\n```\n"
                "```\n0\nSECTION\n2\nENTITIES\n```\n")
    check(out["cad"], {"cad_format": "several",
                       "cad_formats": ["cadquery", "dxf"],
                       "cad_parameters": ["thickness=6"]})


def test_cad_parameters_of_a_cadquery_file():
    record = {"raw_response": "see file", "prompt_text": "p", "files": []}
    out = run_inputs(Inputs([InputFile(
        "part.py", b"import cadquery as cq\nthickness = 6\narm = 120.0\n")],
        record=record))
    check(out["cad"], {"cad_format": "cadquery",
                       "cad_parameters": ["arm=120", "thickness=6"]})


def test_empty_text_is_no_input():
    assert all(v == {"status": "no-input"} for v in run_inputs(Inputs(())).values())
