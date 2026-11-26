"""Languages of files, and a linear split of source into code, comments and
strings. No parser and no execution: a file is read once, left to right."""

import re
from dataclasses import dataclass

_BY_SUFFIX = {
    "py": "python", "pyw": "python", "ipynb": "python",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "javascript", "ts": "typescript", "tsx": "typescript", "go": "go",
    "rs": "rust", "java": "java", "kt": "kotlin", "cs": "csharp",
    "cpp": "cpp", "cc": "cpp", "hpp": "cpp", "c": "c", "h": "c",
    "rb": "ruby", "php": "php", "r": "r", "jl": "julia", "m": "matlab",
    "scala": "scala", "swift": "swift", "lua": "lua", "pl": "perl",
    "dart": "dart", "sql": "sql", "sh": "shell", "bash": "shell",
    "ps1": "powershell", "bat": "batch", "scad": "openscad",
    "yaml": "yaml", "yml": "yaml", "json": "json", "toml": "toml",
    "ini": "ini", "cfg": "ini", "xml": "xml", "env": "env",
    "dockerfile": "dockerfile", "mk": "make", "csv": "csv", "tsv": "csv",
    "md": "markdown", "html": "html", "htm": "html", "css": "css",
    "svg": "svg", "tex": "latex", "dxf": "dxf", "stl": "stl", "step": "step",
    "stp": "step", "gcode": "gcode", "mmd": "mermaid", "dot": "dot",
}
_BY_NAME = {"dockerfile": "dockerfile", "makefile": "make",
            "jenkinsfile": "groovy", "gemfile": "ruby", "rakefile": "ruby",
            "go.mod": "gomod", ".env": "env"}
# General-purpose languages a program is written in.
PROGRAMMING = frozenset({
    "python", "javascript", "typescript", "go", "rust", "java", "kotlin",
    "csharp", "cpp", "c", "ruby", "php", "r", "julia", "matlab", "scala",
    "swift", "lua", "perl", "dart"})
SCRIPTING = frozenset({"sql", "shell", "powershell", "batch"})
CONFIG = frozenset({"yaml", "toml", "ini", "dockerfile", "make", "groovy",
                    "gomod", "env", "json", "xml"})

# Patterns that identify an untagged block. Only clear marks: a block that is
# not recognised stays unrecognised.
_SNIFF = (
    ("step", re.compile(r"\AISO-10303-21;")),
    ("dxf", re.compile(r"\A\s{0,20}0[ \t\r]{0,5}\n[ \t]{0,5}SECTION\b")),
    ("stl", re.compile(r"\A\s{0,20}solid\b[^\n]{0,200}\n[ \t]{0,20}facet normal\b")),
    ("svg", re.compile(r"\A\s{0,200}(?:<\?xml[^>]{0,200}>\s{0,20})?<svg\b")),
    ("go", re.compile(r"\A(?:[ \t]{0,40}\n|//[^\n]{0,200}\n){0,40}package \w{1,40}"
                      r"[ \t\r]{0,5}\n")),
    ("python", re.compile(
        r"^(?:def \w{1,80}\(|from [\w.]{1,80} import |import [a-z_][\w.]{0,80}"
        r"(?: as \w{1,40})?[ \t\r]{0,5}$|if __name__ ==)", re.M)),
    ("openscad", re.compile(
        r"^[ \t]{0,40}(?:difference|union|linear_extrude|rotate_extrude|hull|"
        r"cylinder|cube|translate)[ \t]{0,5}\(", re.M)),
)


def sniff(text):
    """The language of an untagged block, or None."""
    head = text[:20000]
    for language, pattern in _SNIFF:
        if pattern.search(head):
            return language
    return None


def language_of(path, text):
    name = path.rsplit("/", 1)[-1].lower()
    if name in _BY_NAME:
        return _BY_NAME[name]
    _, dot, suffix = name.rpartition(".")
    if not dot or suffix == "txt":
        if name.startswith(("requirements", "constraints")):
            return None
        return sniff(text)
    return _BY_SUFFIX.get(suffix)


@dataclass(frozen=True)
class Parts:
    code: str           # comments and docstrings removed
    bare: str           # as code, with every string emptied
    comments: tuple     # the comment texts
    strings: tuple      # the string literals' contents
    comment_lines: int
    docstrings: int


_HASH = frozenset({"python", "ruby", "shell", "powershell", "r", "julia", "yaml",
                   "toml", "make", "dockerfile", "perl", "env", "ini"})
_PYTHON_TOKEN = re.compile(
    r'(?P<triple>"""|\'\'\')|(?P<line>#[^\n]*)|'
    r'(?P<string>"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n])*\'?)')
_HASH_TOKEN = re.compile(
    r'(?P<line>(?<![\w$\\{#])#[^\n]*)|'
    r'(?P<string>"(?:\\.|[^"\\\n])*"?|\'[^\'\n]*\'?)')
_C_TOKEN = re.compile(
    r'(?P<block>/\*)|(?P<line>//[^\n]*)|'
    r'(?P<string>"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n])*\'?|`[^`]*`?)')
_SQL_TOKEN = re.compile(
    r'(?P<block>/\*)|(?P<line>--[^\n]*)|(?P<string>\'[^\'\n]*\'?|"[^"\n]*"?)')
_MATLAB_TOKEN = re.compile(r'(?P<line>%[^\n]*)|(?P<string>"[^"\n]*"?)')


def _tokens(language):
    if language == "python":
        return _PYTHON_TOKEN
    if language in _HASH:
        return _HASH_TOKEN
    if language == "sql":
        return _SQL_TOKEN
    if language == "matlab":
        return _MATLAB_TOKEN
    return _C_TOKEN


def split(language, text):
    """Split ``text`` of ``language`` into :class:`Parts`."""
    token = _tokens(language)
    code, bare, comments, strings = [], [], [], []
    comment_lines = docstrings = 0
    position = 0
    last = ""           # the last character of code before this point
    while True:
        found = token.search(text, position)
        end = found.start() if found else len(text)
        chunk = text[position:end]
        code.append(chunk)
        bare.append(chunk)
        stripped = chunk.rstrip()
        if stripped:
            last = stripped[-1]
        if not found:
            break
        kind = found.lastgroup
        position = found.end()
        value = found[0]
        if kind == "line":
            if not (value.startswith("#!") and found.start() == 0):
                comments.append(value)
                comment_lines += 1
        elif kind == "block":
            close = text.find("*/", position)
            close = len(text) if close < 0 else close + 2
            value = text[found.start():close]
            comments.append(value)
            comment_lines += value.count("\n") + 1
            position = close
            code.append(" ")
            bare.append(" ")
        elif kind == "triple":
            close = text.find(value, position)
            inner = text[position:len(text) if close < 0 else close]
            position = len(text) if close < 0 else close + 3
            # alone on its line, first in the file or after a block opener
            before = found.start() - 1
            while before >= 0 and text[before] in " \t":
                before -= 1
            alone = before < 0 or text[before] == "\n"
            if alone and last in ("", ":"):
                docstrings += 1
            else:
                strings.append(inner)
                code.append(value + inner + value)
                bare.append('""')
            last = '"'
        else:
            quote = value[0]
            inner = value[1:-1] if len(value) > 1 and value.endswith(quote) \
                else value[1:]
            strings.append(inner)
            code.append(value)
            bare.append(quote + quote)
            last = quote
    return Parts("".join(code), "".join(bare), tuple(comments), tuple(strings),
                 comment_lines, docstrings)
