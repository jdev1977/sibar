"""A small HTML (and JSX) tokenizer and tree builder that runs in linear time.

Python's ``html.parser`` was not used: on hostile input such as ``"<a " *
10000`` (a start tag that never closes) it takes minutes, and repeated
``"</"`` takes quadratic time. This tokenizer reads each character a bounded
number of times: every search for a closing ``>``, quote or ``-->`` that
fails ends the parse, since a later search from further on would fail too.
That matches browsers, which drop an unclosed tag or comment at the end of
the file.

It builds a light tree, not the full HTML5 one: it closes ``<p>``, ``<li>``
and table cells implicitly in the common cases, ignores stray end tags and
caps depth and element count. Extractors here need tags, attributes, parents
and text, which this gives.

In JSX mode (``.jsx``/``.tsx`` files and Babel scripts) tag case is kept (a
capitalised tag is a component), ``className`` and ``htmlFor`` are read as
``class`` and ``for``, attribute values in braces are skipped as a whole, and
text outside any element, or in ``{...}``, is treated as code, not copy.
"""

import html
import re
from dataclasses import dataclass, field

VOID = frozenset("area base br col embed hr img input link meta param source track "
                 "wbr".split())
RAW_TEXT = frozenset("script style textarea title xmp iframe noembed noframes "
                     "plaintext".split())
HIDDEN = frozenset("script style template noscript head".split())
BLOCKS_CLOSING_P = frozenset(
    "address article aside blockquote details div dl fieldset figcaption figure "
    "footer form h1 h2 h3 h4 h5 h6 header hr main menu nav ol p pre section table "
    "ul".split())
IMPLIED_END = {
    "li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "tr": {"tr", "td", "th"},
    "td": {"td", "th"}, "th": {"td", "th"}, "option": {"option"},
}
MAX_ELEMENTS = 100_000
MAX_DEPTH = 512
MAX_NAME = 200

_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_TAG_NAME = re.compile(r"[A-Za-z][^\s/>]{0,%d}" % MAX_NAME)
_ATTR_NAME = re.compile(r"[^\s/>][^\s/>=]{0,%d}" % MAX_NAME)
_SPACE = re.compile(r"[\s/]*")
_WHITESPACE = re.compile(r"\s*")
_UNQUOTED = re.compile(r"[^\s>]*")
_BRACES = re.compile(r"[{}]")
_QUOTED = re.compile(r"""["'`]([^"'`]{0,2000})["'`]""")
_TEMPLATE_PART = re.compile(r"\$\{[^{}]{0,500}\}")
_SPACES = re.compile(r"\s+")
_INNER_BRACES = re.compile(r"\{[^{}]{0,2000}\}")
MAX_BRACE_PASSES = 8
JSX_ATTRS = {"classname": "class", "htmlfor": "for"}


@dataclass
class Element:
    index: int
    tag: str  # lower case
    name: str  # as written
    attrs: dict  # lower-case names; the first of a repeated name wins
    parent: int  # -1 at the top level
    depth: int
    hidden: bool  # inside script, style, template, noscript or head
    component: bool = False  # JSX: <Button>, not an HTML element
    children: list = field(default_factory=list)
    text_start: int = 0  # len(texts) when the element started
    end: int = 0  # index after the last element inside this one

    @property
    def classes(self):
        return self.attrs.get("class", "").split()


