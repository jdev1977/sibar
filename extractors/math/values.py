"""Precision, units, method keywords, constants and code of a math or science
answer."""

import re
from collections import Counter

from extractors.base import Extractor
from extractors.common import code, units
from extractors.common.numbers import NUMBER, canonical, normalise, parse, prompt_values
from extractors.common.response import NO_INPUT, PLAIN, get_doc, result

MAX_NUMBERS = 100_000
LONG = 7            # significant figures of a number nobody rounded


def _text(inputs):
    """The working, with one spelling for numbers."""
    return inputs.cached("t2.8.normal",
                         lambda: normalise(get_doc(inputs).working))


# --- precision --------------------------------------------------------------

_BOLD = re.compile(r"\*\*(?=\S)([^*\n]{1,200})\*\*")
_BOXED = re.compile(r"\\boxed\{")
_LABEL = re.compile(r"^[ \t]{0,5}(?:step|part|section|case|option|method|table|figure|"
                    r"question|example|month|row|note)\b", re.IGNORECASE)
_APPROX = re.compile(r"≈ ?[$€£]? ?")
_UNITLESS_OK = re.compile(r"[=≈:$€£]")
MAX_SEGMENTS = 2_000


def _boxed(text):
    for found in list(_BOXED.finditer(text))[:MAX_SEGMENTS]:
        depth = 1
        for index in range(found.end(), min(found.end() + 300, len(text))):
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            if not depth:
                yield text[found.end():index]
                break


def _result_of(segment, given):
    """The number a marked segment reports: its last one, unless it is a
    value the prompt gave or a bare count."""
    segment = normalise(segment)
    if _LABEL.match(segment):
        return None
    last = None
    for match in NUMBER.finditer(segment):
        # a power or an index of a unit is not a result
        if not segment[max(match.start() - 1, 0):match.start()] in ("^", "_", "{"):
            last = match
    if last is None:
        return None
    number = parse(last)
    if canonical(number.value) in given or number.sig_figs is None:
        return None
    bare = ("." not in number.mantissa and not _UNITLESS_OK.search(segment)
            and not units.quantities(segment))
    return None if bare else number


def _most_common(values):
    if not values:
        return None
    ranked = Counter(values).most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "mixed"
    return ranked[0][0]


