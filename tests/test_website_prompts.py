"""The website prompt set in prompts/website/ (T1.1). No network.

The checks are mechanical and cannot prove that a prompt carries no hint: the
human-written rules are in prompts/website/README.md, and T1.2 reviews each
prompt by reading it.
"""

import hashlib
import json
import re
from difflib import SequenceMatcher
from functools import cache
from itertools import combinations
from pathlib import Path

import pytest

from runner.prompts import load_prompts
from runner.record import LEVELS, WORDINGS

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "prompts" / "website"

# Each task's prompt-set version and a fingerprint of its 6 texts as sent.
# A text change must raise the version (see prompts/website/README.md); then
# update both values here. The test prints the new fingerprint.
EXPECTED = {
    "bakery-landing": ("1", "ac10f30b65735956"),
    "dashboard": ("1", "8ed1eda7b7d2c95a"),
    "event-page": ("1", "b921700e205e3928"),
    "portfolio": ("1", "7e9cdc05dcc1c314"),
    "pricing-page": ("1", "1fe304fb08b96bd4"),
    "todo-app": ("1", "fdb45b811f9368af"),
}

# Words that every prompt of a task uses, so the levels ask for the same thing.
SUBJECT = {
    "bakery-landing": "bakery",
    "dashboard": "dashboard",
    "event-page": "event",
    "portfolio": "portfolio",
    "pricing-page": "pricing page",
    "todo-app": "to-do list",
}

# L0 and L1 must not name or imply a look, a component or a technology. A
# plural or "-es" form of each word is caught too.
STYLE_WORDS = """
    style styled stylish aesthetic look feel vibe theme design designed
    modern minimal minimalist clean sleek simple elegant beautiful stunning
    pretty attractive fancy polished professional rustic vintage retro classic
    bold playful fun cozy cosy warm cool bright calm friendly cheerful luxury
    luxurious premium upscale cute creative artisan artisanal handmade
    color colour colorful colourful palette hue tone gradient shade shadow
    dark light black white grey gray red orange yellow green blue purple
    violet indigo pink brown beige cream gold silver teal navy pastel neon
    monochrome
    font typeface typography serif sans monospace italic
    layout grid column sidebar navbar nav navigation menu hero header footer
    banner card button modal tab carousel slider accordion table form section
    widget icon emoji logo brand branding image photo picture illustration
    animation animated chart graph responsive mobile desktop
""".split()

# No prompt at any level asks for a format or a technology.
TECH_WORDS = """
    html css javascript typescript js jsx tsx react vue svelte angular
    next.js nextjs nuxt tailwind bootstrap jquery node npm framework library file
    single-file cdn localstorage python php
""".split()

# Colour and type words, compared between the two L2 wordings.
LOOK_WORDS = """
    black white grey gray red orange yellow green blue purple violet indigo
    pink brown beige cream teal lilac charcoal oxblood navy gold silver
    serif sans slab monospace typewriter condensed didone humanist geometric
    grotesque script gradient shadow rounded square light dark
""".split()


def word_pattern(words):
    alternatives = "|".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?:e?s)?(?![\w-])",
                      re.IGNORECASE)


STYLE = word_pattern(STYLE_WORDS)
TECH = word_pattern(TECH_WORDS)
NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\d{3}-\d{4}")
QUOTED = re.compile(r"[\"“]([^\"”\n]+)[\"”]")
CAPITALIZED = re.compile(r"\b[A-Z][A-Za-z]+\b")


@cache
def tasks():
    return {task.task_id: task for task in load_prompts([FOLDER])}


def fingerprint(task):
    sent = json.dumps(task.variants(), ensure_ascii=False)
    return hashlib.sha256(sent.encode("utf-8")).hexdigest()[:16]


def cells():
    return [(task_id, level) for task_id in sorted(EXPECTED) for level in LEVELS]


def texts(level_filter=LEVELS):
    return [(task_id, level, wording, task.text(level, wording))
            for task_id, task in sorted(tasks().items())
            for level in level_filter for wording in WORDINGS]


def text_id(item):
    return "-".join(item[:3])


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def look_words(text):
    found = set(words(text.replace("-", " ")))
    return {w for w in LOOK_WORDS if w in found or w + "s" in found}


def mid_sentence_names(text):
    """Capitalised words that are not the first word of a sentence or line."""
    names = set()
    for match in CAPITALIZED.finditer(text):
        before = text[:match.start()].rstrip(" \"“(")
        line = before.rsplit("\n", 1)[-1].strip()
        if before and not before.endswith(("\n", ".", "!", "?", ":")) \
                and line not in ("-", "*"):
            names.add(match.group())
    return names


# --- the set as a whole ------------------------------------------------------


