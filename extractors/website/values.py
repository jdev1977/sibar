"""Reading CSS values: colours (following ``var()``), lengths and helpers
shared by the website extractors."""

import tinycss2

from extractors.website import colors
from extractors.website.css import is_page_selector, significant, walk

# Properties whose plain words (``red``, ``navy``) are colours.
COLOR_PROPERTIES = frozenset({
    "color", "background", "background-color", "background-image", "border",
    "border-color", "border-top", "border-right", "border-bottom", "border-left",
    "border-top-color", "border-right-color", "border-bottom-color",
    "border-left-color", "border-block", "border-inline", "border-block-color",
    "border-inline-color", "outline", "outline-color", "box-shadow", "text-shadow",
    "fill", "stroke", "stop-color", "caret-color", "accent-color", "column-rule",
    "column-rule-color", "text-decoration", "text-decoration-color", "filter",
    "scrollbar-color", "text-emphasis-color", "flood-color", "lighting-color",
    "-webkit-text-fill-color", "-webkit-text-stroke-color", "-webkit-text-stroke",
})
MAX_VAR_DEPTH = 4
FONT_SIZE_PX = 16  # rem and em are read as 16px


class Resolver:
    """Custom properties of a site, for following ``var(--name)``.

    A name takes its value from the last declaration outside ``@media`` on
    ``:root``, ``html`` or ``body``; failing that, from the last outside
    ``@media`` whose selector does not mention dark.
    """

    def __init__(self, declarations):
        page, other = {}, {}
        for declaration in declarations:
            if not declaration.prop.startswith("--") or declaration.media:
                continue
            if is_page_selector(declaration.selector) or declaration.selector in (
                    ":root", "@theme"):
                page[declaration.prop] = declaration
            elif "dark" not in declaration.selector.lower():
                other[declaration.prop] = declaration
        self.values = {**other, **page}

    def lookup(self, name):
        declaration = self.values.get(name.lower() if name.startswith("--")
                                      else name)
        return declaration.value if declaration is not None else None


def color_nodes(nodes, prop, resolver=None, depth=0):
    """``(hex, alpha)`` of each colour in ``nodes``, in order; and the count
    of colour values that could not be read (``var()`` that does not
    resolve, ``lab()``, ``color()``...)."""
    found, unread = [], 0
    words_are_colors = prop in COLOR_PROPERTIES or (
        prop.startswith("--") and len(significant(nodes)) == 1)
    skip = set()
    for node in walk(nodes):
        if id(node) in skip:
            continue
        kind = node.type
        if kind == "hash":
            parsed = colors.parse_hex(node.value)
            if parsed:
                found.append(parsed)
        elif kind == "ident" and words_are_colors:
            hex_color = colors.named(node.value)
            if hex_color:
                found.append((hex_color, 1.0))
        elif kind == "function":
            name = node.lower_name
            if name in colors.COLOR_FUNCTIONS:
                parsed = colors.parse_function(node)
                if parsed:
                    found.append(parsed)
                else:
                    unread += 1
                skip.update(id(n) for n in walk(node.arguments))
            elif name in colors.UNREAD_COLOR_FUNCTIONS:
                unread += 1
                skip.update(id(n) for n in walk(node.arguments))
            elif name == "var":
                args = significant(node.arguments)
                target = args[0].value if args and args[0].type == "ident" else ""
                value = resolver.lookup(target) if resolver and depth < MAX_VAR_DEPTH \
                    else None
                if value is not None:
                    inner, missing = color_nodes(value, prop, resolver, depth + 1)
                    found += inner
                    unread += missing
                    skip.update(id(n) for n in walk(node.arguments))
                elif not any(a.type == "literal" and a.value == "," for a in args):
                    unread += 1
    return found, unread


def visible(found):
    """Hex colours from :func:`color_nodes` that are not fully transparent."""
    return [hex_color for hex_color, alpha in found if alpha > 0]


def parse_color_text(text):
    """A colour written in an HTML attribute, as ``#rrggbb``, or None."""
    text = (text or "").strip()
    if not text or len(text) > 100:
        return None
    if text.startswith("#"):
        parsed = colors.parse_hex(text)
        return parsed[0] if parsed and parsed[1] > 0 else None
    if text.isalpha():
        return colors.named(text)
    try:
        node = tinycss2.parse_one_component_value(text)
    except Exception:  # noqa: BLE001 - malformed attribute text
        return None
    if getattr(node, "type", "") == "function":
        parsed = colors.parse_function(node)
        return parsed[0] if parsed and parsed[1] > 0 else None
    return None


def to_px(node):
    """A length token in px (rem and em as 16px, 0 as 0), else None.
    Percentages give None; callers that want them check first."""
    if node.type == "number" and node.value == 0:
        return 0.0
    if node.type != "dimension":
        return None
    unit = node.lower_unit
    if unit == "px":
        return float(node.value)
    if unit in ("rem", "em"):
        return float(node.value) * FONT_SIZE_PX
    if unit == "pt":
        return float(node.value) * 4 / 3
    return None


def px_text(value):
    """A px number as text: ``8px``, ``12.5px``."""
    value = round(value * 2) / 2
    return f"{int(value)}px" if value == int(value) else f"{value}px"


def sorted_counts(counter):
    """A Counter as a dict sorted by key (for stable output)."""
    return {key: counter[key] for key in sorted(counter)}


def most_common(counter, prefer=None):
    """The key with the highest count; ties go to the first in sorted order
    (or by ``prefer``, a sort key). None when empty."""
    if not counter:
        return None
    best = max(counter.values())
    tied = [key for key, count in counter.items() if count == best]
    return min(tied, key=prefer) if prefer else min(tied)

