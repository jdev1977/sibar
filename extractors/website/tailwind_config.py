"""A project's own Tailwind theme, read without running anything.

Read from:

- ``tailwind.config = {...}`` in an inline script, and ``tailwind.config.*``
  files (v3): the ``colors`` and ``fontFamily`` objects, wherever they sit
  (``theme`` or ``theme.extend``);
- ``@theme { --color-*: ...; --font-*: ... }`` in CSS (v4).

Nested colour keys are joined with ``-`` (``primary: {500: ...}`` gives
``primary-500``; ``DEFAULT`` gives the bare name). A value that is not a
plain colour (``hsl(var(--primary))``) is kept as a known name with no
colour. Config objects are parsed by a small bounded reader of object
literals over the script's code with strings already set aside: keys,
nested objects, arrays and strings. Anything else (function calls, spreads,
references) is skipped, so the reader never fails on odd configs; it reads
less.
"""

import re

from extractors.website.css import significant
from extractors.website.values import Resolver, color_nodes, parse_color_text, visible

MAX_TOKENS = 5000
MAX_OBJECTS = 20  # colors/fontFamily objects read per script
MAX_DEPTH = 5
CONFIG_FILE = re.compile(r"(?:^|/)tailwind\.config\.(?:js|cjs|mjs|ts)$")
_TOKEN = re.compile(r'\s*(?:([{}:,\[\]()])|"§(\d+)"|([A-Za-z_$][\w$.-]{0,60}|\d{1,4}))')
_KEYS = re.compile(r"\b(colors|fontFamily)\s*:\s*\{")


def _tokens(code, start, strings):
    """``(kind, value, end)`` tokens of an object literal from ``start``."""
    position, count = start, 0
    while count < MAX_TOKENS:
        match = _TOKEN.match(code, position)
        if not match or match.end() == position:
            return
        position = match.end()
        count += 1
        if match.group(1):
            yield "punct", match.group(1), position
        elif match.group(2) is not None:
            index = int(match.group(2))
            yield "string", strings[index] if index < len(strings) else "", position
        else:
            yield "word", match.group(3), position


def _parse_object(stream, depth):
    """Read ``key: value`` pairs until the closing brace. Values are text,
    a list of text, a nested dict, or None (anything else)."""
    result = {}
    for kind, value, _ in stream:
        if kind == "punct" and value == "}":
            return result
        if kind == "punct" and value == ",":
            continue
        if kind == "punct" and value in "([":
            _skip(stream, value, None)  # a call or array where a key was expected
            continue
        if kind not in ("string", "word"):
            return result
        key = value
        colon = next(stream, None)
        if colon is None or colon[1] != ":":
            return result
        result[key] = _parse_value(stream, depth)
    return result


def _parse_value(stream, depth):
    token = next(stream, None)
    if token is None:
        return None
    kind, value, _ = token
    if kind == "punct" and value == "{":
        return _parse_object(stream, depth + 1) if depth < MAX_DEPTH else _skip(
            stream, "{", "}")
    if kind == "punct" and value == "[":
        items = []
        for kind, value, _ in stream:
            if kind == "punct" and value == "]":
                break
            if kind == "string":
                items.append(value)
        return items
    if kind == "string":
        return value
    return _skip_rest(stream, kind, value)


def _skip(stream, opening, closing):
    depth = 1
    for kind, value, _ in stream:
        if kind == "punct" and value in "{[(":
            depth += 1
        elif kind == "punct" and value in "}])":
            depth -= 1
            if depth == 0:
                return None
    return None


def _skip_rest(stream, kind, value):
    """Skip an expression such as ``colors.indigo`` or ``fn(1)``."""
    if kind == "punct" and value in "([":
        _skip(stream, value, None)
    return None


def _flatten(tree, prefix=""):
    for key, value in tree.items():
        name = prefix if key == "DEFAULT" else (f"{prefix}-{key}" if prefix else key)
        if isinstance(value, dict):
            yield from _flatten(value, name)
        elif name:
            yield name, value


def _config_scripts(site):
    for script in site.scripts:
        origin = script.origin.split("#")[0]
        if CONFIG_FILE.search(origin.lower()) or "tailwind" in script.code:
            yield script


class Theme:
    """A site's Tailwind theme: ``colors`` maps a name (``primary-500``) to
    ``#rrggbb`` or None (not a plain colour); ``fonts`` maps a key (``sans``,
    ``display``) to its first family, lower case."""

    def __init__(self, site):
        self.colors, self.fonts = {}, {}
        for script in _config_scripts(site):
            for count, match in enumerate(_KEYS.finditer(script.code)):
                if count >= MAX_OBJECTS:
                    break
                stream = _tokens(script.code, match.end(), script.strings)
                tree = _parse_object(stream, 1)
                if match.group(1) == "colors":
                    for name, value in _flatten(tree):
                        hex_color = parse_color_text(value) if isinstance(
                            value, str) else None
                        self.colors.setdefault(name.lower(), hex_color)
                else:
                    for key, value in tree.items():
                        first = value[0] if isinstance(value, list) and value else value
                        if isinstance(first, str) and first.strip():
                            self.fonts.setdefault(key, " ".join(
                                first.replace('"', " ").replace("'", " ").split()).lower())
        resolver = Resolver(site.declarations())
        for declaration in site.declarations():
            if declaration.selector != "@theme":
                continue
            prop = declaration.prop
            if prop.startswith("--color-"):
                found, _ = color_nodes(declaration.value, prop, resolver)
                shown = visible(found)
                self.colors[prop[8:]] = shown[0] if shown else None
            elif prop.startswith("--font-") and prop[7:] not in self.fonts:
                names = [n for n in significant(declaration.value)
                         if n.type in ("string", "ident")]
                if names:
                    self.fonts[prop[7:]] = " ".join(str(names[0].value).split()).lower()


def get_theme(site):
    if "_theme" not in site.__dict__:
        site.__dict__["_theme"] = Theme(site)
    return site.__dict__["_theme"]
