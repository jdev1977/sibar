"""Quantities with units, and which unit system they belong to.

Only a unit written right after a number, or alone in brackets (a table
heading), is read. ``in`` is also an English word, so it counts only where a
sentence cannot go on with it: before punctuation or a word of size. A
fraction is read whole (``1/8 in``, ``1 1/2 in``). ``2g`` written closed up
is twice the acceleration of gravity, not two grams, and is not read.
"""

import re

from extractors.common.numbers import NUMBER, canonical, parse

METRIC = frozenset("mm cm m km µm μm um nm g kg mg N kN MN Pa kPa MPa GPa J kJ "
                   "L mL dm K °C bar tonne".split())
US = frozenset("in inch inches ft feet foot lb lbs lbf pound pounds psi ksi oz "
               "gal gpm °F hp mph mil mils thou".split())
NEUTRAL = frozenset("s min h hr Hz kHz rpm V mV A mA W kW rad Ω mol mmol M mM "
                    "yr years".split())
_ATOM = "(?:" + "|".join(re.escape(u) for u in
                         sorted(METRIC | US | NEUTRAL, key=lambda u: (-len(u), u))) + ")"
_POWER = r"(?:\^[({]?-?\d[)}]?)"
# atoms joined by a product or a division mark; a bare space joins them only
# before a power ("mol L^-1")
_COMPOUND = (rf"{_ATOM}{_POWER}?(?![A-Za-z])"
             rf"(?:(?:[·⋅*/\-] ?{_ATOM}{_POWER}?|[ .]{_ATOM}{_POWER})(?![A-Za-z])){{0,4}}")
_AFTER = re.compile(rf"(?:[ \-]?(?P<unit>{_COMPOUND})|(?P<quote>\"))")
_BRACKETED = re.compile(rf"[(\[](?P<unit>{_COMPOUND})[)\]]")
_INCH_FOLLOWS = re.compile(
    r"[ \t]?(?:$|[.,;:)\]|×*\n]|x ?\d|(?:long|diameter|dia\b|wide|OD\b|ID\b|thick|"
    r"deep|high|tall|across|square|travel|free|material|stock|plywood|wire|hole)\b)")
_QUOTE_FOLLOWS = re.compile(
    r"[ \t]?(?:$|[.,;:)\]|×\n]|x ?\d|(?:long|diameter|dia\b|wide|OD\b|ID\b|thick|deep|"
    r"high|tall|across|square|plywood|wire|hole)\b)")
_SPLIT = re.compile(r"[·⋅*/\- .]+(?!\d)")
_POWERS = re.compile(r"\^[({]?-?\d[)}]?")
MAX_QUANTITIES = 20_000
# the "1 1/" before the "2" of a fraction
_FRACTION = re.compile(r"(?:(?<![\d./])(\d{1,3})[ \-])?(?<![\d./])(\d{1,3})/\Z")


def _value(text, match):
    """The number of a match, as the whole fraction it may end."""
    number = parse(match)
    start = match.start()
    fraction = _FRACTION.search(text[max(start - 9, 0):start])
    if fraction and number.mantissa.isdigit() \
            and int(fraction[2]) < int(number.mantissa):
        return int(fraction[1] or 0) + int(fraction[2]) / number.value
    return number.value


def quantities(text, quotes=True):
    """``(value or None, unit)`` for each quantity in normalised ``text``.
    ``quotes`` False for code, where ``"`` ends a string and is not inches."""
    found = []
    for match in NUMBER.finditer(text):
        after = _AFTER.match(text, match.end())
        if not after:
            continue
        end = after.end()
        if after["quote"]:
            if not quotes:
                continue
            start = match.start()
            if start and text[start - 1] in "\"'" or not _QUOTE_FOLLOWS.match(text, end):
                continue
            unit = "in"
        else:
            unit = after["unit"]
            if unit == "in" and not _INCH_FOLLOWS.match(text, end):
                continue
            if unit == "g" and match["mantissa"] == "2" \
                    and after.start("unit") == match.end():
                continue
        found.append((canonical(_value(text, match)), unit))
        if len(found) >= MAX_QUANTITIES:
            return found
    for match in _BRACKETED.finditer(text):
        found.append((None, match["unit"]))
        if len(found) >= MAX_QUANTITIES:
            break
    return found


def system_of(unit):
    """``metric``, ``us`` or None for a unit that both systems use."""
    atoms = set(_SPLIT.split(_POWERS.sub("", unit)))
    if atoms & US:
        return "us"
    return "metric" if atoms & METRIC else None


def unit_system(found):
    """``(system, metric mentions, US mentions)``: a system holding four in
    five of the mentions or more, else ``both``; ``none`` with no mention."""
    counts = {"metric": 0, "us": 0}
    for _, unit in found:
        system = system_of(unit)
        if system:
            counts[system] += 1
    metric, us = counts["metric"], counts["us"]
    total = metric + us
    name = ("none" if not total else "metric" if metric >= 0.8 * total
            else "us-customary" if us >= 0.8 * total else "both")
    return name, metric, us