def test_six_tasks_three_levels_two_wordings():
    assert sorted(tasks()) == sorted(EXPECTED)
    assert all(task.project_type == "website" for task in tasks().values())
    variants = [v for task in tasks().values() for v in task.variants()]
    assert len(variants) == 6 * 3 * 2 == 36
    assert {(level, wording) for task in tasks().values()
            for level, wording, _ in task.variants()} == {
        (level, wording) for level in LEVELS for wording in WORDINGS}


def test_each_task_has_its_pinned_version_and_text():
    actual = {task_id: (task.prompt_set_version, fingerprint(task))
              for task_id, task in tasks().items()}
    assert actual == EXPECTED, (
        "a prompt text changed: raise prompt_set_version in that file and "
        f"set EXPECTED to {actual}")


def test_each_file_records_its_l2_direction():
    for path in sorted(FOLDER.glob("*.yaml")):
        assert "# L2 direction:" in path.read_text(encoding="utf-8"), path.name


def test_l2_directions_differ_between_tasks():
    looks = {task_id: frozenset(look_words(task.text("L2", "A")))
             for task_id, task in tasks().items()}
    for first, second in combinations(sorted(looks), 2):
        assert looks[first] != looks[second], (first, second)


# --- every prompt -----------------------------------------------------------


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_every_level_keeps_the_task_subject(item):
    task_id, _, _, text = item
    assert SUBJECT[task_id] in text.lower()


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_no_prompt_asks_for_a_format_or_technology(item):
    assert TECH.findall(item[3]) == []


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_contact_details_are_reserved_examples(item):
    text = item[3]
    assert all(email.endswith("@example.com") for email in EMAIL.findall(text))
    assert all(phone.startswith("555-01") for phone in PHONE.findall(text))
    assert "http" not in text and "www." not in text


@pytest.mark.parametrize("item", texts(("L0", "L1")), ids=text_id)
def test_l0_and_l1_name_no_style_component_or_look(item):
    assert STYLE.findall(item[3]) == []


@pytest.mark.parametrize("item", texts(("L0", "L1")), ids=text_id)
def test_l0_and_l1_hold_no_invented_details(item):
    text = item[3]
    assert NUMBER.findall(text) == [] and EMAIL.findall(text) == []
    assert QUOTED.findall(text) == []


@pytest.mark.parametrize("task_id", sorted(EXPECTED))
@pytest.mark.parametrize("wording", WORDINGS)
def test_each_level_is_longer_than_the_last(task_id, wording):
    lengths = [len(tasks()[task_id].text(level, wording)) for level in LEVELS]
    assert lengths == sorted(lengths) and len(set(lengths)) == 3


# --- the two wordings of a cell ----------------------------------------------


# Word-sequence similarity a pair must stay under. L2 pairs share every fact,
# so they are allowed more overlap.
MAX_SIMILARITY = {"L0": 0.7, "L1": 0.7, "L2": 0.75}


@pytest.mark.parametrize("task_id,level", cells())
def test_the_two_wordings_differ_in_phrasing(task_id, level):
    task = tasks()[task_id]
    a, b = words(task.text(level, "A")), words(task.text(level, "B"))
    assert a != b
    ratio = SequenceMatcher(None, a, b, autojunk=False).ratio()
    assert ratio < MAX_SIMILARITY[level]


@pytest.mark.parametrize("task_id", sorted(EXPECTED))
def test_the_two_l2_wordings_carry_the_same_facts(task_id):
    task = tasks()[task_id]
    a, b = task.text("L2", "A"), task.text("L2", "B")
    for pattern in (NUMBER, EMAIL, QUOTED):
        assert set(pattern.findall(a)) == set(pattern.findall(b)), pattern
    assert look_words(a) == look_words(b)
    for text, other in ((a, b), (b, a)):
        missing = {name for name in mid_sentence_names(text)
                   if not re.search(rf"\b{name}\b", other)}
        assert missing == set()


# --- the checks themselves ---------------------------------------------------


@pytest.mark.parametrize("text", [
    "Make a modern website for a bakery.",
    "Make a website with a dark theme.",
    "Make a bakery site with cards and a hero.",
    "Make a website in pastel colours.",
    "Use a serif font.",
])
def test_the_style_check_catches_a_hint(text):
    assert STYLE.findall(text)


@pytest.mark.parametrize("text", [
    "Make it a single HTML file.",
    "Use React and Tailwind.",
    "Build it with Next.js.",
    "Keep everything in localStorage.",
])
def test_the_technology_check_catches_a_request(text):
    assert TECH.findall(text)


def test_mid_sentence_names_skip_first_words():
    text = "Make a page.\n- Owners: Ana Ruiz.\nOpen on Friday. Closed Monday."
    assert mid_sentence_names(text) == {"Ruiz", "Friday", "Monday"}
