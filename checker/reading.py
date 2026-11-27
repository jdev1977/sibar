"""A response as the extractor reads it: sentences and table rows, each with
the heading it stands under, and one spelling for numbers and marks.

Everything is bounded: long lines and long sentences are left out, and the
patterns are applied to short pieces only.
"""

import re
from dataclasses import dataclass

from extractors.common.numbers import normalise

MAX_LINES = 5_000
MAX_LINE = 1_000
MAX_SENTENCE = 400
MAX_CELLS = 12
MAX_HEADING = 120

_BOXED = re.compile(r"\\boxed\{((?:[^{}]|\{[^{}]{0,60}\}){0,200})\}")
_ACCENT = re.compile(r"\\(hat|bar|overline)\{ ?([xy]) ?\}")
_LATEX = (("\\left", ""), ("\\right", ""), ("\\(", " "), ("\\)", " "), ("\\[", " "),
          ("\\]", " "), ("\\quad", " "), ("\\Rightarrow", ";"), ("\\implies", ";"),
          ("₀", "0"), ("x̅", "x̄"), ("x̄", "x̄"))
_FRACTION = re.compile(r"\\[dt]?frac\{([^{}]{0,80})\}\{([^{}]{0,80})\}")
_BULLET = re.compile(r"^[ \t]{0,12}(?:(?:[-*+•>]|#{1,6}|\d{1,2}[.)])[ \t]+){0,3}")
_SENTENCE = re.compile(r"(?<=[.!?])[ \t]+(?=[A-Z*(\\$])")
_RULE = re.compile(r"\|?[ \t:|-]{0,400}-[ \t:|-]{0,400}")
_BOLD_LINE = re.compile(r"[ \t]{0,3}(?:#{1,6}[ \t].{0,200}|\*\*[^*]{1,100}\*\*:?[ \t]*)")
_WRAPPED = re.compile(r"^([*_]{1,3})(.*?)\1$")
_VALUE_AFTER = re.compile(r"=|≈|:\s{0,3}\S{0,20}\d")


@dataclass(frozen=True)
class Sentence:
    text: str
    heading: str          # the titles it stands under
    section: str          # the last title that holds no value


@dataclass(frozen=True)
class Table:
    header: tuple
    rows: tuple
    heading: str
    section: str


def clean(text):
    """One line with LaTeX and Markdown marks made plain."""
    text = _ACCENT.sub(lambda m: "ŷ" if m[2] == "y" else "x̄", text)
    for _ in range(2):
        text = _BOXED.sub(r"\1", text)
    for old, new in _LATEX:
        text = text.replace(old, new)
    text = normalise(text)
    text = _FRACTION.sub(r"(\1)/(\2)", text)
    text = text.replace("\\$", "").replace("$", "").replace("`", "")
    return re.sub(r" {2,}", " ", text.replace("__", "")).strip()


def _cells(line):
    # marks around a whole cell go; the star of "t*" stays
    cells = [_WRAPPED.sub(r"\2", clean(c)) for c in line.strip().strip("|").split("|")]
    return tuple(cells[:MAX_CELLS])


def read(text):
    """``(sentences, tables)`` of ``text`` (prose and plain-text blocks)."""
    lines = [line.rstrip("\r") for line in text.split("\n")[:MAX_LINES]]
    sentences, tables, heading, section = [], [], "", ""
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if len(line) > MAX_LINE or not line.strip():
            continue
        following = lines[index].strip() if index < len(lines) else ""
        if "|" in line and "|" in following and _RULE.fullmatch(following[:MAX_LINE]):
            header, rows = _cells(line), []
            index += 1
            while index < len(lines) and "|" in lines[index]:
                if len(lines[index]) <= MAX_LINE:
                    rows.append(_cells(lines[index]))
                index += 1
            tables.append(Table(header, tuple(rows), heading, section))
            continue
        stripped = line.strip()
        marked = _BOLD_LINE.fullmatch(line)
        valued = _VALUE_AFTER.search(stripped)
        if marked or (stripped.endswith(":") and len(stripped.split()) <= 10
                      and not valued):
            # a heading is read as a sentence too: it may be the conclusion
            title = clean(_BULLET.sub("", stripped))[:MAX_HEADING].strip("*:# ")
            if not valued:
                heading = section = title
            elif stripped.startswith("#"):
                heading, section = title, ""
            else:           # a bold figure stays under the title it follows
                heading = f"{section} / {title}" if section else title
        body = _BULLET.sub("", line)
        for sentence in _SENTENCE.split(body):
            sentence = clean(sentence).strip("*_ ")
            if sentence and len(sentence) <= MAX_SENTENCE:
                sentences.append(Sentence(sentence, heading, section))
    return tuple(sentences), tuple(tables)