@dataclass
class Document:
    """One parsed file or fragment.

    ``texts`` holds ``(text, element index)`` for the text between tags;
    ``raws`` holds ``(element index, content)`` for script, style, title and
    other raw-text elements. ``truncated`` is true when a limit cut the parse
    short; ``unterminated`` when the file ended inside a tag or comment.
    """

    path: str
    jsx: bool = False
    fragment: bool = False
    elements: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    raws: list = field(default_factory=list)
    roots: list = field(default_factory=list)
    truncated: bool = False
    unterminated: bool = False

    def find(self, *tags):
        wanted = set(tags)
        return [e for e in self.elements if e.tag in wanted and not e.component]

    def ancestors(self, element):
        index = element.parent
        while index >= 0:
            yield self.elements[index]
            index = self.elements[index].parent

    def descendants(self, element):
        return self.elements[element.index + 1:element.end]

    def text_of(self, element, limit=2000):
        """The visible text inside ``element``, whitespace collapsed."""
        stop = (self.elements[element.end].text_start
                if element.end < len(self.elements) else len(self.texts))
        parts, size = [], 0
        for text, owner in self.texts[element.text_start:stop]:
            if element.index <= owner < element.end:
                parts.append(text)
                size += len(text)
                if size > limit:
                    break
        return _SPACES.sub(" ", " ".join(parts)).strip()[:limit]

    def finish(self):
        """Work out where each element's subtree ends (elements are in
        document order, so a subtree is a run of deeper elements)."""
        open_ = []
        for element in self.elements:
            while open_ and self.elements[open_[-1]].depth >= element.depth:
                self.elements[open_.pop()].end = element.index
            open_.append(element.index)
        for index in open_:
            self.elements[index].end = len(self.elements)

    def copy_texts(self):
        """Visible text pieces: text outside hidden elements, plus the title."""
        pieces = [text for text, owner in self.texts
                  if owner < 0 and not self.jsx
                  or owner >= 0 and not self.elements[owner].hidden]
        pieces += [content if self.jsx else html.unescape(content)
                   for owner, content in self.raws
                   if self.elements[owner].tag == "title"]
        return [p for p in (_SPACES.sub(" ", piece).strip() for piece in pieces) if p]


def _jsx_text(text):
    """Text in JSX with ``{...}`` expressions removed."""
    for _ in range(MAX_BRACE_PASSES):
        if "{" not in text:
            break
        text = _INNER_BRACES.sub(" ", text)
    if "{" in text:
        text = text[:text.index("{")]
    if "}" in text:
        text = text[text.rindex("}") + 1:]
    return text


def _class_from_expression(value):
    """Class names written as ``{"a b"}``, ``{`a ${x}`}`` or ``{clsx("a", ...)}``."""
    value = _TEMPLATE_PART.sub(" ", value)
    return " ".join(match.group(1) for match in _QUOTED.finditer(value))


class _Builder:
    def __init__(self, document):
        self.doc = document
        self.stack = []
        self.open = {}

    def _pop_to(self, tag):
        while self.stack:
            index = self.stack.pop()
            name = self.doc.elements[index].tag
            self.open[name] -= 1
            if name == tag:
                return

    def start(self, name, attrs, self_closing):
        doc = self.doc
        if len(doc.elements) >= MAX_ELEMENTS:
            doc.truncated = True
            return None
        tag = name.translate(_ASCII_LOWER)
        if not doc.jsx and self.stack:
            top = doc.elements[self.stack[-1]].tag
            if top in IMPLIED_END.get(tag, ()) or (top == "p"
                                                   and tag in BLOCKS_CLOSING_P):
                self._pop_to(top)
        parent = self.stack[-1] if self.stack else -1
        parent_element = doc.elements[parent] if parent >= 0 else None
        element = Element(
            index=len(doc.elements), tag=tag, name=name, attrs=attrs, parent=parent,
            depth=len(self.stack),
            hidden=(tag in HIDDEN or bool(parent_element and parent_element.hidden)),
            component=doc.jsx and (name[:1].isupper() or "." in name),
            text_start=len(doc.texts))
        doc.elements.append(element)
        if parent_element is not None:
            parent_element.children.append(element.index)
        else:
            doc.roots.append(element.index)
        if not self_closing and tag not in VOID and len(self.stack) < MAX_DEPTH:
            self.stack.append(element.index)
            self.open[tag] = self.open.get(tag, 0) + 1
        return element

    def end(self, name):
        tag = name.translate(_ASCII_LOWER)
        if self.open.get(tag):
            self._pop_to(tag)

    def text(self, text):
        if not text:
            return
        owner = self.stack[-1] if self.stack else -1
        if self.doc.jsx:
            if owner < 0:
                return  # code around the markup
            text = _jsx_text(text)
            if not text.strip():
                return
        else:
            text = html.unescape(text)
        self.doc.texts.append((text, owner))


