"""Reading CSS values: colours (following ``var()``), lengths and helpers
shared by the website extractors."""

import re

import tinycss2

from extractors.website import colors
from extractors.website.css import (
    is_dark_page_selector, is_page_selector, serialize, significant, walk,
)

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
# Bounds on following var(): a custom property whose value, with its own
# var()s substituted, passes MAX_EXPANDED nodes (or MAX_TEXT characters as
# text) is treated as unreadable; each property is expanded once and its
# colours read once (memoised), so fan-out (--a: var(--b) var(--b) ...) and
# huge values cost linear time.
MAX_EXPANDED = 200
MAX_TEXT = 300
MAX_VAR_COLORS = 50
FONT_SIZE_PX = 16  # rem and em are read as 16px


class Resolver:
    """Custom properties of a site, for following ``var(--name)``.

    A name takes its value from the last declaration outside ``@media`` on
    ``:root``, ``html`` or ``body``; failing that, from the last outside
    ``@media`` whose selector does not mention dark. With ``dark`` (a page
    forced into its dark theme), declarations on dark selectors of the page
    (``.dark``, ``html.dark``, ``[data-theme="dark"]``) win over both.
    """

    def __init__(self, declarations, dark=False):
        page, other, forced = {}, {}, {}
        for declaration in declarations:
            if not declaration.prop.startswith("--") or declaration.media:
                continue
            if is_page_selector(declaration.selector) or declaration.selector in (
                    ":root", "@theme"):
                page[declaration.prop] = declaration
            elif dark and is_dark_page_selector(declaration.selector):
                forced[declaration.prop] = declaration
            elif "dark" not in declaration.selector.lower():
                other[declaration.prop] = declaration
        self.values = {**other, **page, **forced}
        self._expanded, self._text, self._colors = {}, {}, {}

    def lookup(self, name):
        declaration = self.values.get(name.lower() if name.startswith("--")
                                      else name)
        return declaration.value if declaration is not None else None

    def expanded(self, name, depth=0):
        """The value of ``name`` with its top-level ``var()``s substituted,
        or None if unknown, cyclic or over :data:`MAX_EXPANDED` nodes."""
        key = name.lower()
        if key in self._expanded:
            return self._expanded[key]
        self._expanded[key] = None  # in progress: a cycle reads as unknown
        value = self.lookup(key)
        result = None
        if value is not None:
            result = []
            for node in value:
                inner = None
                if (node.type == "function" and node.lower_name == "var"
                        and depth < MAX_VAR_DEPTH):
                    args = significant(node.arguments)
                    if args and args[0].type == "ident":
                        inner = self.expanded(args[0].value, depth + 1)
                if inner is None:
                    result.append(node)
                else:
                    result += inner
                if len(result) > MAX_EXPANDED:
                    result = None
                    break
        self._expanded[key] = result
        return result

    def text(self, name):
        """:meth:`expanded` as text, or None when over :data:`MAX_TEXT`."""
        key = name.lower()
        if key not in self._text:
            nodes = self.expanded(key)
            text = serialize(nodes) if nodes is not None else ""
            self._text[key] = text if text and len(text) <= MAX_TEXT else None
        return self._text[key]

    def colors_of(self, name, prop, depth):
        """``color_nodes`` of a property's value, read once per property."""
        words = prop in COLOR_PROPERTIES or prop.startswith("--")
        key = (name.lower(), words)
        if key not in self._colors:
            nodes = self.expanded(name)
            if nodes is None:
                self._colors[key] = None
            else:
                found, unread = color_nodes(nodes, prop, self, depth + 1)
                self._colors[key] = (found[:MAX_VAR_COLORS], unread)
        return self._colors[key]


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
                if parsed is None and resolver:
                    # hsl(var(--primary)) with --primary: 221 83% 53% (shadcn)
                    text = node.serialize()
                    if "var(" in text and len(text) <= MAX_TEXT:
                        hex_color = parse_color_text(resolve_text(text, resolver))
                        parsed = (hex_color, 1.0) if hex_color else None
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
                read = (resolver.colors_of(target, prop, depth)
                        if resolver and target and depth < MAX_VAR_DEPTH else None)
                if read is not None:
                    found += read[0]
                    unread += read[1]
                    skip.update(id(n) for n in walk(node.arguments))
                elif not any(a.type == "literal" and a.value == "," for a in args):
                    unread += 1
    return found, unread


def substitute_vars(nodes, resolver, depth=0):
    """``nodes`` with each top-level ``var(--name)`` replaced by the value it
    resolves to (followed :data:`MAX_VAR_DEPTH` levels); an unresolved
    ``var()`` is kept, so callers can tell it was not read."""
    result = []
    for node in nodes or ():
        if node.type == "function" and node.lower_name == "var" and resolver:
            args = significant(node.arguments)
            value = (resolver.expanded(args[0].value)
                     if args and args[0].type == "ident" else None)
            if value is not None:
                result += value
                continue
        result.append(node)
    return result


_VAR_TEXT = re.compile(r"var\(\s*(--[\w-]{1,100})\s*(?:,[^()]{0,200})?\)")


def resolve_text(text, resolver):
    """``text`` with each ``var(--name)`` replaced by the text of its value
    (four rounds at most, so a cycle stops). Text longer than
    :data:`MAX_TEXT`, before or after a round, is returned as it is: it is
    not a colour."""
    def value(match):
        return resolver.text(match.group(1)) or match.group(0)

    for _ in range(MAX_VAR_DEPTH):
        if "var(" not in text or len(text) > MAX_TEXT:
            break
        changed = _VAR_TEXT.sub(value, text)
        if changed == text:
            break
        text = changed
    return text


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

