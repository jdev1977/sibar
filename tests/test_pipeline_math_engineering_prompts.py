"""The pipeline, math and engineering prompt sets (T2.1). No network.

The rules are in docs/leak-check.md and each type's README. The checks are
mechanical: the word lists catch known hints, and only reading catches new
ones. Shared matching lives in tests/prompt_checks.py.

Math and engineering tasks carry "givens": the numbers a checkable question
cannot be asked without. Every prompt of a task contains its givens word for
word, and L0 and L1 contain no other number.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from prompt_checks import (BRITISH, EMAIL, NUMBER, PHONE, QUOTED,
                           fact_problems, fingerprint, please_count,
                           similarity, word_pattern, words)
from runner.prompts import load_prompts
from runner.record import KNOWN_PROJECT_TYPES, LEVELS, WORDINGS

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PromptSet:
    # task_id -> (prompt_set_version, fingerprint of its 6 texts as sent).
    # Any text change fails the test until this is updated; raise the
    # version in the same change (see the type's README).
    expected: dict
    # task_id -> words every prompt of the task contains.
    subject: dict
    # task_id -> invented names and fixed terms both L2 wordings contain.
    names: dict
    # task_id -> the givens: exact strings in every prompt of the task.
    givens: dict
    # How wording A may open. Wording B always opens "Can you ".
    openings: tuple
    # Words L0 and L1 must not use: the type's open choices.
    hints: re.Pattern
    # Common defaults an L2 must not name, not even to forbid them.
    named_defaults: re.Pattern


# --- word lists ---------------------------------------------------------------

# Pipeline open choices (plan.md): language, libraries, structure, config,
# error handling, logging, retries, tests, scheduling, storage, docs.
PIPELINE_HINTS = """
    python javascript typescript node nodejs java rust golang ruby perl php
    bash shell powershell sql sqlite postgres postgresql mysql mongodb duckdb
    redis pandas polars numpy httpx aiohttp pillow pil imagemagick opencv
    airflow prefect dagster luigi cron crontab scheduler systemd docker
    kubernetes github gitlab jenkins circleci yaml json toml xml parquet
    library libraries framework script scripts module modules function
    functions class classes cli command-line argparse config configuration
    logging logger retry retries backoff test testing unittest pytest
    docstring comment readme robust production production-ready scalable
    efficient modular simple async parallel concurrent multiprocessing
    exception
""".split() + ["error handling", "single file", "one file", "environment variable"]

PIPELINE_DEFAULTS = """
    python pandas numpy pillow pil airflow cron crontab sqlite postgres
    postgresql docker github pytest unittest argparse
""".split()

# Math open choices: method, steps, assumptions, units and figures,
# notation, checking, structure, analogies, plots, code.
MATH_HINTS = """
    numerical numerically numeric analytic analytical analytically
    closed-form exact exactly approximate approximately approximation euler
    runge kutta rk4 heun simulate simulation iterative iteration code coding
    program programming python matlab octave excel spreadsheet julia
    calculator plot plotted graph chart table diagram sketch visualize
    visualization latex markdown heading bullet step-by-step step derive
    derivation proof prove rigorous detailed brief briefly short concise
    simple simply intuitive intuition analogy analogies example t-test
    z-test wilcoxon parametric nonparametric non-parametric one-sided
    two-sided one-tailed two-tailed significance significant alpha p-value
    confidence normal normality regression matrix formula formulas equation
    differential ode decimal round rounded rounding units si metric imperial
    disorder messy boltzmann logarithm check checked verify drag linear
    quadratic vacuum
""".split() + ["significant figures"]

MATH_DEFAULTS = """
    python matplotlib numpy scipy latex disorder messy untidy tidy heading
    bullet t-test plot code
