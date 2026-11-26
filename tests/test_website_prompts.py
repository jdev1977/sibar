"""The website prompt set in prompts/website/ (T1.1, T1.2). No network.

The checks are mechanical and cannot prove that a prompt carries no hint: the
rules are in docs/leak-check.md, and the T1.2 leak check read each prompt (its
log is prompts/website/leak-check.md). The word lists here pin what that check
decided, so a later edit cannot quietly undo it.
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
# Any text change makes the test fail until this table is updated. The test
# cannot tell whether the version was raised: the rule in
# prompts/website/README.md is to raise it in the same change, and a reviewer
# checks that both values changed together. The test prints the new values.
EXPECTED = {
    "bakery-landing": ("1", "1e314bcd3421b4c3"),
    "dashboard": ("1", "11bfefd004088148"),
    "event-page": ("1", "b67708948325cfa9"),
    "portfolio": ("1", "02febb80532ee023"),
    "pricing-page": ("1", "349aef827233aede"),
    "todo-app": ("1", "dab31ae22594d6a6"),
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

# Invented names and labels that both L2 wordings of a task must contain.
NAMES = {
    "bakery-landing": ["Wrenmoor Bread Room", "Tanner Street", "Wrenmoor",
                       "Priya Halvorsen", "Dev Okafor"],
    "dashboard": ["Ostrey Food Bank"],
    "event-page": ["Fix-It Day", "Marrowick Tool Share",
                   "Marrowick Community Hall", "Ferry Road", "Rosa Imbert"],
    "portfolio": ["Joss Achterberg", "Fennlow", "Tideline"],
    "pricing-page": ["Billfinch", "Starter", "Solo", "Studio"],
    "todo-app": ["Term Planner", "HIST 210", "CHEM 101", "STAT 230",
                 "LIT 305", "Bauhaus"],
}

# L0 and L1 must not name or imply a look, a component or a technology. A
# plural or "-es" form of each word is caught too. The last line holds words
# that say how a page should read or that share a root with a page pattern
# (T1.2): "at a glance", "a quick overview", "compare the plans".
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
    glance overview compare comparison gallery showcase landing
""".split()

# No prompt at any level asks for a format or a technology. "single" alone is
# allowed ("a single oxblood red"), so its compounds are listed.
TECH_WORDS = """
    html css javascript typescript js jsx tsx react vue svelte angular
    next.js nextjs nuxt tailwind bootstrap jquery node npm framework library file
    single-file one-file single-page one-page multi-page cdn localstorage
    python php
""".split()

# Colour and type words, compared between the two L2 wordings.
LOOK_WORDS = """
    black white grey gray red orange yellow green blue purple violet indigo
    pink brown beige cream teal cyan lilac charcoal oxblood navy gold silver
    serif sans slab monospace typewriter condensed didone humanist geometric
    grotesque script gradient shadow rounded square light dark
""".split()


def word_pattern(words):
    """Match a listed word on its own or as part of a hyphenated compound
    ("dark-mode", "React-based"), but not inside a longer word."""
    alternatives = "|".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?:e?s)?(?![a-z0-9])",
                      re.IGNORECASE)


# An L2 brief says what it wants and never names the common default it moves
# away from, not even to forbid it (T1.2; docs/leak-check.md). A named default
# that then shows up in an output could have come from the prompt.
NAMED_DEFAULT_WORDS = """
    gradient shadow rounded emoji icon hero pill badge card glassmorphism
    hype jargon pun
""".split()
NAMED_DEFAULT_PHRASES = ("most popular", "dark mode", "dark theme",
                         "exclamation mark", "supercharge", "seamless")
# Page content that holds a listed word without naming a component.
ALLOWED_CONTENT = ("credit card",)

# The set uses US spelling throughout, so no prompt hints at another locale.
BRITISH_WORDS = """
    grey colour colourful centre centred neighbourhood organise organised
    favourite enquiry catalogue programme whilst labelled cancelled
    cancelling
""".split()

STYLE = word_pattern(STYLE_WORDS)
TECH = word_pattern(TECH_WORDS)
NAMED_DEFAULT = word_pattern(NAMED_DEFAULT_WORDS)
BRITISH = word_pattern(BRITISH_WORDS)
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


def named_defaults(text):
    """Common defaults that an L2 text names, as words and stock phrases."""
    lowered = text.lower().replace("-", " ")
    for content in ALLOWED_CONTENT:
        lowered = lowered.replace(content, " ")
    return NAMED_DEFAULT.findall(lowered) + [
        phrase for phrase in NAMED_DEFAULT_PHRASES if phrase in lowered]


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


@pytest.mark.parametrize("item", texts(("L2",)), ids=text_id)
def test_l2_names_no_default_to_forbid_it(item):
    assert named_defaults(item[3]) == []


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_every_prompt_uses_us_spelling(item):
    assert BRITISH.findall(item[3]) == []


@pytest.mark.parametrize("item", texts(), ids=text_id)
def test_each_wording_keeps_its_voice_at_every_level(item):
    """A is a command and B a request, the same way in every task, so the
    pair differs in one fixed bundle of mood, verb, length and voice."""
    _, level, wording, text = item
    opening = {"A": "Make ", "B": "Can you build "}[wording]
    assert text.startswith(opening)
    assert ("?" in text.splitlines()[0]) == (wording == "B")
    pleases = len(re.findall(r"\bplease\b", text, re.IGNORECASE))
    assert pleases == (1 if (level, wording) == ("L2", "B") else 0)


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


