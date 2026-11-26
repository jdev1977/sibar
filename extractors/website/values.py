"""Reading CSS values: colours (following ``var()``), lengths and helpers
shared by the website extractors."""

import re
from itertools import islice

import tinycss2

from extractors.website import colors
from extractors.website.css import (
    MAX_VALUE_DEPTH, is_dark_page_selector, is_page_selector, serialize,
    significant, walk,
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
MAX_VAR_DEPTH = 4  # rounds of var() substitution in colour-function text
# Bounds on following var(), so that a hostile stylesheet costs time in
# proportion to its size and no more:
# - a custom property whose value, with its top-level var()s substituted,
#   holds more than MAX_EXPANDED component values is unreadable. Every value
#   counts, also those inside functions and blocks, so nesting hides nothing;
# - as text inside a colour function the limit is MAX_TEXT characters;
# - at most MAX_VAR_COLORS colours are taken from one property;
# - each property is expanded once and its colours read once (memoised);
# - every use of a property is charged against one budget per page,
#   MAX_PAGE_WORK: a component value spliced in or a character substituted
#   costs one unit. When the budget is spent, the var()s that follow are left
#   unresolved. Ordinary pages use a small part of it.
MAX_EXPANDED = 400
MAX_TEXT = 300
MAX_VAR_COLORS = 50
MAX_PAGE_WORK = 300_000
FONT_SIZE_PX = 16  # rem and em are read as 16px

_MISSING, _PENDING, _CYCLE = object(), object(), object()


def _var_target(node):
    """The custom property a ``var()`` node names (lower case), else None."""
    if node.type != "function" or node.lower_name != "var":
        return None
    for argument in node.arguments:
        if argument.type in ("whitespace", "comment"):
            continue
        return argument.value.lower() if argument.type == "ident" else None
    return None


def _size(node, limit):
    """Component values in ``node``, itself included, counted to ``limit``."""
    return sum(1 for _ in islice(walk((node,)), max(limit, 1)))


def _scan(nodes):
    """:func:`walk` that does not enter colour functions (they are read
    whole)."""
    stack = [iter(nodes or ())]
    while stack:
        node = next(stack[-1], None)
        if node is None:
            stack.pop()
            continue
        yield node
        if node.type == "function":
            if (node.lower_name in colors.COLOR_FUNCTIONS
                    or node.lower_name in colors.UNREAD_COLOR_FUNCTIONS):
                continue
            inner = node.arguments
        elif node.type in ("() block", "[] block", "{} block"):
            inner = node.content
        else:
            inner = None
        if inner and len(stack) <= MAX_VALUE_DEPTH:
            stack.append(iter(inner))


class Resolver:
    """Custom properties of a site, for following ``var(--name)``.

    A name takes its value from the last declaration outside ``@media`` on
    ``:root``, ``html`` or ``body``; failing that, from the last outside
    ``@media`` whose selector does not mention dark. With ``dark`` (a page
    forced into its dark theme), declarations on dark selectors of the page
    (``.dark``, ``html.dark``, ``[data-theme="dark"]``) win over both.

    What a name resolves to depends on the stylesheet alone, never on which
    rule asked first: alias chains are followed to any length (without
    recursion), and a property that reaches a cycle is unreadable. The one
    exception is a page that spends :data:`MAX_PAGE_WORK`: from then on
    nothing more resolves (the same page still gives the same result).
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
        self._expanded, self._sizes, self._text, self._colors = {}, {}, {}, {}
        self._resolved = {}
        self.budget = MAX_PAGE_WORK

    def spend(self, units):
        """Charge ``units`` of work to the page; False once the budget is
        spent (and then for every later call)."""
        if units >= self.budget:
            self.budget = 0
            return False
        self.budget -= max(units, 1)
        return True

    def lookup(self, name):
        declaration = self.values.get(name.lower() if name.startswith("--")
                                      else name)
        return declaration.value if declaration is not None else None

    def expanded(self, name):
        """The value of ``name`` with its top-level ``var()``s substituted
        (a ``var()`` naming an unreadable property is kept as it is). None if
        the property is unknown, reaches a cycle of top-level ``var()``s, or
        holds more than :data:`MAX_EXPANDED` component values."""
        key = name.lower()
        if key not in self._expanded:
            self._expand(key)
        state = self._expanded[key]
        return None if state is _CYCLE else state

    def size(self, name):
        """Component values in :meth:`expanded`, nested ones included."""
        return self._sizes.get(name.lower(), 0)

    def _expand(self, start):
        # Depth first without recursion: a chain of 100,000 aliases is fine.
        # A name is _PENDING exactly while it is an ancestor of the one in
        # hand, so meeting a _PENDING name is meeting a cycle.
        memo, stack = self._expanded, [start]
        while stack:
            key = stack[-1]
            state = memo.get(key, _MISSING)
            if state is not _MISSING and state is not _PENDING:
                stack.pop()
                continue
            declaration = self.values.get(key)
            if declaration is None:
                memo[key] = None
                stack.pop()
                continue
            if state is _MISSING:
                memo[key] = _PENDING
                todo = [target for target in dict.fromkeys(
                    map(_var_target, declaration.value))
                    if target and target not in memo]
                if todo:
                    stack.extend(todo)
                    continue
            stack.pop()
            memo[key] = self._splice(key, declaration.value)

    def _splice(self, key, value):
        memo = self._expanded
        targets = [_var_target(node) for node in value]
        if any(memo.get(target) is _PENDING or memo.get(target) is _CYCLE
               for target in targets if target):
            return _CYCLE
        result, size = [], 0
        for node, target in zip(value, targets):
            inner = memo.get(target) if target else None
            if inner is None:
                result.append(node)
                size += _size(node, MAX_EXPANDED + 1 - size)
            else:
                size += self._sizes[target]
                if not self.spend(self._sizes[target]):
                    return None
                result += inner
            if size > MAX_EXPANDED:
                return None
        self._sizes[key] = size
        return result

    def text(self, name):
        """:meth:`expanded` as text, or None when over :data:`MAX_TEXT`."""
        key = name.lower()
        if key not in self._text:
            nodes = self.expanded(key)
            text = ""
            if nodes is not None and self.spend(self.size(key)):
                text = serialize(nodes)
            self._text[key] = text if text and len(text) <= MAX_TEXT else None
        return self._text[key]

    def colors_of(self, name, prop):
        """``color_nodes`` of a property's value, read once per property;
        None if the property is unreadable or reaches a cycle through the
        ``var()``s inside its value."""
        words = prop in COLOR_PROPERTIES or prop.startswith("--")
        start = (name.lower(), words)
        if start not in self._colors:
            self._read_colors(start, prop)
        state = self._colors[start]
        if state is None or state is _CYCLE or not self.spend(1 + len(state[0])):
            return None
        return state

    def _read_colors(self, start, prop):
        # As _expand: the properties named inside a value are read first, so
        # color_nodes below finds them memoised and never recurses deeper.
        memo, words, stack = self._colors, start[1], [start[0]]
        while stack:
            name = stack[-1]
            key = (name, words)
            state = memo.get(key, _MISSING)
            if state is not _MISSING and state is not _PENDING:
                stack.pop()
                continue
            nodes = self.expanded(name)
            if nodes is None:
                memo[key] = None
                stack.pop()
                continue
            inside = list(dict.fromkeys(
                target for target in map(_var_target, _scan(nodes)) if target))
            if state is _MISSING:
                if not self.spend(self.size(name)):
                    memo[key] = None
                    stack.pop()
                    continue
                memo[key] = _PENDING
                todo = [target for target in inside if (target, words) not in memo]
                if todo:
                    stack.extend(todo)
                    continue
            stack.pop()
            if any(memo.get((target, words)) is _PENDING
                   or memo.get((target, words)) is _CYCLE for target in inside):
                memo[key] = _CYCLE
            else:
                found, unread = color_nodes(nodes, prop, self)
                memo[key] = (found[:MAX_VAR_COLORS], unread)


def color_nodes(nodes, prop, resolver=None):
    """``(hex, alpha)`` of each colour in ``nodes``, in order; and the count
    of colour values that could not be read (``var()`` that does not
    resolve, ``lab()``, ``color()``...)."""
    found, unread = [], 0
    words_are_colors = prop in COLOR_PROPERTIES or (
        prop.startswith("--") and len(significant(nodes)) == 1)
    skip = set()
    for node in _scan(nodes):
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
                    text = serialize_within(node, MAX_TEXT)
                    if "var(" in text:
                        hex_color = parse_color_text(resolve_text(text, resolver))
                        parsed = (hex_color, 1.0) if hex_color else None
                if parsed:
                    found.append(parsed)
                else:
                    unread += 1
            elif name in colors.UNREAD_COLOR_FUNCTIONS:
                unread += 1
            elif name == "var":
                target = _var_target(node)
                read = (resolver.colors_of(target, prop)
                        if resolver and target else None)
                if read is not None:
                    found += read[0]
                    unread += read[1]
                    skip.update(id(n) for n in walk(node.arguments))
                elif not any(a.type == "literal" and a.value == ","
                             for a in node.arguments):
                    unread += 1
    return found, unread


def serialize_within(node, limit):
    """The text of ``node`` if it is at most ``limit`` characters, else ""
    (decided from its size first: a huge function is not serialised)."""
    if _size(node, limit + 1) > limit:
        return ""
    text = node.serialize()
    return text if len(text) <= limit else ""


def substitute_vars(nodes, resolver):
    """``nodes`` with each top-level ``var(--name)`` replaced by the value it
    resolves to (aliases followed all the way); an unresolved ``var()`` is
    kept, so callers can tell it was not read. Each replacement is charged
    to the page budget of the resolver."""
    result = []
    for node in nodes or ():
        target = _var_target(node) if resolver else None
        if target:
            value = resolver.expanded(target)
            if value is not None and resolver.spend(resolver.size(target)):
                result += value
                continue
        result.append(node)
    return result


_VAR_TEXT = re.compile(r"var\(\s*(--[\w-]{1,100})\s*(?:,[^()]{0,200})?\)")


def resolve_text(text, resolver):
    """``text`` with each ``var(--name)`` replaced by the text of its value
    (four rounds at most, so a cycle stops). Text longer than
    :data:`MAX_TEXT`, before or after a round, is returned as it is: it is
    not a colour. Each distinct text is resolved once per page and charged
    to the page budget."""
    if "var(" not in text or len(text) > MAX_TEXT:
        return text
    cached = resolver._resolved.get(text)
    if cached is not None:
        return cached

    def value(match):
        return resolver.text(match.group(1)) or match.group(0)

    result = text
    for _ in range(MAX_VAR_DEPTH):
        if "var(" not in result or len(result) > MAX_TEXT:
            break
        if not resolver.spend(len(result)):
            return text
        changed = _VAR_TEXT.sub(value, result)
        if changed == result:
            break
        result = changed
    resolver._resolved[text] = result
    return result


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