def _balanced_end(text, start):
    """Index of the brace closing the one at ``start``, or -1."""
    depth = 0
    for match in _BRACES.finditer(text, start):
        depth += 1 if match.group() == "{" else -1
        if depth == 0:
            return match.start()
    return -1


def _start_tag(text, position, jsx):
    """Parse a start tag whose name begins at ``position``.

    Returns ``(name, attrs, self_closing, end)`` or None if the file ends
    inside the tag.
    """
    length = len(text)
    match = _TAG_NAME.match(text, position)
    name, i = match.group(), match.end()
    attrs = {}
    self_closing = False
    while True:
        spaces = _SPACE.match(text, i)
        if i < spaces.end():
            self_closing = text[spaces.end() - 1] == "/"
        i = spaces.end()
        if i >= length:
            return None
        if text[i] == ">":
            return name, attrs, self_closing, i + 1
        self_closing = False
        match = _ATTR_NAME.match(text, i)
        attr, i = match.group(), match.end()
        i = _WHITESPACE.match(text, i).end()
        value = ""
        if i < length and text[i] == "=":
            i = _WHITESPACE.match(text, i + 1).end()
            if i >= length:
                return None
            quote = text[i]
            if quote in "\"'":
                close = text.find(quote, i + 1)
                if close < 0:
                    return None
                value, i = text[i + 1:close], close + 1
                if not jsx:
                    value = html.unescape(value)
            elif jsx and quote == "{":
                close = _balanced_end(text, i)
                if close < 0:
                    return None
                value, i = text[i:close + 1], close + 1
            else:
                match = _UNQUOTED.match(text, i)
                value, i = html.unescape(match.group()), match.end()
        key = attr.translate(_ASCII_LOWER)
        if jsx:
            key = JSX_ATTRS.get(key, key)
            if key == "class" and value.startswith("{"):
                value = _class_from_expression(value)
        attrs.setdefault(key, value)


def parse_html(text, path="", jsx=False, fragment=False):
    """Parse ``text`` into a :class:`Document`."""
    doc = Document(path=path, jsx=jsx, fragment=fragment)
    builder = _Builder(doc)
    lower = text.translate(_ASCII_LOWER)  # same length as text, unlike .lower()
    length, i = len(text), 0
    while i < length and not doc.truncated:
        j = text.find("<", i)
        if j < 0:
            builder.text(text[i:])
            break
        builder.text(text[i:j])
        after = text[j + 1:j + 2]
        if text.startswith("<!--", j):
            close = text.find("-->", j + 4)
            if close < 0:
                doc.unterminated = True
                break
            i = close + 3
        elif after in ("!", "?") or (after == "/" and not
                                     _TAG_NAME.match(text, j + 2)):
            close = text.find(">", j + 1)
            if close < 0:
                doc.unterminated = True
                break
            i = close + 1
        elif after == "/":
            name = _TAG_NAME.match(text, j + 2).group()
            close = text.find(">", j + 2)
            if close < 0:
                doc.unterminated = True
                break
            builder.end(name)
            i = close + 1
        elif after.isascii() and after.isalpha():
            parsed = _start_tag(text, j + 1, jsx)
            if parsed is None:
                doc.unterminated = True
                break
            name, attrs, self_closing, i = parsed
            element = builder.start(name, attrs, self_closing)
            tag = name.translate(_ASCII_LOWER)
            if element is not None and tag in RAW_TEXT and not self_closing:
                close = lower.find("</" + tag, i)
                end = length if close < 0 else close
                doc.raws.append((element.index, text[i:end]))
                if close < 0:
                    doc.unterminated = True
                    break
                builder.end(tag)
                gt = text.find(">", close)
                if gt < 0:
                    doc.unterminated = True
                    break
                i = gt + 1
        elif jsx and after == ">":
            i = j + 2  # <> fragment
        else:
            builder.text("<")
            i = j + 1
    doc.finish()
    return doc
