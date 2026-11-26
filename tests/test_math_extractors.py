"""The math extractors on hand-made fixtures with known values (T2.8).

Fixtures are in tests/fixtures/math/. Each expected value was worked out by
reading the fixture.
"""

from pathlib import Path

import pytest

from extractors.base import InputFile, Inputs, run_extractors
from extractors.registry import extractors_for
from runner.files import extract_files

FIXTURES = Path(__file__).parent / "fixtures" / "math"
MATH = extractors_for("math")


def run_inputs(inputs):
    results = run_extractors(MATH, inputs)
    return {full.split(".", 1)[1]: values for full, (_, values) in results.items()}


def run(name):
    return run_inputs(Inputs.from_directory(FIXTURES / name))


def reply(text, prompt="Work it out."):
    record = {"raw_response": text, "prompt_text": prompt, "files": []}
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


def test_loan():
    out = run("loan")
    check(out["currency"], {"currency": ["$"]})
    check(out["notation"], {"notation": ["latex"], "main_notation": "latex",
                            "has_formula": True})
    check(out["code"], {"code_present": False, "code_languages": [],
                        "plot_code": False, "plot_libraries": []})
    check(out["precision"], {"result_sig_figs": "5+", "result_decimals": "2",
                             "long_decimals": False})
    check(out["voice"], {"address": "you"})
    check(out["methods"], {"methods": ["annuity-formula"]})
    check(out["units"], {"unit_system": "none", "unit_style": "none"})
    check(out["constants"], {"g_value": "not-relevant", "ka_value": "not-relevant"})
    check(out["reply"], {"headings": 1, "tables": 1, "largest_table_rows": 3,
                         "code_blocks": 0})


def test_projectile():
    out = run("projectile")
    check(out["constants"], {
        "projectile_mass": "0.145 kg", "projectile_diameter": "0.074 m",
        "drag_coefficient": "0.47", "air_density": "1.225", "g_value": "9.81",
        "ka_value": "not-relevant", "kw_value": "not-relevant"})
    check(out["code"], {"code_present": True, "code_languages": ["python"],
                        "plot_code": True, "plot_libraries": ["matplotlib"]})
    check(out["methods"], {"methods": ["closed-form", "numerical", "ode-solver",
                                       "runge-kutta"]})
    check(out["precision"], {"result_sig_figs": "3"})
    check(out["notation"], {"main_notation": "latex"})
    check(out["voice"], {"address": "we"})
    check(out["units"], {"unit_system": "metric", "unit_style": "slash"})
    check(out["currency"], {"currency": []})


def test_titration():
    out = run("titration")
    check(out["constants"], {"ka_value": "1.8e-05", "pka_value": "4.74",
                             "kw_value": "1e-14", "g_value": "not-relevant"})
    check(out["notation"], {"notation": ["unicode"], "main_notation": "unicode"})
    check(out["methods"], {"methods": ["henderson-hasselbalch"]})
    check(out["units"], {"unit_style": "exponent",
                         "concentration_notation": ["mol-per-litre-exponent"]})
    check(out["code"], {"code_present": False})
    check(out["reply"], {"tables": 1, "largest_table_rows": 4})
    check(out["currency"], {"currency": []})


def test_hypothesis():
    out = run("hypothesis")
    check(out["methods"], {"methods": ["normality", "p-value", "shapiro-wilk",
                                       "t-test"]})
    check(out["notation"], {"notation": ["plain"], "main_notation": "plain"})
    check(out["code"], {"code_present": True, "code_languages": ["r"],
                        "plot_code": False})
    check(out["currency"], {"currency": []})


def test_entropy():
    out = run("entropy")
    check(out["methods"], {"methods": ["boltzmann", "disorder", "microstates",
                                       "second-law"]})
    check(out["voice"], {"address": "you"})
    check(out["reply"], {"headings": 2, "tables": 0})
    check(out["precision"], {"result_sig_figs": None})


@pytest.mark.parametrize("text, expected", [
    ("The payment is $178.21 and the fee is $50.", ["$"]),
    ("Pay \\$178.21 on the loan.", ["$"]),
    ("A loan of $9,000 to $10,000.", ["$"]),
    ("The loan: let $P = 9000$ and $r$ be the rate.", ["none"]),
    ("The loan payment is 178.21.", ["none"]),
    ("The loan payment is £178.21 (GBP).", ["GBP", "£"]),
    ("Interest of 20 euros on the loan.", ["euros"]),
    ("The slope is $m = 2$.", []),
])
def test_currency_is_not_confused_with_math(text, expected):
    assert reply(text)["currency"]["currency"] == expected


@pytest.mark.parametrize("text, expected", [
    ("**Answer: 36.8 m**", "3"),
    ("**x = 2.0**", "2"),
    ("**Step 3**\n\n**Range = 36.82 m**", "4"),
    ("**25 m/s** and **30°** are given.", None),
    ("**Slope = 1.9464**, **intercept = 0.21**", "mixed"),
    ("So $\\boxed{t = 1.64 \\times 10^{3}}$ s.", "3"),
    ("The range is ≈ 36.8 m.", "3"),
])
def test_precision_of_results(text, expected):
    prompt = "Launched at 25 m/s and 30° above the horizontal."
    assert reply(text, prompt)["precision"]["result_sig_figs"] == expected


def test_a_full_precision_dump_is_seen():
    assert reply("x = 36.81234567")["precision"]["long_decimals"] is True


def test_plain_text_blocks_are_working_and_code_is_not():
    out = reply("```text\ny = 2x^2\n```\n```python\nz = 3 ** 2\n```\n")
    check(out["notation"], {"notation": ["plain"]})
    check(out["code"], {"code_present": True, "code_languages": ["python"]})


def test_constants_need_their_context():
    out = reply("The titration uses 5 g = 5000 mg of acid.")
    check(out["constants"], {"ka_value": "not-stated", "g_value": "not-relevant"})
    out = reply("With air resistance: mass 145 g, diameter 7.4 cm, C_d = 0.3; "
                "later C_d = 0.5.")
    check(out["constants"], {"projectile_mass": "0.145 kg",
                             "projectile_diameter": "0.074 m",
                             "drag_coefficient": "several", "g_value": "not-stated"})


def test_code_blocks_without_stored_files_leave_code_undetermined():
    record = {"raw_response": "```python\nx = 1\n```", "prompt_text": "p",
              "files": []}
    out = run_inputs(Inputs((), record=record))
    assert out["code"]["code_present"] is None


def test_empty_text_is_no_input():
    assert all(v == {"status": "no-input"} for v in run_inputs(Inputs(())).values())
