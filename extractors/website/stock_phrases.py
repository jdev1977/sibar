"""Stock phrases: rules from ``stock_phrases.json`` matched on the page's
copy, plus em dashes, exclamation marks and Title Case headings."""

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from extractors.base import Extractor
from extractors.website.site import get_site

RULES_FILE = Path(__file__).with_name("stock_phrases.json")
CODE_VERSION = "1"
MAX_REPEAT = 100
MAX_TEXT = 2_000_000
HEADINGS = ("h1", "h2", "h3")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         " ": " ", "‑": "-"})
_SPACES = re.compile(r"\s+")
_WORDS = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
_REPEAT = re.compile(r"\{(\d{1,3}),?(\d{0,3})\}")
_SMALL_WORDS = frozenset({"a", "an", "and", "as", "at", "but", "by", "for", "in",
                          "of", "on", "or", "the", "to", "with", "from", "into"})


class RuleError(ValueError):
    """The rules file is malformed or a pattern is unsafe."""


def check_pattern(pattern):
    """Raise RuleError unless ``pattern`` uses only bounded repeats.

    Refused: ``*`` and ``+`` (unescaped, outside a character class), ``{m,n}``
    with n over :data:`MAX_REPEAT` or n missing, a repeat applied to a group,
    and backreferences. These keep matching time linear in the text.
    """
    i, in_class = 0, False
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            if pattern[i + 1:i + 2].isdigit() and pattern[i + 1] != "0":
                raise RuleError(f"{pattern!r}: backreference")
            i += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char in "*+":
            raise RuleError(f"{pattern!r}: unbounded repeat {char!r}")
        elif char == "{":
            match = _REPEAT.match(pattern, i)
            if not match:
                raise RuleError(f"{pattern!r}: malformed repeat")
            upper = match.group(2) if "," in match.group(0) else match.group(1)
            if not upper or int(upper) > MAX_REPEAT:
                raise RuleError(f"{pattern!r}: repeat over {MAX_REPEAT}")
            if i and pattern[i - 1] == ")":
                raise RuleError(f"{pattern!r}: repeat applied to a group")
            i = match.end()
            continue
        elif char == "(" and pattern[i + 1:i + 4] == "?P=":
            raise RuleError(f"{pattern!r}: backreference")
        i += 1
    return pattern


@lru_cache(maxsize=None)
def load_rules(path=RULES_FILE):
    """``(version, [(id, category, compiled regex)])`` from the rules file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise RuleError("version must be a whole number of at least 1")
    sources = data.get("sources", {})
    rules, seen = [], set()
    for rule in data.get("rules", []):
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not re.fullmatch(r"[a-z0-9-]+", rule_id) \
                or rule_id in seen:
            raise RuleError(f"rule id {rule_id!r} is missing, repeated or not a slug")
        seen.add(rule_id)
        source = rule.get("source")
        if source not in sources or not sources[source].get("url"):
            raise RuleError(f"rule {rule_id}: source {source!r} has no URL")
        if "phrases" in rule:
            phrases = rule["phrases"]
            if not phrases or not all(isinstance(p, str) and p.strip()
                                      and p == p.lower() for p in phrases):
                raise RuleError(f"rule {rule_id}: phrases must be lower-case text")
            body = "|".join(re.escape(p) for p in sorted(phrases, key=len,
                                                         reverse=True))
            regex = re.compile(r"(?<![\w])(?:" + body + r")(?![\w])")
        elif "pattern" in rule:
            regex = re.compile(check_pattern(rule["pattern"]))
        else:
            raise RuleError(f"rule {rule_id}: needs phrases or a pattern")
        rules.append((rule_id, rule.get("category", "other"), regex))
    return version, rules


def normalise(text):
    """Lower case, straight quotes, single spaces."""
    return _SPACES.sub(" ", text.translate(_QUOTES).lower()).strip()


def is_title_case(text):
    """True when a heading of three or more words capitalises every word of
    four or more letters (and is not all capitals)."""
    words = _WORDS.findall(text)
    long_words = [w for w in words if len(w) >= 4 and w.lower() not in _SMALL_WORDS]
    if len(words) < 3 or len(long_words) < 2 or text.isupper():
        return False
    return all(w[0].isupper() for w in long_words)


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup:
        return {"status": "no-input"}
    _, rules = load_rules()
    copy = site.copy_texts()
    # One piece per line, so no phrase is matched across two elements.
    text = "\n".join(normalise(p) for p in copy + site.attribute_texts())[:MAX_TEXT]
    counts, categories = Counter(), set()
    for rule_id, category, regex in rules:
        hits = sum(1 for _ in regex.finditer(text))
        if hits:
            counts[rule_id] = hits
            categories.add(category)
    words = sum(len(_WORDS.findall(piece)) for piece in copy)
    joined = "".join(copy)
    headings = title_case = 0
    for doc in site.page_docs() + [d for d in site.docs if d.fragment]:
        for element in doc.find(*HEADINGS):
            heading = doc.text_of(element, 300)
            if len(_WORDS.findall(heading)) >= 3:
                headings += 1
                title_case += is_title_case(heading)
    return {
        "status": site.status(),
        "stock_phrases": sorted(counts),
        "stock_phrase_counts": {key: counts[key] for key in sorted(counts)},
        "stock_phrase_hits": sum(counts.values()),
        "stock_phrase_categories": sorted(categories),
        "copy_word_count": words,
        "em_dash_count": joined.count("—"),
        "exclamation_count": joined.count("!"),
        "headings_checked": headings,
        "title_case_headings": title_case,
    }


def _version():
    try:
        rules_version = load_rules()[0]
    except (OSError, ValueError):
        rules_version = "missing"
    return f"{CODE_VERSION}+rules.{rules_version}"


EXTRACTOR = Extractor("website.stock-phrases", _version(), "website", extract,
                      "stock phrases from public slop lists; em dashes; Title Case")
