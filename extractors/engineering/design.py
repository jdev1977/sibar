"""What an engineering answer chooses: units, the safety factor, standards,
named checks, spring ends, materials, a few stated values and the form of
its CAD file."""

import re

from extractors.base import Extractor
from extractors.common import code, units
from extractors.common.numbers import NUMBER, canonical, normalise, parse
from extractors.common.response import NO_INPUT, get_doc, result
from runner.files import EXTENSIONS

MAX_HITS = 500
_CODE = code.PROGRAMMING | code.SCRIPTING | {"openscad"}


def _text(inputs):
    """The whole reply, code and comments included, with one spelling for
    numbers and without formula delimiters."""
    return inputs.cached(
        "t2.8.engineering",
        lambda: normalise(get_doc(inputs).text).replace("$", ""))


def _extractor_values(build):
    def extract(inputs):
        doc = get_doc(inputs)
        if not doc.has_text:
            return dict(NO_INPUT)
        return result(doc, build(inputs, doc, _text(inputs)))
    return extract


def _found(table, text):
    return sorted(name for name, pattern in table if pattern.search(text))


def _table(rows, flags=re.IGNORECASE):
    return tuple((name, re.compile(pattern, flags)) for name, pattern in rows)


def _one(values, none="not-stated"):
    """The one value, ``several``, or ``none`` for an empty set."""
    if not values:
        return none
    return next(iter(values)) if len(values) == 1 else "several"


# --- units --------------------------------------------------------------------


def _block_language(block):
    suffix = EXTENSIONS.get(block.language, "txt" if not block.language else "")
    return code.language_of(f"block.{suffix}", block.body) if suffix else None


def _read_quantities(doc):
    """Quantities of the prose and of every block. A program is read outside
    its strings: the text of a plot label is not a dimension, and its closing
    quote is not inches. Every other block (data, notes, drawings) is read
    whole."""
    whole, found = [doc.prose], []
    for block in doc.blocks:
        language = _block_language(block)
        if language not in _CODE:
            whole.append(block.body)
            continue
        parts = code.split("c" if language == "openscad" else language, block.body)
        outside = "\n".join((parts.bare, *parts.comments))
        found += units.quantities(normalise(outside), quotes=False)
    return units.quantities(normalise("\n".join(whole)).replace("$", "")) + found


def _found_quantities(inputs):
    return inputs.cached("t2.8.quantities",
                         lambda: _read_quantities(get_doc(inputs)))


def _units(inputs, doc, text):
    found = _found_quantities(inputs)
    system, metric, us = units.unit_system(found)
    return {"unit_system": system, "metric_mentions": metric, "us_mentions": us,
            "unit_symbols": sorted({unit for _, unit in found})[:100]}


# --- safety factor ------------------------------------------------------------

_TERM = (r"(?:(?i:safety factors?|factors? of safety|design factors?)|"
         r"(?<![A-Za-z])(?:FoS|FOS|SF|FS)(?![A-Za-z]))")
_MENTION = re.compile(_TERM)
# term, then perhaps a symbol in brackets, a joining word or mark, the number
_AFTER = re.compile(
    _TERM + r"(?: ?\([^()\n]{0,20}\))?(?:,? n(?:_\{?\w{1,6}\}?)?)?"
    # "of about 4.2" and "≈ 2.1" report what a design came to, not what it
    # was designed to, and are left unread
    r"(?: ?(?:of at least|of|>=|≥|=|:|\||is|at least)){0,2}"
    r"(?: n(?:_\{?\w{1,6}\}?)? ?=)? ?(?=\d)")
_BEFORE = re.compile(
    r"(?<![\d.])(\d{1,2}(?:\.\d{1,2})?)(?: ?×|:1|-fold| times)? (?i:safety factor|"
    r"factor of safety)")
_RANGE = re.compile(r" ?(?:-|–|—|to) ?(?=\d)")
_COMPUTED = re.compile(r"\b(?:actual|achieved|resulting|calculated|computed|"
                       r"provide[sd]?|gives|giving|yield(?:s|ing)|obtained)\b",
                       re.IGNORECASE)
