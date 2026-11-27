"""Numbers in running text: one spelling for LaTeX, Unicode and plain
forms, and significant figures as written."""

import re
from dataclasses import dataclass

_PLAIN_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_SUPERSCRIPT = re.compile("[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,6}")
_SPACES = re.compile(r"[ \t   ]{1,}")
_BRACED_POWER = re.compile(r"\^\{([-+]?\d{1,3})\}")
_TEXT = re.compile(r"\\(?:text|mathrm|mathbf|textbf|operatorname|mathit)"
                   r"[ ]?\{([^{}]{0,80})\}")
_REPLACE = (
    ("^{\\circ}", "°"), ("^\\circ", "°"), ("\\degree", "°"),
    ("\\times", "×"), ("\\cdot", "·"), ("\\approx", "≈"), ("\\simeq", "≈"),
    ("\\varepsilon", "ε"), ("\\epsilon", "ε"), ("\\rho", "ρ"), ("\\mu", "μ"),
    ("\\Delta", "Δ"), ("\\,", " "), ("\\;", " "), ("\\!", ""), ("\\ ", " "),
    ("\\%", "%"), ("\\$", "$"), ("{,}", ","), ("~", " "), ("−", "-"),
)

# A number as written: optional sign, digit groups, decimals, and a power of
# ten in e-notation or as "x 10^n". Every repeat is bounded.
NUMBER = re.compile(
    r"(?<![\w.^,])(?P<sign>(?<![\d)] )-)?"
    r"(?P<mantissa>(?:\d{1,3}(?:,\d{3}){1,5}(?![\d])|\d{1,15})(?:\.\d{1,15})?)"
    r"(?:[eE](?P<e>[-+]?\d{1,3})(?!\d)|"
    r" ?[×x*·] ?10 ?\^ ?[{(]?(?P<power>[-+]?\d{1,3})[})]?)?")


def normalise(text):
    """``text`` with LaTeX and Unicode number spellings made plain, runs of
    blanks made one and Markdown bold marks removed."""
    text = _SPACES.sub(" ", text)
    for old, new in _REPLACE:
        text = text.replace(old, new)
    text = _BRACED_POWER.sub(r"^\1", text)      # so \text{m^{-3}} has no braces
    for _ in range(2):
        text = _TEXT.sub(r"\1", text)
    text = _SUPERSCRIPT.sub(lambda m: "^" + m[0].translate(_PLAIN_SUPER), text)
    return _SPACES.sub(" ", text.replace("**", ""))


def sig_figs(mantissa):
    """Significant figures of a number as written, or None where the writing
    does not say (zero, or a whole number ending in zero)."""
    digits = mantissa.replace(",", "").lstrip("+-")
    if "." not in digits and digits.endswith("0"):
        return None
    return len(digits.replace(".", "").lstrip("0")) or None


@dataclass(frozen=True)
class Number:
    value: float
    mantissa: str
    sig_figs: object
    decimals: int


def parse(match):
    """The :class:`Number` of a :data:`NUMBER` match."""
    mantissa = match["mantissa"]
    exponent = int(match["e"] or match["power"] or 0)
    plain = mantissa.replace(",", "")
    value = float(f"{match['sign'] or ''}{plain}e{exponent}")
    decimals = len(plain.split(".")[1]) if "." in plain else 0
    return Number(value, mantissa, sig_figs(mantissa), decimals)


def canonical(value):
    """One spelling of a value, to six significant figures."""
    return format(float(f"{value:.6g}"), ".6g")


def prompt_values(prompt):
    """The values of the numbers in the prompt: restating them is no choice."""
    return {canonical(parse(m).value) for m in NUMBER.finditer(normalise(prompt))}
