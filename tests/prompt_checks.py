"""Checks shared by the prompt-set tests (website, pipeline, math, engineering).

The rules these checks pin are in docs/leak-check.md. Each test file holds its
own word lists; this module holds the matching and comparing.
"""

import hashlib
import json
import re
from difflib import SequenceMatcher


def word_pattern(words):
    """Match a listed word or phrase on its own or as part of a hyphenated
    compound ("dark-mode", "React-based"), but not inside a longer word. A
    plural or "-es" form is matched too."""
    alternatives = "|".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?:e?s)?(?![a-z0-9])",
                      re.IGNORECASE)


# Every prompt set uses US spelling, so no prompt hints at another locale.
BRITISH_WORDS = """
    grey colour colourful centre centred neighbourhood organise organised
    favourite enquiry catalogue programme whilst labelled cancelled
    cancelling metre millimetre centimetre kilometre litre millilitre
    aluminium analyse analysed modelling modelled behaviour optimise
    optimised summarise minimise maximise licence practise practising
    tonne sulphur
""".split()
BRITISH = word_pattern(BRITISH_WORDS)

NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\d{3}-\d{4}")
QUOTED = re.compile(r"[\"“]([^\"”\n]+)[\"”]")
CAPITALIZED = re.compile(r"\b[A-Z][A-Za-z]+\b")


def fingerprint(task):
    """A short hash of a task's texts as sent, in send order."""
    sent = json.dumps(task.variants(), ensure_ascii=False)
    return hashlib.sha256(sent.encode("utf-8")).hexdigest()[:16]


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def similarity(a, b):
    """Word-sequence similarity of two texts, from 0 to 1."""
    return SequenceMatcher(None, words(a), words(b), autojunk=False).ratio()


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


def fact_problems(a, b, names=(), compare=()):
    """Differences in checkable facts between two wordings of one brief.

    Numbers, emails and quoted text are compared in order, so two swapped
    prices count as a difference. ``compare`` holds (label, function) pairs
    whose results must be equal for both texts. Each of ``names`` must appear
    in both, wherever it stands, and no capitalized word in the middle of a
    sentence may appear in one text only.
    """
    problems = []
    for label, pattern in (("numbers", NUMBER), ("emails", EMAIL),
                           ("quoted text", QUOTED)):
        if pattern.findall(a) != pattern.findall(b):
            problems.append(f"{label} differ or are in another order")
    for label, function in compare:
        if function(a) != function(b):
            problems.append(f"{label} differ")
    for name in names:
        for wording, text in (("A", a), ("B", b)):
            if name not in text:
                problems.append(f"{wording} lacks {name!r}")
    for wording, text, other in (("A", a, b), ("B", b, a)):
        missing = sorted(name for name in mid_sentence_names(text)
                         if not re.search(rf"\b{name}\b", other))
        if missing:
            problems.append(f"names only in {wording}: {missing}")
    return problems


def please_count(text):
    return len(re.findall(r"\bplease\b", text, re.IGNORECASE))