# part of a sum, or set against a limit: "SF = 1.8 > 1.5"
# "so FS >= 1.3" concludes; "FS >= 1.3 is required" sets out
_CONCLUDED = re.compile(r"\b(?:so|thus|hence|therefore)\b", re.IGNORECASE)
_AT_LEAST = re.compile(r">=|≥")
_EXPRESSION = re.compile(r" ?[/×*÷<>≥≤]")


def _chosen(written):
    """A factor someone chooses is round (1.5, 2, 1.25); 2.87 is a result."""
    decimals = written.partition(".")[2]
    return len(decimals) < 2 or len(decimals) == 2 and decimals[1] in "05"


def _safety(inputs, doc, text):
    values, ranged, mentioned = set(), False, False
    for hit, _ in zip(_MENTION.finditer(text), range(MAX_HITS)):
        mentioned = True
        start = text.rfind("\n", max(hit.start() - 60, 0), hit.start())
        before = text[max(start, hit.start() - 40, 0):hit.start()]
        computed = _COMPUTED.search(before)
        after = _AFTER.match(text, hit.start())
        if not after or computed \
                or _AT_LEAST.search(after[0]) and _CONCLUDED.search(before):
            continue
        match = NUMBER.match(text, after.end())
        if not match or _EXPRESSION.match(text, match.end()):
            continue
        number = parse(match)
        value = number.value
        if not 1 <= value <= 20 or not _chosen(number.mantissa):
            continue
        span = _RANGE.match(text, match.end())
        if span and NUMBER.match(text, span.end()):
            ranged = True
            continue
        values.add(canonical(value))
    for hit, _ in zip(_BEFORE.finditer(text), range(MAX_HITS)):
        before = text[max(hit.start() - 40, 0):hit.start()].rsplit("\n", 1)[-1]
        value = float(hit[1])
        if 1 <= value <= 20 and _chosen(hit[1]) and not _COMPUTED.search(before) \
                and not before.rstrip().endswith(("-", "–", " to")):
            values.add(canonical(value))
    if values:
        factor = _one(values)
    else:
        factor = "range" if ranged else None if mentioned else "none"
    return {"safety_factor": factor, "safety_factor_mentioned": mentioned,
            "safety_factor_values": sorted(values)[:50]}


# --- standards ----------------------------------------------------------------

_BODY = (r"(?:BS EN ISO|DIN EN ISO|BS EN|DIN EN|EN ISO|DIN ISO|AS/NZS|GB/T|ISO|DIN|EN|"
         r"BS|ASTM|ASME|ANSI|AGMA|AISC|JIS|IEC|UL|NEMA|AWS|ACI|API|CSA|NFPA|VDI|IEEE)")
_DESIGNATION = re.compile(
    rf"(?<![A-Za-z0-9/])(?P<body>{_BODY})(?:[ \-]| ?#)?"
    r"(?P<number>(?:[A-Z]{1,2}\.?)?\d{1,6}[A-Z]?(?:[\-.:/]\d{1,4}){0,3})(?![A-Za-z0-9])")
_EUROCODE = re.compile(r"\bEurocode(?: (\d)(?!\d))?")
_BARE_BODY = re.compile(r"(?<![A-Za-z])(AISC|AGMA|Eurocode)(?![A-Za-z])")


def _standards(inputs, doc, text):
    standards, bodies = set(), set()
    for hit, _ in zip(_DESIGNATION.finditer(text), range(MAX_HITS)):
        standards.add(f"{hit['body']} {hit['number'].rstrip('.')}")
        bodies.add(hit["body"].split()[0])
    for hit, _ in zip(_EUROCODE.finditer(text), range(MAX_HITS)):
        if hit[1]:
            standards.add(f"Eurocode {hit[1]}")
    bodies |= {m[1] for m, _ in zip(_BARE_BODY.finditer(text), range(MAX_HITS))}
    return {"standards": sorted(standards)[:100],
            "standard_bodies": sorted(bodies),
            "standards_cited": bool(bodies)}


# --- checks, spring ends, stress correction -------------------------------------

