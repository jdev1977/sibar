"""CSS read with tinycss2 into a flat list of declarations with their context.

tinycss2 implements the CSS Syntax spec's tokenizer and parser, so comments,
strings, escapes, ``url()`` and nested blocks are read as a browser reads
them; a hand-written regex reader gets these wrong. It runs in linear time on
the hostile inputs in the tests. Nesting (CSS nesting, ``@media`` inside
``@media``) is followed to :data:`MAX_NESTING` levels; a value nested deeper
than :data:`MAX_VALUE_DEPTH` is skipped.

SCSS, Sass and Less files are read as CSS (most of their syntax tokenizes
cleanly), and their ``$name: value`` / ``@name: value`` variables are read as
custom properties so their colours and fonts count.
"""

import re
from dataclasses import dataclass, field

import tinycss2

MAX_NESTING = 16
MAX_VALUE_DEPTH = 32
MAX_DECLARATIONS = 50_000
GROUPING_AT_RULES = frozenset({"media", "supports", "container", "layer", "document",
                               "scope", "starting-style"})
TAILWIND_AT_RULES = frozenset({"tailwind", "apply", "theme", "plugin", "config",
                               "variant", "custom-variant", "utility", "source"})
_SPACES = re.compile(r"\s+")
_PREPROCESSOR_VARIABLE = re.compile(
    r"^[ \t]*[$@]([A-Za-z_][\w-]{0,60})[ \t]*:[ \t]*([^;\n{}]{1,300})", re.MULTILINE)


@dataclass(frozen=True)
class Declaration:
    prop: str  # lower case
    value: tuple  # tinycss2 component values
    text: str  # the value as written, whitespace collapsed
    important: bool
    selector: str  # "" for a style attribute; "@font-face" in @font-face
    media: tuple  # enclosing at-rules, such as "media (max-width: 600px)"
    origin: str  # file path, with "#style" for a <style> element
    element: object = None  # the Element of a style attribute


@dataclass
class Sheet:
    origin: str
    declarations: list = field(default_factory=list)
    at_rules: list = field(default_factory=list)  # (keyword, prelude text, media)
    imports: list = field(default_factory=list)  # @import targets
    selectors: list = field(default_factory=list)  # (selector, media) per rule
    applied: list = field(default_factory=list)  # class names in @apply
    truncated: bool = False


def _depth(nodes):
    """Nesting depth of a component value list, without recursion."""
    deepest, stack = 0, [(nodes, 1)]
    while stack:
        items, depth = stack.pop()
        deepest = max(deepest, depth)
        if depth > MAX_VALUE_DEPTH:
            return depth
        for node in items or ():
            inner = getattr(node, "arguments", None)
            if inner is None:
                inner = getattr(node, "content", None)
            if isinstance(inner, list):
                stack.append((inner, depth + 1))
    return deepest


def serialize(nodes):
    """The text of ``nodes`` with whitespace collapsed ("" if too deep)."""
    if _depth(nodes) > MAX_VALUE_DEPTH:
        return ""
    return _SPACES.sub(" ", tinycss2.serialize(nodes)).strip()


def walk(nodes):
    """Every component value in ``nodes``, depth first, including those
    inside functions and blocks (up to :data:`MAX_VALUE_DEPTH`)."""
    stack = [iter(nodes or ())]
    while stack:
        node = next(stack[-1], None)
        if node is None:
            stack.pop()
            continue
        yield node
        if node.type == "function":
            inner = node.arguments
        elif node.type in ("() block", "[] block", "{} block"):
            inner = node.content
        else:
            inner = None
        if inner and len(stack) <= MAX_VALUE_DEPTH:
            stack.append(iter(inner))


def significant(nodes):
    """``nodes`` without whitespace and comments."""
    return [n for n in nodes or () if n.type not in ("whitespace", "comment")]