def l2_fact_problems(task_id, a, b):
    """Differences in checkable facts between the two L2 wordings.

    Numbers, emails and quoted text are compared in order, so two swapped
    prices or percentages count as a difference. Each name in NAMES must
    appear in both, wherever it stands in the sentence.
    """
    problems = []
    for label, pattern in (("numbers", NUMBER), ("emails", EMAIL),
                           ("quoted text", QUOTED)):
        if pattern.findall(a) != pattern.findall(b):
            problems.append(f"{label} differ or are in another order")
    if look_words(a) != look_words(b):
        problems.append("color and type words differ")
    for name in NAMES[task_id]:
        for wording, text in (("A", a), ("B", b)):
            if name not in text:
                problems.append(f"{wording} lacks {name!r}")
    for wording, text, other in (("A", a, b), ("B", b, a)):
        missing = sorted(name for name in mid_sentence_names(text)
                         if not re.search(rf"\b{name}\b", other))
        if missing:
            problems.append(f"names only in {wording}: {missing}")
    return problems


def test_names_are_listed_for_every_task():
    assert sorted(NAMES) == sorted(EXPECTED)


@pytest.mark.parametrize("task_id", sorted(EXPECTED))
def test_the_two_l2_wordings_carry_the_same_facts(task_id):
    task = tasks()[task_id]
    assert l2_fact_problems(task_id, task.text("L2", "A"),
                            task.text("L2", "B")) == []


# --- the checks themselves ---------------------------------------------------


@pytest.mark.parametrize("text", [
    "Make a modern website for a bakery.",
    "Make a website with a dark theme.",
    "Make a bakery site with cards and a hero.",
    "Make a website in pastel colours.",
    "Use a serif font.",
    "Make a website with a dark-mode toggle.",
    "Make a card-based pricing page.",
    "Make a two-column portfolio.",
    "Make a mobile-friendly event page.",
    "Make a dashboard they can read at a glance.",
    "Make a page that gives a quick overview.",
    "Make a pricing page so they can compare the plans.",
    "Make a landing page for a bakery.",
])
def test_the_style_check_catches_a_hint(text):
    assert STYLE.findall(text)


@pytest.mark.parametrize("text", [
    "Make it a single HTML file.",
    "Use React and Tailwind.",
    "Build it with Next.js.",
    "Keep everything in localStorage.",
    "Make a single-page site.",
    "Make a React-based to-do list.",
    "Keep it HTML-only.",
])
def test_the_technology_check_catches_a_request(text):
    assert TECH.findall(text)


@pytest.mark.parametrize("text", [
    "Make a to-do list web app.",
    "Make a page for a one-day event that takes pre-orders.",
    "A lightweight, cardamom-scented profile of a tabletop maker.",
])
def test_the_checks_pass_ordinary_words_and_compounds(text):
    assert STYLE.findall(text) == [] and TECH.findall(text) == []


@pytest.mark.parametrize("text", [
    "No gradients and no rounded corners.",
    "Show the plans in a table, not as separate cards.",
    'Do not mark any plan as "most popular".',
    'No hype words such as "supercharge" or "seamless".',
    "No emoji. No icons.",
    "Short sentences, no exclamation marks, no puns.",
    "Plain labels, no jargon.",
    "A light page with a dark-mode toggle.",
])
def test_the_named_default_check_catches_a_ban(text):
    assert named_defaults(text)


@pytest.mark.parametrize("text", [
    "Starter needs no credit card.",
    "Flat, solid color and square corners throughout.",
    "Links and labels are words only.",
    "A pre-order form with name, email and pickup day.",
])
def test_the_named_default_check_passes_content_and_positive_direction(text):
    assert named_defaults(text) == []


def test_the_spelling_check_catches_british_spelling():
    assert BRITISH.findall("A pale grey-blue page in the town centre.")
    assert BRITISH.findall("A pale gray-blue page in the town center.") == []


def test_single_alone_is_not_a_technology():
    assert TECH.findall("Charts in a single oxblood red.") == []


def l2(task_id):
    task = tasks()[task_id]
    return task.text("L2", "A"), task.text("L2", "B")


@pytest.mark.parametrize("task_id,old,new", [
    ("bakery-landing", "loaf for $9, seeded rye for $10",
     "loaf for $10, seeded rye for $9"),                       # swapped prices
    ("dashboard", "pasta and rice 82%, canned vegetables 64%",
     "pasta and rice 64%, canned vegetables 82%"),           # swapped shares
    ("bakery-landing", "It's owned by Priya Halvorsen",
     "It's owned by Maya Halvorsen"),                        # changed person
    ("event-page", "volunteer Rosa Imbert", "volunteer Rosa Imbach"),
    ("pricing-page", '"Start free"', '"Start for free"'),
    ("todo-app", "Call it Term Planner", "Call it Term Tracker"),
])
def test_the_fact_check_catches_a_changed_fact(task_id, old, new):
    a, b = l2(task_id)
    assert old in b
    assert l2_fact_problems(task_id, a, b.replace(old, new, 1)) != []


def test_mid_sentence_names_skip_first_words():
    text = "Make a page.\n- Owners: Ana Ruiz.\nOpen on Friday. Closed Monday."
    assert mid_sentence_names(text) == {"Ruiz", "Friday", "Monday"}