_CHECKS = _table((
    ("bending", r"\bbending\b"),
    ("shear", r"\bshear\b"),
    ("torsion", r"(?<!lateral-)(?<!lateral )\btorsion(?:al)?\b"),
    ("deflection", r"\bdeflect(?:s|ion|ions)?\b"),
    ("yield", r"\byield(?:ing)? (?:strength|stress|limit|check)|\bon yield\b|\byielding\b"),
    ("buckling", r"\bbuckl\w{0,6}"),
    ("fatigue", r"\bfatigue\b|\bGoodman\b|\bendurance (?:limit|strength)"),
    ("natural-frequency", r"\bnatural frequency\b|\bresonance\b|\bsurge frequency\b"),
    ("coil-bind", r"\bcoil[- ]bind\w{0,3}|\bsolid (?:length|height|stress)\b|"
                  r"\bclash allowance\b"),
    ("bearing-stress", r"\bbearing stress\b"),
    ("screw-load", r"\bpull[- ]?out\b|\btear[- ]?out\b|\bshear (?:on|in) (?:each|the) "
                   r"screws?\b|\b(?:force|load) (?:on|per) (?:each )?screws?\b"),
    ("stress-concentration", r"\bstress concentration\b"),
    ("creep", r"\bcreep\b"),
    ("cavitation", r"\bcavitat\w{0,6}|\bNPSH\w{0,2}"),
    ("weld", r"\bwelds?\b|\bweld(?:ed)? (?:strength|stress|size)"),
    ("junction-temperature", r"\bjunction temperature\b"),
))
_SPRING = re.compile(r"\bcoils?\b|\bwire diameter\b|\bcompression spring\b|"
                     r"\bspring (?:rate|constant|design|index|steel|wire)\b", re.IGNORECASE)
_SPRING_WORD = re.compile(r"\bsprings?\b", re.IGNORECASE)
_SQUARED = r"(?:squared?|closed)"
_GROUND_JOIN = (r"(?:[- ](?:ends?)?[ ,\-]{0,3}(?:\(squared\) ?)?(?:and |& |\+ )?"
                r"(?:then )?)")
_ENDS = _table((
    ("squared-and-ground", rf"\b{_SQUARED}(?: \((?:squared|closed)\))?{_GROUND_JOIN}ground\b"),
    ("squared", rf"\b{_SQUARED}(?: but)?[- ](?:not ground|unground)\b|"
                rf"\b{_SQUARED}(?: \((?:squared|closed)\))? ends?\b(?![ ,\-]{{0,3}}"
                r"(?:and |& |\+ )?(?:then )?ground\b)"),
    ("plain-and-ground", r"\bplain[ ,\-]{1,3}(?:ends?[ ,\-]{1,3})?(?:and |& )?ground\b"),
    ("plain", r"\bplain ends?\b(?![ ,\-]{0,3}(?:and |& )?ground\b)"),
    ("open", r"\bopen(?:-coil)? ends?\b"),
))
# a row or line that declares the end type
_DECLARED = re.compile(
    r"\bend(?:s| ?-?(?:type|style|condition|treatment|configuration)s?)[ ]?[:|=]"
    r"([^.\n]{0,80})", re.IGNORECASE)


def _end_type(text):
    declared = "\n".join(
        "ends: " + m[1] for m, _ in zip(_DECLARED.finditer(text), range(MAX_HITS)))
    for part in (declared, text):
        found = _found(_ENDS, part)
        if not found and part is declared:
            # "Ends: squared and ground" or "End type: plain": the word alone
            for name, pattern in (
                    ("squared-and-ground", rf"{_SQUARED}[^|\n]{{0,20}}\bground\b"),
                    ("squared", rf"ends: ?\|? ?{_SQUARED}"),
                    ("plain", r"ends: ?\|? ?plain\b")):
                if re.search(pattern, part, re.IGNORECASE):
                    found = [name]
                    break
        if found:
            return found[0] if len(found) == 1 else "several"
    return "not-stated"


def _checks(inputs, doc, text):
    values = {"checks": _found(_CHECKS, text)}
    if not (_SPRING.search(text) or _SPRING_WORD.search(text)
            and _found(_ENDS, text)):
        values.update(spring_end_type="no-spring", stress_correction="no-spring")
        return values
    wahl = re.search(r"\bWahl", text) is not None
    bergstrasser = re.search(r"\bBergstr(?:ä|a|ae)(?:ss|ß)er", text) is not None
    values["spring_end_type"] = _end_type(text)
    values["stress_correction"] = (
        "both" if wahl and bergstrasser else "wahl" if wahl
        else "bergstrasser" if bergstrasser else "not-mentioned")
    return values