""".split() + ["t test"]

# Engineering open choices: unit system, material, safety factor, loads,
# standards, formula source, checks, tolerances, drawing or CAD format.
ENGINEERING_HINTS = """
    steel aluminum aluminium wood wooden timber plywood plastic pla nylon
    brass bronze copper titanium stainless iron carbon composite material
    alloy safety margin standard code iso din ansi asme astm aisc eurocode
    sae metric imperial inch inches ft feet lb lbs lbf pound psi ksi kip gpm
    stress deflection buckling fatigue yield tolerance manufacturability
    manufacturing machined machining printed printing laser cnc weld welded
    welding step stl dxf dwg iges openscad freecad solidworks fusion autocad
    onshape drawing sketch catalog catalogue off-the-shelf commercial brand
    vendor supplier disclaimer engineer fan fin finned extruded extrusion
    forced convection darcy weisbach hazen colebrook moody pvc polyethylene
    centrifugal submersible worm helical spur gearbox pulley sprocket chain
    timing coil wire gusset brace l-shaped triangular simple cheap low-cost
    lightweight strong sturdy robust heavy-duty optimal optimized 3d
""".split() + ["safety factor", "factor of safety", "music wire"]

ENGINEERING_DEFAULTS = """
    fin finned fan extruded extrusion gusset i-beam wide-flange worm darcy
    colebrook moody openscad stl pla disclaimer consult
""".split() + ["music wire", "professional engineer", "structural steel"]

# Engineering outputs are study data, not designs: no prompt at any level
# frames a task as something people's safety depends on.
SAFETY_WORDS = """
    people person passenger child children human balcony staircase railing
    handrail hoist crane harness vehicle car aircraft boiler medical
    climbing swing
""".split() + ["pressure vessel", "life-safety"]

# Any type, any level: no spelled-out count at L0 and L1 (numbers are
# givens or absent), and no ban written into an L2 (docs/leak-check.md).
NUMBER_WORDS = word_pattern("""
    two three four five six seven eight nine ten eleven twelve hundred
    thousand dozen
