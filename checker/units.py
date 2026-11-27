"""One spelling for a unit, so that ``kNm``, ``kN·m`` and ``kN-m`` match.

A unit is a product of known atoms over another such product. Anything with
an unknown atom has no canonical form, and a value in it is not graded.
Case matters (``mm`` and ``Mm``, ``mPa`` and ``MPa``).
"""

import re

MAX_UNIT = 40
CURRENCIES = frozenset({"", "$", "usd", "us$", "dollar", "dollars", "us dollars", "€",
                        "eur", "euro", "euros", "£", "gbp", "pounds sterling",
                        "currency", "currency units"})
# Units that are one name, matched whole and without regard to case.
_NAMED = {
    "1": ("", "1", "-", "dimensionless", "unitless"),
    "pH": ("", "ph", "ph units"),
    "percent": ("%", "percent", "per cent"),
    "percent per month": ("%", "% per month", "%/month", "percent per month", "% monthly",
                          "% a month", "percent a month"),
    "decimal fraction per month": ("decimal fraction per month",),
    "fraction": ("fraction",),
    "ways": ("", "ways", "way", "arrangements", "microstates"),
    "teeth": ("", "teeth", "tooth", "t"),
    "date": ("", "date"),
}
# spelling -> atom. Longer words are matched without regard to case.
_ATOMS = {
    "m": "m", "mm": "mm", "cm": "cm", "in": "in", "ft": "ft", "inch": "in",
    "inches": "in", "feet": "ft", "foot": "ft", "meter": "m", "meters": "m",
    "metre": "m", "metres": "m", "millimeters": "mm", "millimetres": "mm",
    "N": "N", "kN": "kN", "lb": "lb", "lbf": "lb", "lbs": "lb", "pound": "lb",
    "pounds": "lb",
    "Pa": "Pa", "kPa": "kPa", "MPa": "MPa", "GPa": "GPa", "psi": "psi", "ksi": "ksi",
    "bar": "bar",
    "s": "s", "sec": "s", "seconds": "s", "min": "min", "month": "month",
    "rpm": "rpm", "RPM": "rpm", "rev": "rev", "rad": "rad", "r": "rev",
    "W": "W", "kW": "kW", "watts": "W", "A": "A", "amps": "A", "amperes": "A",
    "L": "L", "l": "L", "liter": "L", "liters": "L", "litre": "L", "litres": "L",
    "mL": "mL", "ml": "mL",
    "°C": "°C", "℃": "°C", "degC": "°C", "C": "C", "K": "K",
}
_SUPER = str.maketrans({"²": "^2", "³": "^3", "⁴": "^4"})
_PRODUCT = re.compile(r"(?:[·⋅*×. ]|(?<=[A-Za-z])-(?=[A-Za-z]))+")
_ATOM = re.compile(r"(?P<name>[^\d^]{1,20}?)(?:\^?\(?(?P<power>-?[1-4])\)?)?")
# atoms written closed up ("kNm", "Nmm", "lbin", "lbfft")
_CLOSED = re.compile(r"(kN|N|lbf|lb)(mm|m|in|ft)")


def _factors(text):
    found = []
    if text.strip() == "1":
        return found
    for word in _PRODUCT.split(text.strip("() ")):
        if not word:
            continue
        closed = _CLOSED.fullmatch(word)
        for part in (closed.groups() if closed else (word,)):
            match = _ATOM.fullmatch(part)
            if not match:
                return None
            word = match["name"]
            name = _ATOMS.get(word) or (_ATOMS.get(word.lower()) if len(word) > 3 else None)
            if not name:
                return None
            found.append((name, int(match["power"] or 1)))
    return found


def canonical(unit):
    """A comparable form of ``unit``, or None where it is not known."""
    text = (unit or "").strip().translate(_SUPER).replace("^ ", "^")
    if len(text) > MAX_UNIT or not text:
        return None
    text = re.sub(r"\b(?:deg|degrees?) ?C(?:elsius)?\b", "°C", text)
    text = re.sub(r"° C\b", "°C", text)
    text = re.sub(r"\br(?:ev)?/min\b|\brev(?:olutions)? per minute\b", "rpm", text)
    text = re.sub(r"\bsq\.? ?(mm|cm|m|in)\b", r"\1^2", text)
    text = text.replace(" per ", "/")
    parts = text.split("/")
    if len(parts) > 2:
        return None
    top = _factors(parts[0])
    bottom = _factors(parts[1]) if len(parts) == 2 else []
    if top is None or bottom is None or not (top or bottom):
        return None
    powers = {}
    for name, power in top:
        powers[name] = powers.get(name, 0) + power
    for name, power in bottom:
        powers[name] = powers.get(name, 0) - power
    # a temperature difference per watt: °C/W, C/W and K/W are told apart only
    # by the reference's own list of accepted units
    if powers.get("W") == -1 and powers.get("C") == 1:
        powers["°C"] = powers.pop("C")
    if powers == {"N": 1, "mm": -2}:
        powers = {"MPa": 1}
    return tuple(sorted((name, power) for name, power in powers.items() if power))


def same(stated, wanted):
    """Whether the unit text ``stated`` names the reference unit ``wanted``."""
    text = (stated or "").strip()
    if wanted == "currency":
        return text.lower() in CURRENCIES
    if wanted in _NAMED:
        return text.lower() in _NAMED[wanted]
    form = canonical(text)
    return form is not None and form == canonical(wanted)


def conversion(stated, quantity):
    """``(factor, offset)`` from the quantity's unit to the unit ``stated``,
    or None where that unit is not one the reference accepts."""
    if same(stated, quantity["unit"]):
        return 1.0, 0.0
    for other in quantity.get("other_units", ()):
        if same(stated, other["unit"]):
            return float(other["factor"]), float(other.get("offset", 0.0))
    return None