# --- materials ----------------------------------------------------------------

_SPECIAL_STEEL = re.compile(r"\b(?:stainless|spring)[- ]steel\b", re.IGNORECASE)
_MATERIALS = _table((
    ("aluminum", r"\balumini?um\b|\b(?:6061|6063|7075|2024|5052)-?T\d"),
    ("stainless-steel", r"\bstainless\b|\bAISI (?:30[1-4]|316)\b"),
    ("spring-steel", r"\bmusic wire\b|\bpiano wire\b|\bspring steel\b|\bchrome[- ]"
                     r"(?:silicon|vanadium)\b|\bhard[- ]drawn\b|\boil[- ]tempered\b|"
                     r"\bASTM A22[789]\b"),
    ("cast-iron", r"\bcast iron\b|\bductile iron\b"),
    ("copper", r"\bcopper\b"),
    ("brass", r"\bbrass\b"),
    ("bronze", r"\bbronze\b"),
    ("titanium", r"\btitanium\b"),
    ("wood", r"\bplywood\b|\bMDF\b|\btimber\b|\blumber\b|\bwood(?:en)?\b(?! screws?)|"
             r"\bbirch\b|\boak\b|\bpine\b"),
    ("polyethylene", r"\bpolyethylene\b|\b[HLM]DPE\b|\bPE[- ]?(?:80|100|X)\b"),
    ("pvc", r"\b[uc]?PVC\b"),
    ("nylon", r"\bnylon\b|\bpolyamide\b"),
    ("acrylic", r"\bacrylic\b|\bPMMA\b"),
    ("polycarbonate", r"\bpolycarbonate\b"),
    ("graphite", r"\bgraphite\b"),
))
_PRINTED = _table((("pla", r"\bPLA\+?\b"), ("petg", r"\bPETG\b"),
                   ("abs", r"\bABS\b(?! ?\()")), flags=0)
_STEEL = re.compile(r"\bsteel\b|\bS(?:235|275|355)\b|\bA36\b|\b(?:AISI|SAE) ?10\d\d\b",
                    re.IGNORECASE)


def _materials(inputs, doc, text):
    found = set(_found(_MATERIALS, text)) | set(_found(_PRINTED, text))
    if _STEEL.search(_SPECIAL_STEEL.sub(" ", text)):
        found.add("steel")
    return {"materials": sorted(found)}


# --- stated values ------------------------------------------------------------

_VOLTS = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{1,2})?)(?:[ -]?V(?:DC|AC|ac|dc)?|[ -]volts?)"
    r"(?![A-Za-z0-9^/²³_=])(?! ?=)")
_PIPE = re.compile(r"\bpipes?\b|\bpipework\b|\bpiping\b", re.IGNORECASE)
_ROUGHNESS = re.compile(
    r"(?:ε|\b[Rr]oughness\b|\be(?= ?= ?\d))[^\n\d]{0,60}?(?<![\d.])(?=\d)")
_LENGTH = re.compile(r" ?(mm|µm|μm|um|m)(?![A-Za-z/^])")
_TO_MM = {"mm": 1, "µm": 1e-3, "μm": 1e-3, "um": 1e-3, "m": 1e3}
_WATER = re.compile(r"\bwater\b", re.IGNORECASE)
_WATER_TEMPERATURE = (
    re.compile(r"\bwater\b[^\n\d]{0,30}?(\d{1,2}(?:\.\d)?) ?°C", re.IGNORECASE),
    re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d)?) ?°C water\b", re.IGNORECASE),
    re.compile(r"\bwater temperature\b[^\n\d]{0,30}?(\d{1,2}(?:\.\d)?)", re.IGNORECASE),
)