""".split())
BAN = re.compile(r"\b(?:do not|don't|avoid|instead of|rather than|never)\b",
                 re.IGNORECASE)
URL = re.compile(r"https?://([^/\s]+)")
IP = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
DOC_IP_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")
INCHES = re.compile(r"\d in\b")


SETS = {
    "pipeline": PromptSet(
        expected={
            "ci-workflow": ("1", "52e01976b8258add"),
            "csv-to-database": ("1", "e258fe725bbc7c3c"),
            "daily-api-fetch": ("1", "37ab96b8d765524b"),
            "data-validation": ("1", "a4ec9976ba36b92e"),
            "image-resize": ("1", "5be23bf811b99a95"),
            "log-aggregation": ("1", "4e0866ef57fc5434"),
        },
        subject={
            "ci-workflow": "continuous integration",
            "csv-to-database": "csv",
            "daily-api-fetch": "api",
            "data-validation": "valid",
            "image-resize": "resize",
            "log-aggregation": "log",
        },
        names={
            "ci-workflow": ["tallyfold", "Go", "CHANGELOG.md"],
            "csv-to-database": ["Brindlecote Tea", "orders-2027-03.csv"],
            "daily-api-fetch": ["Quellmouth", "Clean Air Group",
                                "api.example.com", "X-Api-Key"],
            "data-validation": ["Ostley Valley Weather Network",
                                "stations.csv"],
            "image-resize": ["Saltmarsh Pottery"],
            "log-aggregation": ["Fernhollow Recipes", "access.log"],
        },
        givens={},
        openings=("Write ",),
        hints=word_pattern(PIPELINE_HINTS),
        named_defaults=word_pattern(PIPELINE_DEFAULTS),
    ),
    "math": PromptSet(
        expected={
            "entropy-explanation": ("1", "4d9ec47968080661"),
            "hypothesis-test": ("1", "a0f6dfafc4bb7a85"),
            "least-squares-fit": ("1", "a0fcfb2f0ccfc30d"),
            "loan-amortization": ("1", "311262c3458aee00"),
            "projectile-drag": ("1", "083e88af469e2b2f"),
            "titration-curve": ("1", "68bf8c981ab55e90"),
        },
        subject={
            "entropy-explanation": "entropy",
            "hypothesis-test": "mean",
            "least-squares-fit": "straight line",
            "loan-amortization": "loan",
            "projectile-drag": "projectile",
            "titration-curve": "ph curve",
        },
        names={
            "entropy-explanation": ["Maya"],
            "hypothesis-test": ["Pellmore Machine Works", "Wilcoxon"],
            "least-squares-fit": ["Sxx", "Sxy"],
            "loan-amortization": ["April 1, 2027"],
            "projectile-drag": ["Heun"],
            "titration-curve": ["Ka", "Kw"],
        },
        givens={
            "hypothesis-test": (
                "50.8, 51.6, 49.7, 52.3, 51.1, 50.4, 52.0, 51.5", "from 50"),
            "least-squares-fit": (
                "(1, 2.3), (2, 4.1), (3, 5.8), (4, 8.2), (5, 9.9), "
                "(6, 11.6), (7, 14.1)",),
            "loan-amortization": ("9000", "7%", "5 years"),
            "projectile-drag": ("25 m/s", "30°"),
            "titration-curve": ("25.0 mL", "0.100 M acetic acid",
                                "0.100 M sodium hydroxide"),
        },
        openings=("Work out ", "Test ", "Fit ", "Explain "),
        hints=word_pattern(MATH_HINTS),
        named_defaults=word_pattern(MATH_DEFAULTS),
    ),
    "engineering": PromptSet(
        expected={
            "cantilever-beam": ("1", "b1796a32db300772"),
            "compression-spring": ("1", "74f2b7e59378129b"),
            "conveyor-gear-ratio": ("1", "9c64524567a4382b"),
            "heat-sink": ("1", "19c4af351a5aff5b"),
            "pipe-and-pump": ("1", "788c9e51d7e7cdc5"),
            "shelf-bracket": ("1", "040bba9ef5a76bf2"),
        },
        subject={
            "cantilever-beam": "beam",
            "compression-spring": "compression spring",
            "conveyor-gear-ratio": "gear ratio",
            "heat-sink": "heat sink",
            "pipe-and-pump": "pressure drop",
            "shelf-bracket": "bracket",
        },
        names={
            "cantilever-beam": ["6061-T6"],
            "compression-spring": ["type 302 stainless steel"],
            "conveyor-gear-ratio": ["1725 rpm"],
            "heat-sink": ["copper plate"],
            "pipe-and-pump": ["Wickley Lane Community Garden",
                              "Hazen-Williams"],
            "shelf-bracket": ["birch plywood"],
        },
        givens={
            "cantilever-beam": ("1.5 m", "4 kN"),
            "conveyor-gear-ratio": ("0.4 m/s", "150 mm"),
            "heat-sink": ("20 W", "1.0 °C/W", "125 °C", "40 °C"),
            "pipe-and-pump": ("1.5 L/s", "6 m", "35 m", "40 mm"),
        },
        openings=("Size ", "Work out ", "Design "),
        hints=word_pattern(ENGINEERING_HINTS),
        named_defaults=word_pattern(ENGINEERING_DEFAULTS),
    ),
}

SAFETY = word_pattern(SAFETY_WORDS)
# Engineering tasks whose L0 and L1 give no numbers, so the unit system is
# a choice being measured. Their L2 gives US customary units, pointing away
# from the expected metric default.
UNITS_OPEN = ("compression-spring", "shelf-bracket")


# --- helpers ------------------------------------------------------------------


@cache
def tasks(type_name):
    return {task.task_id: task
            for task in load_prompts([ROOT / "prompts" / type_name])}


def givens(type_name, task_id):
    return SETS[type_name].givens.get(task_id, ())


def without_givens(type_name, task_id, text):
    for given in givens(type_name, task_id):
        text = text.replace(given, " ")
    return text


def all_tasks():
    return [(type_name, task_id) for type_name in sorted(SETS)
            for task_id in sorted(SETS[type_name].expected)]


def texts(level_filter=LEVELS, types=tuple(SETS)):
    return [(type_name, task_id, level, wording,
             tasks(type_name)[task_id].text(level, wording))
            for type_name, task_id in all_tasks() if type_name in types
            for level in level_filter for wording in WORDINGS]


def text_id(item):
    return "-".join(item[:4])


TASK_IDS = ["-".join(pair) for pair in all_tasks()]


# --- each set as a whole ------------------------------------------------------


@pytest.mark.parametrize("type_name", sorted(SETS))
def test_each_folder_is_a_project_type_the_records_accept(type_name):
    assert type_name in KNOWN_PROJECT_TYPES


@pytest.mark.parametrize("type_name", sorted(SETS))
def test_six_tasks_three_levels_two_wordings(type_name):
    found = tasks(type_name)
    spec = SETS[type_name]
    assert sorted(found) == sorted(spec.expected)
    assert all(task.project_type == type_name for task in found.values())
    pairs = [(level, wording) for task in found.values()
             for level, wording, _ in task.variants()]
    assert len(pairs) == 6 * 3 * 2 == 36
    assert set(pairs) == {(l, w) for l in LEVELS for w in WORDINGS}
    for table in (spec.subject, spec.names):
        assert sorted(table) == sorted(spec.expected)
    assert set(spec.givens) <= set(spec.expected)


@pytest.mark.parametrize("type_name", sorted(SETS))
def test_each_task_has_its_pinned_version_and_text(type_name):
    actual = {task_id: (task.prompt_set_version, fingerprint(task))
              for task_id, task in tasks(type_name).items()}
    assert actual == SETS[type_name].expected, (
        "a prompt text changed: raise prompt_set_version in that file and "
        f"set expected to {actual}")


@pytest.mark.parametrize("type_name,task_id", all_tasks(), ids=TASK_IDS)
def test_each_file_records_its_design(type_name, task_id):
    """Every file names its L2 direction; math and engineering files also
    say what their givens are and what is checkable at which level."""
    source = tasks(type_name)[task_id].path.read_text(encoding="utf-8")
    assert "# L2 direction:" in source
    if type_name != "pipeline":
        assert "# Givens" in source and "# Checkable:" in source


# --- every prompt -------------------------------------------------------------


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_every_level_keeps_the_task_subject(item):
    type_name, task_id, _, _, text = item
    assert SETS[type_name].subject[task_id] in text.lower()


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_every_prompt_holds_the_givens_word_for_word(item):
    type_name, task_id, _, _, text = item
    for given in givens(type_name, task_id):
        assert given in text


@pytest.mark.parametrize("item", texts(("L0", "L1")), ids=text_id)
def test_l0_and_l1_name_none_of_the_open_choices(item):
    type_name, _, _, _, text = item
    assert SETS[type_name].hints.findall(text) == []


@pytest.mark.parametrize("item", texts(("L0", "L1")), ids=text_id)
def test_l0_and_l1_hold_no_number_beyond_the_givens(item):
    type_name, task_id, _, _, text = item
    rest = without_givens(type_name, task_id, text)
    assert NUMBER.findall(rest) == []
    assert NUMBER_WORDS.findall(rest) == []
    assert QUOTED.findall(text) == [] and EMAIL.findall(text) == []
    assert URL.findall(text) == []


@pytest.mark.parametrize("item", texts(("L2",)), ids=text_id)
def test_l2_names_no_default_to_forbid_it(item):
    type_name, _, _, _, text = item
    assert BAN.findall(text) == []
    assert SETS[type_name].named_defaults.findall(text) == []


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_every_prompt_uses_us_spelling(item):
    assert BRITISH.findall(item[4]) == []


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_invented_contact_details_and_addresses_are_reserved(item):
    text = item[4]
    assert all(email.lower().endswith("@example.com")
               for email in EMAIL.findall(text))
    assert all(phone.startswith("555-01") for phone in PHONE.findall(text))
    assert all(host == "example.com" or host.endswith(".example.com")
               for host in URL.findall(text))
    assert "www." not in text
    assert all(ip.startswith(DOC_IP_PREFIXES) for ip in IP.findall(text))


@pytest.mark.parametrize("item", texts(types=("engineering",)), ids=text_id)
def test_no_engineering_prompt_frames_a_safety_critical_use(item):
    assert SAFETY.findall(item[4]) == []


@pytest.mark.parametrize("task_id", UNITS_OPEN)
def test_units_open_tasks_give_units_only_at_l2(task_id):
    task = tasks("engineering")[task_id]
    assert givens("engineering", task_id) == ()
    for wording in WORDINGS:
        assert INCHES.search(task.text("L2", wording))


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_each_wording_keeps_its_voice_at_every_level(item):
    """A is a command and B a request opening "Can you", the same way in
    every task of a type; B says "please" once at L2 and never below."""
    type_name, _, level, wording, text = item
    first_line = text.splitlines()[0]
    if wording == "A":
        assert text.startswith(SETS[type_name].openings)
        assert "?" not in first_line
    else:
        assert text.startswith("Can you ") and "?" in first_line
    assert please_count(text) == (1 if (level, wording) == ("L2", "B") else 0)


@pytest.mark.parametrize("type_name,task_id", all_tasks(), ids=TASK_IDS)
@pytest.mark.parametrize("wording", WORDINGS)
def test_each_level_is_longer_than_the_last(type_name, task_id, wording):
    task = tasks(type_name)[task_id]
    lengths = [len(task.text(level, wording)) for level in LEVELS]
    assert lengths == sorted(lengths) and len(set(lengths)) == 3


# --- the two wordings of a cell -----------------------------------------------


# Word-sequence similarity a pair must stay under, as for websites. The
# givens and any line found word for word in both (sample data such as CSV
# rows or log lines) are removed first: they are the same by design.
MAX_SIMILARITY = {"L0": 0.7, "L1": 0.7, "L2": 0.75}


def phrasing(type_name, task_id, text, other):
    shared = set(text.splitlines()) & set(other.splitlines()) - {""}
    kept = "\n".join(line for line in text.splitlines() if line not in shared)
    return without_givens(type_name, task_id, kept)


@pytest.mark.parametrize("type_name,task_id", all_tasks(), ids=TASK_IDS)
@pytest.mark.parametrize("level", LEVELS)
def test_the_two_wordings_differ_in_phrasing(type_name, task_id, level):
    task = tasks(type_name)[task_id]
    a, b = task.text(level, "A"), task.text(level, "B")
    a, b = phrasing(type_name, task_id, a, b), phrasing(type_name, task_id, b, a)
    assert words(a) != words(b)
    assert similarity(a, b) < MAX_SIMILARITY[level]


def l2_problems(type_name, task_id, a, b):
    """Differences in facts between the two L2 wordings. The givens are
    checked word for word elsewhere, so they are removed before numbers are
    compared in order; that lets B put the givens in its own order."""
    return fact_problems(without_givens(type_name, task_id, a),
                         without_givens(type_name, task_id, b),
                         SETS[type_name].names[task_id])


@pytest.mark.parametrize("type_name,task_id", all_tasks(), ids=TASK_IDS)
def test_the_two_l2_wordings_carry_the_same_facts(type_name, task_id):
    task = tasks(type_name)[task_id]
    assert l2_problems(type_name, task_id, task.text("L2", "A"),
                       task.text("L2", "B")) == []


# --- the checks themselves ----------------------------------------------------


@pytest.mark.parametrize("type_name,text", [
    ("pipeline", "Write a Python script that loads a CSV file."),
    ("pipeline", "Write a pipeline with logging and retries."),
    ("pipeline", "Write a pipeline that stores data in SQLite."),
    ("pipeline", "Write a pandas-based pipeline."),
    ("pipeline", "Write a pipeline with tests and a config file."),
    ("pipeline", "Write a pipeline with proper error handling."),
    ("math", "Solve it numerically."),
    ("math", "Work out the exact range and plot it."),
    ("math", "Use a t-test at the 5% level."),
    ("math", "Explain entropy as disorder, with an analogy."),
    ("math", "Work out the range with quadratic drag."),
    ("math", "Give the answer to three significant figures."),
    ("engineering", "Size a steel beam with a safety factor of 2."),
    ("engineering", "Design a bracket and give an STL file."),
    ("engineering", "Check stress and deflection to Eurocode."),
    ("engineering", "Design a spring in music wire."),
    ("engineering", "Size an extruded finned heat sink with a fan."),
    ("engineering", "Use the Darcy-Weisbach equation."),
])
def test_the_hint_check_catches_an_open_choice(type_name, text):
    assert SETS[type_name].hints.findall(text)


@pytest.mark.parametrize("type_name,text", [
    ("pipeline", "Write a pipeline that cleans a CSV file and loads it."),
    ("pipeline", "Can you set up continuous integration for a package?"),
    ("math", "Test whether the mean of these measurements differs from 50."),
    ("math", "Fit a straight line to these points by least squares."),
    ("engineering", "Size a beam that is fixed at one end."),
    ("engineering", "Work out the gear ratio for a conveyor belt."),
])
def test_the_hint_check_passes_the_task_itself(type_name, text):
    assert SETS[type_name].hints.findall(text) == []


@pytest.mark.parametrize("text", [
    "Do not use pandas.",
    "Use plain paragraphs rather than headings.",
    "Avoid code.",
    "Never add a disclaimer.",
])
def test_the_ban_check_catches_a_ban(text):
    assert BAN.findall(text)


@pytest.mark.parametrize("type_name,text", [
    ("pipeline", "Use the standard library, not pandas."),
    ("math", "Write it in Python with matplotlib."),
    ("math", "Explain it without the messy-room picture."),
    ("engineering", "A flat plate with no fins."),
    ("engineering", "Use carbon steel, not music wire."),
])
def test_the_named_default_check_catches_a_named_default(type_name, text):
    assert SETS[type_name].named_defaults.findall(text)


def test_the_safety_check_catches_a_safety_critical_use():
    assert SAFETY.findall("Size a beam for a balcony that holds people.")
    assert SAFETY.findall("Pick bolts for a pressure vessel flange.")
    assert SAFETY.findall("Size a beam fixed at one end.") == []


def test_givens_are_removed_before_numbers_are_counted():
    text = tasks("math")["loan-amortization"].text("L0", "A")
    assert NUMBER.findall(text) != []
    assert NUMBER.findall(without_givens("math", "loan-amortization",
                                         text)) == []


@pytest.mark.parametrize("type_name,task_id,old,new", [
    ("pipeline", "csv-to-database", "such as 1250", "such as 1205"),
    ("pipeline", "log-aggregation", "the first 5 shown",
     "the first 10 shown"),
    ("math", "projectile-drag", "0.1 s at a time",
     "0.2 s at a time"),
    ("math", "hypothesis-test", "a significance level of 1%",
     "a significance level of 5%"),
    ("engineering", "cantilever-beam", "no more than 15 mm",
     "no more than 10 mm"),
    ("engineering", "pipe-and-pump", "Wickley Lane", "Wickham Lane"),
])
def test_the_fact_check_catches_a_changed_fact(type_name, task_id, old, new):
    task = tasks(type_name)[task_id]
    a, b = task.text("L2", "A"), task.text("L2", "B")
    assert old in b
    assert l2_problems(type_name, task_id, a, b.replace(old, new, 1)) != []


def test_the_contact_checks_catch_real_addresses():
    assert URL.findall("GET https://api.weather.gov/x") == ["api.weather.gov"]
    assert not "10.0.0.7".startswith(DOC_IP_PREFIXES)
    assert IP.findall("ip=203.0.113.7 v1.4.0") == ["203.0.113.7"]
