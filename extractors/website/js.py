"""JavaScript (and TypeScript, JSX) read as text, never run.

A linear scanner separates comments and string literals from code, which is
enough to find:

- module references: ``import ... from "x"``, ``import "x"``, ``import("x")``,
  ``require("x")`` and ``export ... from "x"``;
- strings that hold HTML (``innerHTML = `<div class="...">...`)``), parsed
  later as HTML fragments;
- class names given to ``className``/``class`` or ``classList.add(...)``;
- strings that read as prose, for the copy-text extractors.

Regular expression literals are not recognised: a ``/`` that is not a comment
is read as division. A quote inside a regex literal can make the scanner read
a short stretch of code as a string, up to the end of that line.
"""

import re
from dataclasses import dataclass, field

MAX_STRINGS = 20_000
_SPECIAL = re.compile(r"""[/"'`]""")
_DOUBLE = re.compile(r'(?:[^"\\\n]|\\.)*"', re.DOTALL)
_SINGLE = re.compile(r"(?:[^'\\\n]|\\.)*'", re.DOTALL)
_TEMPLATE = re.compile(r"(?:[^`\\]|\\.)*`", re.DOTALL)
_TEMPLATE_PART = re.compile(r"\$\{[^{}]{0,500}\}")
_ESCAPE = re.compile(r"\\(.)", re.DOTALL)
_PLACEHOLDER = r'"§(\d+)"'
_IMPORTS = re.compile(
    r"\b(?:from|import|require)\s*\(?\s*" + _PLACEHOLDER)
_CLASS_ASSIGN = re.compile(r"\bclass(?:Name)?\s*[=:]\s*" + _PLACEHOLDER)
_CLASS_LIST = re.compile(
    r"\bclassList\s*\.\s*(?:add|remove|toggle|replace|contains)\s*\(\s*"
    + _PLACEHOLDER + r"(?:\s*,\s*" + _PLACEHOLDER + r")?")
_JSX_HINT = re.compile(r"(?:return|=>|[(,?:])\s*<[A-Za-z>]")
_HTML_HINT = re.compile(r"<[A-Za-z][A-Za-z0-9-]{0,30}[\s>/]")
_WORD = re.compile(r"[^\W\d_]{2,}")
_CODE_CHARS = re.compile(r"[{};=<>\\]|=>|://|\$\{|^[#./@]|\(\)")


@dataclass
class Script:
    """One script: a file or an inline ``<script>``."""

    origin: str
    code: str = ""  # comments removed, strings replaced by "§N"
    strings: list = field(default_factory=list)
    templates: set = field(default_factory=set)  # indexes of template literals
    truncated: bool = False

    def imports(self):
        """Module specifiers, in order of appearance."""
        return [self.strings[int(m.group(1))] for m in _IMPORTS.finditer(self.code)
                if int(m.group(1)) < len(self.strings)]

    def class_strings(self):
        """Class lists given in code (not in markup)."""
        found = []
        for match in _CLASS_ASSIGN.finditer(self.code):
            found.append(self.strings[int(match.group(1))])
        for match in _CLASS_LIST.finditer(self.code):
            for group in match.groups():
                if group is not None:
                    found.append(self.strings[int(group)])
        return found

    def html_strings(self):
        """Strings that hold HTML markup."""
        return [s for s in self.strings if "<" in s and _HTML_HINT.search(s)]

    def looks_like_jsx(self):
        return bool(_JSX_HINT.search(self.code))

    def prose_strings(self):
        """Strings that read as words for a person, not code or class lists."""
        return [s for s in self.strings if looks_like_prose(s)]


def looks_like_prose(text):
    """True for text such as ``"Fresh bread, every morning"``; false for
    identifiers, class lists, selectors, URLs, markup and code."""
    text = text.strip()
    if not 1 <= len(text) <= 2000 or "<" in text and _HTML_HINT.search(text):
        return False
    if _CODE_CHARS.search(text):
        return False
    words = text.split()
    if len(words) == 1:  # a Capitalised word, or symbols only (an emoji)
        word = words[0]
        return (word.isalpha() and word[:1].isupper() and word[1:].islower()
                or not any(c.isascii() and c.isalnum() for c in word))
    if not _WORD.search(text):
        return False
    odd = sum(1 for w in words if any(c in w for c in "-_:[]/") and not w.isalpha())
    return odd * 2 < len(words)


def _unescape(body):
    return _ESCAPE.sub(lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)),
                       body)


def scan(text, origin=""):
    """Split ``text`` into code and strings (linear time)."""
    script = Script(origin=origin)
    code, i, length = [], 0, len(text)
    while i < length:
        match = _SPECIAL.search(text, i)
        if match is None:
            code.append(text[i:])
            break
        j = match.start()
        code.append(text[i:j])
        char = text[j]
        if char == "/":
            nxt = text[j + 1:j + 2]
            if nxt == "/":
                end = text.find("\n", j)
                i = length if end < 0 else end
            elif nxt == "*":
                end = text.find("*/", j + 2)
                i = length if end < 0 else end + 2
                code.append(" ")
            else:
                code.append("/")
                i = j + 1
            continue
        pattern = {'"': _DOUBLE, "'": _SINGLE, "`": _TEMPLATE}[char]
        found = pattern.match(text, j + 1)
        if found is None:  # unterminated: a string ends at the line's end
            end = text.find("\n", j + 1) if char != "`" else -1
            end = length if end < 0 else end
            body, i = text[j + 1:end], end
        else:
            body, i = text[j + 1:found.end() - 1], found.end()
        if len(script.strings) >= MAX_STRINGS:
            script.truncated = True
            code.append('""')
            continue
        if char == "`":
            script.templates.add(len(script.strings))
            body = _TEMPLATE_PART.sub(" ", body)
        code.append(f'"§{len(script.strings)}"')
        script.strings.append(_unescape(body))
    script.code = "".join(code)
    return script