def _quantities(inputs, doc, text):
    volts = {canonical(float(m[1])) for m, _ in
             zip(_VOLTS.finditer(text), range(MAX_HITS)) if float(m[1]) >= 3}
    values = {"supply_voltage": _one(volts),
              "supply_voltages": sorted(volts)[:50]}
    if _PIPE.search(text):
        rough = set()
        for hit, _ in zip(_ROUGHNESS.finditer(text), range(MAX_HITS)):
            match = NUMBER.match(text, hit.end())
            unit = match and _LENGTH.match(text, match.end())
            if unit:
                size = parse(match).value * _TO_MM[unit[1]]
                if 0 < size <= 10:
                    rough.add(canonical(size))
        values["pipe_roughness_mm"] = _one(rough)
    else:
        values["pipe_roughness_mm"] = "not-relevant"
    if _PIPE.search(text) and _WATER.search(text):
        warm = {canonical(float(m[1])) for pattern in _WATER_TEMPERATURE
                for m, _ in zip(pattern.finditer(text), range(MAX_HITS))}
        values["water_temperature_c"] = _one(warm)
    else:
        values["water_temperature_c"] = "not-relevant"
    values["quantities"] = sorted(
        {f"{value} {unit}" for value, unit in _found_quantities(inputs)
         if value is not None})[:200]
    return values


# --- CAD and drawing files ------------------------------------------------------

_CAD_LANGUAGES = ("openscad", "dxf", "step", "stl", "svg", "gcode")
_CAD_PYTHON = _table((
    ("cadquery", r"^[ \t]{0,40}(?:import|from) cadquery\b"),
    ("build123d", r"^[ \t]{0,40}(?:import|from) build123d\b"),
    ("freecad", r"^[ \t]{0,40}(?:import|from) (?:FreeCAD|Part)\b"),
    ("ezdxf", r"^[ \t]{0,40}(?:import|from) ezdxf\b"),
    ("solidpython", r"^[ \t]{0,40}(?:import|from) (?:solid|solid2)\b"),
    ("svg-python", r"^[ \t]{0,40}(?:import|from) (?:svgwrite|drawsvg)\b"),
), flags=re.MULTILINE)
_SCAD_PARAMETER = re.compile(
    r"^([A-Za-z_]\w{0,40}) ?= ?(-?\d{1,9}(?:\.\d{1,9})?) ?;", re.MULTILINE)
_PYTHON_PARAMETER = re.compile(
    r"^([A-Za-z_]\w{0,40}) ?= ?(-?\d{1,9}(?:\.\d{1,9})?)[ \t]{0,10}(?:#[^\n]{0,200})?$",
    re.MULTILINE)
_SPACING = re.compile(r"[ \t]{2,}")


def _cad(inputs, doc, text):
    formats, languages, parameters = set(), set(), set()
    for source in doc.files:
        if source.language in _CAD_LANGUAGES:
            formats.add(source.language)
        if source.language not in code.PROGRAMMING and source.language != "openscad":
            continue
        languages.add(source.language)
        script = _SPACING.sub(" ", code.split(
            "c" if source.language == "openscad" else source.language,
            source.text).code).replace(" \n", "\n")
        pattern = None
        if source.language == "openscad":
            pattern = _SCAD_PARAMETER
        elif source.language == "python":
            kinds = _found(_CAD_PYTHON, script)
            formats |= set(kinds)
            pattern = _PYTHON_PARAMETER if kinds else None
        if pattern:
            for hit, _ in zip(pattern.finditer(script), range(MAX_HITS)):
                parameters.add(f"{hit[1]}={canonical(float(hit[2]))}")
    unread = any(b.body.strip() for b in doc.blocks) and not doc.files
    return {"cad_format": None if unread else _one(formats, "none"),
            "cad_formats": sorted(formats),
            "code_languages": sorted(languages),
            "cad_parameters": sorted(parameters)[:100]}


_VERSIONS = {"units": "3", "safety": "2", "quantities": "3"}
EXTRACTORS = tuple(
    Extractor(f"engineering.{name}", _VERSIONS.get(name, "1"), "engineering",
              _extractor_values(build), summary)
    for name, build, summary in (
        ("units", _units, "unit system of the quantities"),
        ("safety", _safety, "the safety factor and its value"),
        ("standards", _standards, "standards cited by designation"),
        ("checks", _checks, "checks named, spring ends, stress correction"),
        ("materials", _materials, "material names found"),
        ("quantities", _quantities, "supply voltage, roughness, other quantities"),
        ("cad", _cad, "CAD or drawing format, code languages, parameters"),
    ))
