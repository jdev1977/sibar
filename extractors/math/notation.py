"""How a math or science answer writes: notation, the form of address, and
the currency it takes a loan to be in."""

import re

from extractors.base import Extractor
from extractors.common.response import NO_INPUT, get_doc, result

MAX_FORMULAS = 100_000

# --- formulas ---------------------------------------------------------------

_DISPLAY = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"))
_BEGIN = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}")
_INLINE_CODE = re.compile(r"`[^`\n]{0,400}`")
_UNICODE = re.compile("[×·÷√∑∫≈≃≤≥≠±∓²³⁰¹⁴⁵⁶⁷⁸⁹⁻ⁿ₀₁₂₃₄₅₆₇₈₉ₐₑₒₓαβγδεηθλμνπρστφχψωΔΣΩ∂∞∝→⇌]")
_PLAIN_MARK = re.compile(r"\^|\bsqrt\(|\bexp\(|\bln\(|<=|>=|!=|\w ?\* ?[\w(]")


def _cut_blocks(text):
    """``(rest, spans)``: delimited formulas taken out of ``text``."""
    spans = []
    for opening, closing in _DISPLAY:
        rest, position = [], 0
        while True:
            start = text.find(opening, position)
            end = text.find(closing, start + len(opening)) if start >= 0 else -1
            if end < 0:
                rest.append(text[position:])
                break
            rest.append(text[position:start])
            spans.append(text[start + len(opening):end])
            position = end + len(closing)
        text = "\n".join(rest)
    rest, position = [], 0
    while True:
        found = _BEGIN.search(text, position)
        end = text.find("\\end{" + found[1], found.end()) if found else -1
        if end < 0:
            rest.append(text[position:])
            break
        rest.append(text[position:found.start()])
        spans.append(text[found.end():end])
        close = text.find("}", end)
        position = len(text) if close < 0 else close + 1
    return "\n".join(rest), spans


def _cut_inline(line):
    """``(rest, spans)`` of one line's ``$...$`` formulas, by the usual rule:
    the opening mark has no blank after it, the closing one no blank before
    it and no digit after it. So two prices do not make a formula."""
    marks = [i for i, c in enumerate(line)
             if c == "$" and (i == 0 or line[i - 1] != "\\")]
    rest, spans, done, k = [], [], 0, 0
    while k + 1 < len(marks):
        start, end = marks[k], marks[k + 1]
        if (end > start + 1 and not line[start + 1].isspace()
                and not line[end - 1].isspace()
                and not line[end + 1:end + 2].isdigit()):
            rest.append(line[done:start])
            spans.append(line[start + 1:end])
            done = end + 1
            k += 2
        else:
            k += 1
    rest.append(line[done:])
    return " ".join(rest), spans


def formulas(text):
    """``(text without its LaTeX formulas, the formulas)``."""
    text, spans = _cut_blocks(text)
    lines = []
    for line in text.split("\n"):
        if "$" in line:
            line, inline = _cut_inline(line)
            spans += inline
        lines.append(line)
    return "\n".join(lines), spans[:MAX_FORMULAS]


def _working(doc):
    return _INLINE_CODE.sub(" ", doc.working)


def _split(inputs):
    return inputs.cached("t2.8.formulas", lambda: formulas(_working(get_doc(inputs))))


def notation(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    rest, spans = _split(inputs)
    counts = {"latex": len(spans), "unicode": 0, "plain": 0}
    relation = any("=" in span or "\\approx" in span for span in spans)
    for line in rest.split("\n"):
        if "=" not in line and "≈" not in line:
            if _PLAIN_MARK.search(line) and re.search(r"\w ?\^ ?[\w({-]", line):
                counts["plain"] += 1
            continue
        relation = True
        counts["unicode" if _UNICODE.search(line) else "plain"] += 1
    total = sum(counts.values())
    if not total:
        main = "none"
    else:
        best = max(sorted(counts), key=counts.get)
        main = best if counts[best] >= 0.7 * total else "mixed"
    return result(doc, {
        "notation": sorted(name for name, count in counts.items() if count),
        "main_notation": main,
        "has_formula": relation,
    })


# --- address ----------------------------------------------------------------

_YOU = re.compile(r"\b[Yy]ou(?:r|rs|rself|'re|'ll|'ve|'d|’re|’ll|’ve|’d)?\b")
_WE = re.compile(r"\b(?:[Ww]e(?:'re|'ll|'ve|’re|’ll|’ve)?|us|[Oo]ur|[Ll]et(?:'|’)s)\b")
PRONOUNS = 2        # fewer is a passing word, not a way of writing


def voice(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    text = _working(doc)
    you = sum(1 for _ in _YOU.finditer(text))
    we = sum(1 for _ in _WE.finditer(text))
    address = ("both" if you >= PRONOUNS and we >= PRONOUNS else "you"
               if you >= PRONOUNS else "we" if we >= PRONOUNS else "neither")
    return result(doc, {"you_count": you, "we_count": we, "address": address})


# --- currency ---------------------------------------------------------------

_MONEY = re.compile(r"\b(?:loan|interest|payments?|principal|price|cost|lender|"
                    r"borrow\w{0,6}|repay\w{0,6}|afford\w{0,6})\b", re.IGNORECASE)
_SYMBOLS = re.compile("[€£¥₹]")
_CODES = re.compile(r"\b(?:USD|EUR|GBP|AUD|CAD|INR|JPY|CHF|NZD|ZAR|CNY|SEK|NOK)\b")
_WORDS = re.compile(r"\b(dollars|euros|rupees|yen|francs|pounds sterling)\b",
                    re.IGNORECASE)
_ESCAPED = re.compile(r"\\\$ ?\d")
_DOLLAR = re.compile(r"(?<![\\$])\$ ?\d")


def currency(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    text = _working(doc)
    rest, _ = _split(inputs)
    found = set(_SYMBOLS.findall(text)) | set(_CODES.findall(text))
    found |= {word.lower() for word in _WORDS.findall(text)}
    if _ESCAPED.search(text) or _DOLLAR.search(rest):
        found.add("$")
    if not found and _MONEY.search(text):
        found = {"none"}
    return result(doc, {"currency": sorted(found)})


EXTRACTORS = (
    Extractor("math.notation", "1", "math", notation,
              "LaTeX, Unicode or plain formulas"),
    Extractor("math.voice", "1", "math", voice,
              "second person and first person plural"),
    Extractor("math.currency", "1", "math", currency,
              "the currency symbol or code of a money answer"),
)