def precision(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    given = prompt_values(doc.prompt)
    raw = doc.working
    segments = [m[1] for m, _ in zip(_BOLD.finditer(raw), range(MAX_SEGMENTS))]
    segments += list(_boxed(raw))
    found = [n for n in (_result_of(s, given) for s in segments) if n]
    basis = "marked"
    text = _text(inputs)
    if not found:
        basis = "approximation"
        for sign, _ in zip(_APPROX.finditer(text), range(MAX_SEGMENTS)):
            match = NUMBER.match(text, sign.end())
            if match:
                number = parse(match)
                if canonical(number.value) not in given and number.sig_figs:
                    found.append(number)
    numbers = [parse(m) for m, _ in zip(NUMBER.finditer(text), range(MAX_NUMBERS))]
    own = [n for n in numbers if canonical(n.value) not in given]
    return result(doc, {
        "result_sig_figs": _most_common(
            ["5+" if n.sig_figs >= 5 else str(n.sig_figs) for n in found]),
        "result_decimals": _most_common(
            ["3+" if n.decimals >= 3 else str(n.decimals) for n in found]),
        "result_basis": basis if found else "none",
        "result_numbers": len(found),
        "max_decimals": max((n.decimals for n in own), default=0),
        "long_decimals": any(n.decimals and (n.sig_figs or 0) >= LONG for n in own),
    })


# --- units ------------------------------------------------------------------

_CONCENTRATION = (
    ("molar", re.compile(r"\d ?M\b(?![\w/·^-])")),
    ("mol-per-litre-slash", re.compile(r"\bmol ?/ ?L\b")),
    ("mol-per-litre-exponent", re.compile(r"\bmol[ ·.]{1,3}L\^[({]?-1")),
    ("mol-per-dm3", re.compile(r"\bmol[ ·./]{1,3}dm\^[({]?-?3")),
)


def unit_features(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    text = _text(inputs)
    found = units.quantities(text)
    system, _, _ = units.unit_system(found)
    names = {unit for _, unit in found}
    slash = any("/" in unit for unit in names)
    exponent = any("^-" in unit or "^{-" in unit or "^(-" in unit for unit in names)
    style = ("both" if slash and exponent else "slash" if slash else
             "exponent" if exponent else "none")
    return result(doc, {
        "unit_system": system,
        "unit_style": style,
        "unit_symbols": sorted(names)[:100],
        "concentration_notation": sorted(
            name for name, pattern in _CONCENTRATION if pattern.search(text)),
    })


# --- method keywords ----------------------------------------------------------

_METHODS = tuple((name, re.compile(pattern, flags)) for name, pattern, flags in (
    ("euler", r"(?<!improved )(?<!modified )\bEuler(?:'s|’s)? (?:method|scheme|"
              r"integration|step)", re.I),
    ("heun", r"\bHeun\b|\b(?:improved|modified) Euler\b", re.I),
    ("runge-kutta", r"\bRunge[-–— ]{1,3}Kutta\b|\bRK ?[245]{1,2}\b", re.I),
    ("ode-solver", r"\bsolve_ivp\b|\bodeint\b|\bode45\b|\bNDSolve\b|\bdeSolve\b", 0),
    ("closed-form", r"\bclosed[- ]form\b|\banalytic(?:al)? (?:solution|expression)", re.I),
    ("numerical", r"\bnumerical(?:ly)?\b", re.I),
    ("henderson-hasselbalch", r"\bHenderson\b|\bHasselbalch\b", re.I),
    ("ice-table", r"\bICE (?:table|chart|box)\b", 0),
    ("charge-balance", r"\bcharge[- ]balance\b", re.I),
    ("quadratic-formula", r"\bquadratic (?:formula|equation)\b", re.I),
    ("bisection", r"\bbisect", re.I),
    ("newton-raphson", r"\bNewton[-–— ]{1,3}Raphson\b|\bNewton(?:'s|’s) method\b", re.I),
    ("root-finder", r"\bbrentq\b|\bfsolve\b|\buniroot\b|\bgoal[- ]seek\b|\broot_scalar\b",
     re.I),
    ("t-test", r"\bt[- ]test\b|\bttest_1samp\b|\bt\.test\b|\bStudent(?:'s|’s) t\b", re.I),
    ("z-test", r"\bz[- ]test\b", re.I),
    ("wilcoxon", r"\bwilcoxon\b|\bsigned[- ]rank\b", re.I),
    ("sign-test", r"\bsign test\b", re.I),
    ("shapiro-wilk", r"\bshapiro\b", re.I),
    ("anderson-darling", r"\banderson[-–— ]{1,3}darling\b", re.I),
    ("qq-plot", r"\bq[-–— ]?q[- ]plot\b|\bqqnorm\b|\bprobplot\b", re.I),
    ("normality", r"\bnormality\b", re.I),
    ("p-value", r"\bp[- ]values?\b|\bpvalue\b", re.I),
    ("confidence-interval", r"\bconfidence interval", re.I),
    ("normal-equations", r"\bnormal equations?\b", re.I),
    ("centered-sums", r"\bcent(?:er|r)ed sums?\b|\bS_?\{?xx\}?(?![a-z])", re.I),
    ("fit-function", r"\bpolyfit\b|\blinregress\b|\bcurve_fit\b|\bLinearRegression\b|"
                     r"\blstsq\b|\blm\( ?\w{1,20} ?~", 0),
    ("annuity-formula", r"\bannuity\b|\bamorti[sz]ation formula\b", re.I),
    ("boltzmann", r"\bBoltzmann\b", re.I),
    ("clausius", r"\bClausius\b", re.I),
    ("second-law", r"\bsecond law\b", re.I),
    ("microstates", r"\bmicro[- ]?states?\b", re.I),
    ("disorder", r"\bdisorder", re.I),
))


def methods(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    text = doc.text
    return result(doc, {"methods": sorted(
        name for name, pattern in _METHODS if pattern.search(text))})


# --- constants -----------------------------------------------------------------

_VALUE = r"(?=[\d.-])"
_PROJECTILE = re.compile(r"\bdrag\b|\bair resistance\b|\bprojectile\b", re.IGNORECASE)
_TITRATION = re.compile(r"\b(?i:titrat)|\bK_?\{?a\}?(?![a-z])|\bpK_?\{?a\}?(?![a-z])")
_IS = r"(?:=|≈|\bof\b|\bis\b|:|\|)"


def _symbol(symbol):
    """``symbol = value``, the symbol perhaps in dollar signs or brackets."""
    return rf"(?<![A-Za-z_\\])(?:{symbol})[$)]{{0,2}} ?(?:=|≈|\|) ?[$]?{_VALUE}"


def _named(name):
    """``name ... value`` with no other digit between."""
    return rf"(?:{name})[^\n\d]{{0,50}}?{_VALUE}"


def _acid(symbol):
    """An equilibrium constant, however the sentence reaches its value:
    ``Ka =``, ``Ka (acetic acid) =``, ``Ka of acetic acid is``, ``Ka for ...:``."""
    return (rf"(?<![A-Za-z_\\])(?:{symbol})(?![A-Za-z])\)?"
            r"(?: ?\([^)\n]{0,40}\))?(?: (?:of|for) [^\n=:≈]{0,50}?)?"
            rf" ?(?:=|≈|:|\||\bis\b|\bof\b) ?{_VALUE}")


_POWER_OF_TEN = re.compile(r"10 ?\^ ?[{(]?(-\d{1,3})")


# feature -> (relevance, patterns, lowest, highest, units to SI factor)
_CONSTANTS = {
    "g_value": (_PROJECTILE, [
        _symbol(r"g(?:_0)?"), r"(?<![\d.])(?=9\.8\d{0,4} ?m ?/ ?s)"], 9.7, 10.0, None),
    "drag_coefficient": (_PROJECTILE, [
        _symbol(r"C_?\{?[dD]\}?"), _named(r"(?i:drag coefficient)(?: \$?C_?\{?[dD]\}?\$?)?")],
        0.01, 2.5, None),
    "air_density": (_PROJECTILE, [
        _symbol(r"ρ(?:_\{?(?:air|a)\}?)?"), _named(r"(?i:air density|density of (?:the )?air)")],
        0.8, 1.5, None),
    "projectile_mass": (_PROJECTILE, [
        _symbol(r"m"), _named(r"\b[Mm]ass\b")], 1e-4, 1e4, {"kg": 1, "g": 1e-3}),
    "projectile_diameter": (_PROJECTILE, [
        _named(r"\b[Dd]iameter\b"), _symbol(r"[dD]")], 1e-4, 1.0,
        {"m": 1, "cm": 1e-2, "mm": 1e-3}),
    "ka_value": (_TITRATION, [
        _acid(r"K_?\{?a\}?"),
        _named(r"(?i:acid dissociation constant)(?: \$?K_?\{?a\}?\$?)?")],
        1e-8, 1e-2, None),
    "pka_value": (_TITRATION, [_acid(r"pK_?\{?a\}?")], 2.0, 7.0, None),
    "kw_value": (_TITRATION, [_acid(r"K_?\{?w\}?")], 1e-16, 1e-12, None),
}
_CONSTANTS = {name: (relevant, [re.compile(p) for p in patterns], low, high, factors)
              for name, (relevant, patterns, low, high, factors) in _CONSTANTS.items()}
_UNIT = re.compile(r" ?(kg|cm|mm|g|m)(?![A-Za-z/^])")


def _constant(text, patterns, low, high, factors):
    found = set()
    for pattern in patterns:
        for hit, _ in zip(pattern.finditer(text), range(200)):
            match = NUMBER.match(text, hit.end())
            if not match:
                continue
            power = _POWER_OF_TEN.match(text, hit.end())    # Kw = 10^-14
            value = float(f"1e{power[1]}") if power else parse(match).value
            unit = ""
            if factors:
                after = _UNIT.match(text, match.end())
                if not after or after[1] not in factors:
                    continue
                value *= factors[after[1]]
                unit = " " + next(u for u, f in factors.items() if f == 1)
            if low <= value <= high:
                found.add(canonical(value) + unit)
    return found


def constants(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    text = normalise(doc.text.replace("ₐ", "_a")).replace("$", "")
    values = {}
    for name, (relevant, patterns, low, high, factors) in _CONSTANTS.items():
        if not relevant.search(text):
            values[name] = "not-relevant"
            continue
        found = _constant(text, patterns, low, high, factors)
        values[name] = ("not-stated" if not found else
                        found.pop() if len(found) == 1 else "several")
    return result(doc, values)


# --- code and plots ------------------------------------------------------------

_PLOTS = tuple((name, languages, re.compile(pattern, re.M))
               for name, languages, pattern in (
    ("matplotlib", ("python",), r"^[ \t]{0,40}(?:import|from) matplotlib\b|\bplt\.\w{1,30}\("),
    ("seaborn", ("python",), r"^[ \t]{0,40}(?:import|from) seaborn\b"),
    ("plotly", ("python", "r", "javascript"), r"\bplotly\b"),
    ("ggplot", ("r",), r"\bggplot\( ?|\blibrary\(ggplot2\)"),
    ("base-r", ("r",), r"(?<![\w.])(?:plot|hist|curve|qqnorm|boxplot)\("),
    ("matlab", ("matlab",), r"(?<![\w.])(?:plot|fplot|scatter|semilogy|loglog)\("),
    ("julia-plots", ("julia",), r"\busing Plots\b"),
))
_PGF = re.compile(r"\\begin\{(?:tikzpicture|axis)\}")


def code_features(inputs):
    doc = get_doc(inputs)
    if not doc.has_text:
        return dict(NO_INPUT)
    programs = [f for f in doc.files
                if f.language in code.PROGRAMMING | code.SCRIPTING]
    plots = set()
    for source in programs:
        text = code.split(source.language, source.text).code
        plots |= {name for name, languages, pattern in _PLOTS
                  if source.language in languages and pattern.search(text)}
    if _PGF.search(doc.text):
        plots.add("pgfplots")
    unknown = any(b.language not in PLAIN and b.body.strip() for b in doc.blocks) \
        and not doc.files
    return result(doc, {
        "code_present": None if unknown else bool(programs),
        "code_languages": sorted({f.language for f in programs}),
        "plot_code": bool(plots),
        "plot_libraries": sorted(plots),
    })


EXTRACTORS = (
    Extractor("math.precision", "2", "math", precision,
              "significant figures and decimals of the results"),
    Extractor("math.units", "2", "math", unit_features,
              "unit system and the writing of compound units"),
    Extractor("math.methods", "1", "math", methods, "named methods as keywords"),
    Extractor("math.constants", "2", "math", constants,
              "the values of constants the answer assumes"),
    Extractor("math.code", "1", "math", code_features,
              "code and plotting code present"),
)