class _Reader:
    def __init__(self, sheet):
        self.sheet = sheet

    def add(self, declaration, selector, media, element=None):
        if len(self.sheet.declarations) >= MAX_DECLARATIONS:
            self.sheet.truncated = True
            return
        if _depth(declaration.value) > MAX_VALUE_DEPTH:
            return
        self.sheet.declarations.append(Declaration(
            prop=declaration.lower_name, value=tuple(declaration.value),
            text=serialize(declaration.value), important=declaration.important,
            selector=selector, media=media, origin=self.sheet.origin,
            element=element))

    def block(self, nodes, selector, media, level):
        """Declarations and nested rules inside a rule's block."""
        if level > MAX_NESTING:
            return
        for node in tinycss2.parse_blocks_contents(nodes, skip_comments=True,
                                                   skip_whitespace=True):
            if node.type == "declaration":
                self.add(node, selector, media)
            elif node.type == "qualified-rule":
                inner = serialize(node.prelude)
                nested = ", ".join(
                    part.strip().replace("&", selector) if "&" in part
                    else f"{selector} {part.strip()}"
                    for part in inner.split(",")) if selector else inner
                self.sheet.selectors.append((nested, media))
                self.block(node.content, nested, media, level + 1)
            elif node.type == "at-rule":
                self.at_rule(node, selector, media, level + 1)

    def at_rule(self, rule, selector, media, level):
        keyword = rule.lower_at_keyword
        prelude = serialize(rule.prelude)
        self.sheet.at_rules.append((keyword, prelude, media))
        if keyword == "import":
            target = next(iter(significant(rule.prelude)), None)
            if target is not None:
                if target.type in ("string", "url"):
                    self.sheet.imports.append(target.value)
                elif target.type == "function" and target.lower_name == "url":
                    strings = [a.value for a in target.arguments if a.type == "string"]
                    self.sheet.imports.extend(strings[:1])
            return
        if keyword == "apply":
            self.sheet.applied.extend(prelude.replace("!important", "").split())
            return
        if rule.content is None or level > MAX_NESTING:
            return
        if keyword in GROUPING_AT_RULES:
            inner_media = media + (f"{keyword} {prelude}".strip(),)
            if selector:
                self.block(rule.content, selector, inner_media, level)
            else:
                self.rules(rule.content, inner_media, level)
        elif keyword == "font-face":
            for node in tinycss2.parse_blocks_contents(
                    rule.content, skip_comments=True, skip_whitespace=True):
                if node.type == "declaration":
                    self.add(node, "@font-face", media)
        elif keyword == "keyframes" or keyword.endswith("-keyframes"):
            self.rules(rule.content, media + (f"keyframes {prelude}",), level)
        elif keyword in ("theme", "layer", "utility") or keyword in TAILWIND_AT_RULES:
            self.block(rule.content, selector or f"@{keyword}", media, level)

    def rules(self, nodes, media, level):
        if level > MAX_NESTING:
            return
        for node in tinycss2.parse_rule_list(nodes, skip_comments=True,
                                             skip_whitespace=True):
            if node.type == "qualified-rule":
                selector = serialize(node.prelude)
                self.sheet.selectors.append((selector, media))
                self.block(node.content, selector, media, level + 1)
            elif node.type == "at-rule":
                self.at_rule(node, "", media, level + 1)


def parse_css(text, origin, preprocessor=False):
    """Read a stylesheet (``preprocessor``: SCSS, Sass or Less) into a Sheet."""
    sheet = Sheet(origin=origin)
    reader = _Reader(sheet)
    if preprocessor:
        for match in _PREPROCESSOR_VARIABLE.finditer(text):
            declaration = tinycss2.parse_one_declaration(
                f"--{match.group(1)}: {match.group(2)}")
            if declaration.type == "declaration":
                reader.add(declaration, ":root", ())
    for node in tinycss2.parse_stylesheet(text, skip_comments=True,
                                          skip_whitespace=True):
        if node.type == "qualified-rule":
            selector = serialize(node.prelude)
            sheet.selectors.append((selector, ()))
            reader.block(node.content, selector, (), 1)
        elif node.type == "at-rule":
            reader.at_rule(node, "", (), 1)
    return sheet


def parse_style_attribute(text, origin, element):
    """The declarations of a ``style="..."`` attribute."""
    sheet = Sheet(origin=origin)
    reader = _Reader(sheet)
    for node in tinycss2.parse_blocks_contents(text, skip_comments=True,
                                               skip_whitespace=True):
        if node.type == "declaration":
            reader.add(node, "", (), element)
    return sheet.declarations


def selector_parts(selector):
    """The comma-separated selectors of a selector list, lower case."""
    return [part.strip().lower() for part in selector.split(",") if part.strip()]


_DARK_MARKER = re.compile(
    r"\.(?:dark|dark-mode|dark-theme|theme-dark)(?![\w-])"
    r"|\[data-(?:theme|mode|bs-theme|color-scheme)\s*=\s*['\"]?dark['\"]?\s*\]")


def is_dark_page_selector(selector):
    """True if every selector in the list is the page (``html``, ``body``,
    ``:root``) marked dark: ``.dark``, ``html.dark``, ``.dark body``,
    ``[data-theme="dark"]``."""
    parts = selector_parts(selector)
    if not parts:
        return False
    for part in parts:
        if not _DARK_MARKER.search(part):
            return False
        rest = _DARK_MARKER.sub(" ", part).split()
        if any(word not in ("html", "body", ":root") for word in rest):
            return False
    return True


def is_page_selector(selector):
    """True if every selector in the list is ``html``, ``body`` or ``:root``."""
    parts = selector_parts(selector)
    return bool(parts) and all(part in ("html", "body", ":root") for part in parts)
