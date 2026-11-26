"""Responsiveness: the viewport tag, media query breakpoints and their
direction, Tailwind breakpoint variants and fluid sizing."""

import re

from extractors.base import Extractor
from extractors.website import tailwind
from extractors.website.css import walk
from extractors.website.site import get_site

NAME, VERSION = "website.responsiveness", "1"
_MIN_MAX = re.compile(r"\b(min|max)-width\s*:\s*(\d{1,5}(?:\.\d{1,4})?)\s*(px|em|rem)")
_RANGE = re.compile(r"\bwidth\s*([<>]=?)\s*(\d{1,5}(?:\.\d{1,4})?)\s*(px|em|rem)"
                    r"|(\d{1,5}(?:\.\d{1,4})?)\s*(px|em|rem)\s*([<>]=?)\s*width\b")
_VIEWPORT_UNITS = frozenset({"vw", "vh", "dvh", "svh", "lvh", "vmin", "vmax",
                             "dvw", "svw", "lvw"})


def _px(number, unit):
    value = float(number) * (16 if unit in ("em", "rem") else 1)
    return int(round(value))


def breakpoints(prelude):
    """``[(direction, px)]`` for the width conditions of a media prelude:
    ``min`` for min-width or width >=, ``max`` for max-width or width <=."""
    found = []
    lowered = prelude.lower()
    for match in _MIN_MAX.finditer(lowered):
        found.append((match.group(1), _px(match.group(2), match.group(3))))
    for match in _RANGE.finditer(lowered):
        if match.group(1):
            direction = "min" if ">" in match.group(1) else "max"
            found.append((direction, _px(match.group(2), match.group(3))))
        else:
            direction = "max" if ">" in match.group(6) else "min"
            found.append((direction, _px(match.group(4), match.group(5))))
    return found


def viewport(site):
    if site.entry is None:
        return None
    for element in site.entry.find("meta"):
        if element.attrs.get("name", "").lower() == "viewport":
            content = element.attrs.get("content", "").lower().replace(" ", "")
            return "device-width" if "width=device-width" in content else "other"
    return "absent"


def extract(inputs):
    site = get_site(inputs)
    if not site.has_markup and not site.sheets:
        return {"status": "no-input"}
    queries, points, directions = 0, set(), {"min": 0, "max": 0}
    fluid = set()
    for sheet in site.sheets:
        for keyword, prelude, _ in sheet.at_rules:
            if keyword == "container":
                fluid.add("container-queries")
            if keyword != "media":
                continue
            found = breakpoints(prelude)
            if found:
                queries += 1
            for direction, px in found:
                points.add(px)
                directions[direction] += 1
    for declaration in site.declarations():
        prop, text = declaration.prop, declaration.text.lower()
        if prop in ("container-type", "container"):
            fluid.add("container-queries")
        if prop == "flex-wrap" and "wrap" in text and "nowrap" not in text:
            fluid.add("flex-wrap")
        if prop == "grid-template-columns" and ("auto-fit" in text
                                                or "auto-fill" in text):
            fluid.add("auto-fit-grid")
        for node in walk(declaration.value):
            if node.type == "function":
                if node.lower_name == "clamp":
                    fluid.add("clamp")
                elif node.lower_name in ("min", "max"):
                    fluid.add("min-max")
            elif node.type == "dimension" and node.lower_unit in _VIEWPORT_UNITS:
                fluid.add("viewport-units")
    variants = set()
    for utility, _, _ in site.utilities():
        for variant in utility.variants:
            if variant in tailwind.BREAKPOINTS or (
                    variant.startswith("max-") and variant[4:] in tailwind.BREAKPOINTS):
                variants.add(variant)
        if utility.base == "flex-wrap":
            fluid.add("flex-wrap")
        if utility.base.startswith(("@container", "@container/")):
            fluid.add("container-queries")
    images = any(e.tag == "picture" or "srcset" in e.attrs
                 for _, e in site.elements() if not e.component)
    if directions["min"] > directions["max"]:
        style = "mobile-first"
    elif directions["max"] > directions["min"]:
        style = "desktop-first"
    else:
        style = "mixed" if directions["min"] else "none"
    if style == "none" and variants:
        style = "mobile-first"  # Tailwind's breakpoints are min-width
    return {
        "status": site.status(),
        "viewport_meta": viewport(site),
        "width_media_queries": queries,
        "breakpoints_px": sorted(points),
        "media_query_style": style,
        "tailwind_breakpoints": sorted(variants, key=lambda v: (
            v.startswith("max-"), tailwind.BREAKPOINTS.index(v.removeprefix("max-")))),
        "fluid_techniques": sorted(fluid),
        "responsive_images": images,
    }


EXTRACTOR = Extractor(NAME, VERSION, "website", extract,
                      "viewport tag, breakpoints, Tailwind variants, fluid sizing")
