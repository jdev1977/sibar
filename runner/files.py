"""Files extracted from a model's text output (T0.5).

Two kinds of file are taken from the raw response text:

- **fenced code blocks** (three or more backticks or tildes, CommonMark
  style). A block is named from a file name in its info string
  (```` ```html index.html ````, ```` ```html:index.html ````,
  ```` ```html title="index.html" ````) or on the line just before it
  (``**index.html**``, ``### `index.html` ``, ``File: index.html``), else
  ``block-NN.<ext>`` from its language. An unclosed block is not extracted.
- **complete HTML documents** outside fenced blocks (from ``<!DOCTYPE html>``
  or ``<html>`` to ``</html>``), named ``document-NN.html``.

Names come from model output, so they are treated as hostile:
:func:`safe_path` keeps only ``A-Z a-z 0-9 . _ -`` in each part, drops empty,
``.`` and ``..`` parts and any drive or root, defuses Windows reserved names,
strips trailing dots and spaces, and limits depth and length. Names are made
unique ignoring case. :func:`write_files` creates files exclusively (never
overwriting) and checks each lands inside its directory.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from runner.record import RESERVED_STEMS, RecordError, _is_relative_path, file_entry

MAX_FILES = 500
MAX_DEPTH = 5
MAX_PART = 100
MAX_PATH = 200  # characters in a relative path
# Characters in a whole path, folder included: Windows without long-path
# support refuses paths of 260 or more, so stay well under.
MAX_FULL_PATH = 240
PREFIX = "extracted"

EXTENSIONS = {
    "html": "html", "htm": "html", "xhtml": "html", "css": "css", "scss": "scss",
    "sass": "sass", "less": "less", "js": "js", "javascript": "js", "mjs": "js",
    "cjs": "js", "jsx": "jsx", "ts": "ts", "typescript": "ts", "tsx": "tsx",
    "json": "json", "jsonc": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml",
    "ini": "ini", "xml": "xml", "svg": "svg", "md": "md", "markdown": "md",
    "py": "py", "python": "py", "python3": "py", "ipython": "py", "r": "r",
    "julia": "jl", "jl": "jl", "matlab": "m", "octave": "m", "sql": "sql",
    "sh": "sh", "bash": "sh", "shell": "sh", "zsh": "sh", "console": "txt",
    "powershell": "ps1", "ps1": "ps1", "bat": "bat", "cmd": "bat",
    "dockerfile": "dockerfile", "makefile": "mk", "make": "mk", "c": "c",
    "h": "h", "cpp": "cpp", "c++": "cpp", "cc": "cpp", "hpp": "hpp",
    "cs": "cs", "csharp": "cs", "java": "java", "kotlin": "kt", "kt": "kt",
    "go": "go", "golang": "go", "rust": "rs", "rs": "rs", "ruby": "rb",
    "rb": "rb", "php": "php", "swift": "swift", "scala": "scala", "lua": "lua",
    "perl": "pl", "pl": "pl", "dart": "dart", "vue": "vue", "svelte": "svelte",
    "graphql": "graphql", "csv": "csv", "tsv": "tsv", "tex": "tex",
    "latex": "tex", "scad": "scad", "openscad": "scad", "gcode": "gcode",
    "step": "step", "stl": "stl", "dxf": "dxf", "mermaid": "mmd", "dot": "dot",
    "text": "txt", "txt": "txt", "plaintext": "txt", "plain": "txt",
    "diff": "diff", "patch": "diff", "env": "env",
}
# File names without an extension that a model may give before a block.
BARE_NAMES = frozenset({"dockerfile", "makefile", "procfile", "gemfile",
                        "license", "readme", "rakefile", "jenkinsfile"})

_FENCE_OPEN = re.compile(r"(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)")
_HTML_DOCUMENT = re.compile(
    r"(?:<!doctype\s+html\b[^>]*>(?:\s|<!--.*?-->)*)?<html\b.*?</html\s*>",
    re.IGNORECASE | re.DOTALL)
_KEY_VALUE = re.compile(
    r"""(?:title|file|filename|name|path)\s*=\s*(?P<q>["']?)(?P<value>.+?)(?P=q)$""",
    re.IGNORECASE)
_LIST_MARKER = re.compile(r"^(?:[-*+]|\d{1,3}[.)])\s+")
_LABEL = re.compile(r"^(?:file|filename|path)\s*[:\-]\s*", re.IGNORECASE)
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,10}$")
_PATH_TOKEN = re.compile(r"[\w./\\:-]+")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_ALNUM = re.compile(r"[A-Za-z0-9]")


@dataclass(frozen=True)
class ExtractedFile:
    path: str  # safe relative path, "/" separated
    content: str
    source: str  # "fence" or "html"


# --- Names ----------------------------------------------------------------------


def _safe_part(raw):
    part = raw.strip(" ").rstrip(" .")
    part = _UNSAFE.sub("_", part)
    if not _ALNUM.search(part):
        return None
    if len(part) > MAX_PART:
        stem, dot, ext = part.rpartition(".")
        if dot and stem and len(ext) <= 10:
            part = stem[:MAX_PART - len(ext) - 1].rstrip(".") + "." + ext
        else:
            part = part[:MAX_PART].rstrip(".")
    if part.split(".")[0].upper() in RESERVED_STEMS:
        part = "_" + part
    return part


def safe_path(hint):
    """A safe relative path made from a name taken from model output, or None.

    Only the last ``MAX_DEPTH`` folders are kept; ``..`` is dropped, not
    followed, so the result never points outside the directory it is used in.
    """
    if not isinstance(hint, str):
        return None
    parts = [part for part in map(_safe_part, hint.replace("\\", "/").split("/"))
             if part]
    parts = parts[-MAX_DEPTH:]
    path = "/".join(parts)
    if len(path) > MAX_PATH and parts:
        path = parts[-1]
    return path if path and _is_relative_path(path) else None


def _looks_like_file_name(token):
    if not token or "://" in token or not _PATH_TOKEN.fullmatch(token):
        return False
    base = token.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return bool(_EXTENSION.search(base)) or base.lower() in BARE_NAMES


def _hint_from_line(line):
    """A file name standing alone on a line, such as ``**index.html**``."""
    text = line.strip().lstrip("#").strip()
    text = _LIST_MARKER.sub("", text)
    decoration = "*_`'\" "
    text = text.strip(decoration)
    text = _LABEL.sub("", text).strip(decoration)
    text = text.rstrip(":").strip(decoration).rstrip(":")
    return text if _looks_like_file_name(text) else None


def _parse_info(info):
    """(language, file name hint) from a fence's info string."""
    tokens = info.strip().split()
    if not tokens:
        return "", None
    first, rest = tokens[0], tokens[1:]
    language, hint = first, None
    if ":" in first and not re.match(r"^[A-Za-z]:[\\/]", first):
        language, _, hint = first.partition(":")
    elif _looks_like_file_name(first) and first.lower().strip("{.}") not in EXTENSIONS:
        language, hint = "", first
    for token in rest if hint is None else ():
        match = _KEY_VALUE.match(token)
        if match:
            hint = match.group("value")
            break
        if "=" not in token and "{" not in token and _PATH_TOKEN.fullmatch(token):
            hint = token
            break
    return language.lower().strip("{.}"), hint or None


def _extension(language, hint):
    if language in EXTENSIONS:
        return EXTENSIONS[language]
    if hint:
        match = _EXTENSION.search(hint)
        if match:
            return match.group(0)[1:].lower()
    return "txt"


class _Names:
    """Allocates unique paths, ignoring case, with no file/folder clash."""

    def __init__(self):
        self.files = set()
        self.folders = set()

    def _clashes(self, path):
        folded = path.casefold()
        parts = folded.split("/")
        prefixes = ["/".join(parts[:n]) for n in range(1, len(parts))]
        return (folded in self.files or folded in self.folders
                or any(prefix in self.files for prefix in prefixes))

    def allocate(self, path, limit=None):
        """A unique path based on ``path``; None (nothing reserved) if it
        would be longer than ``limit``."""
        parts = path.split("/")
        prefixes = ["/".join(parts[:n]).casefold() for n in range(1, len(parts))]
        if any(prefix in self.files for prefix in prefixes):
            path = safe_path(path.replace("/", "_")) or "file"
        folder, _, name = path.rpartition("/")
        stem, dot, ext = name.rpartition(".")
        if not stem or not dot:  # no extension, or a leading-dot name
            stem, dot, ext = name, "", ""
        candidate, number = path, 2
        while self._clashes(candidate):
            numbered = f"{stem}-{number}{dot}{ext}"
            candidate = f"{folder}/{numbered}" if folder else numbered
            number += 1
        if limit is not None and len(candidate) > limit:
            return None
        self.files.add(candidate.casefold())
        parts = candidate.casefold().split("/")
        self.folders.update("/".join(parts[:n]) for n in range(1, len(parts)))
        return candidate


# --- Finding blocks -------------------------------------------------------------


def _lines(text):
    """(start offset, line without its line break) for every line."""
    offset = 0
    for match in re.finditer(r"[^\n]*\n|[^\n]+$", text):
        line = match.group(0)
        yield offset, line.rstrip("\n").rstrip("\r"), line
        offset = match.end()


def _blocks(text):
    """Fenced blocks as (start, end, info, content, line before) and the
    spans of text they cover, including an unclosed block's remainder."""
    lines = list(_lines(text))
    blocks, spans = [], []
    index = 0
    while index < len(lines):
        start, stripped, _ = lines[index]
        opening = _FENCE_OPEN.fullmatch(stripped)
        if not opening or (opening.group("fence")[0] == "`"
                           and "`" in opening.group("info")):
            index += 1
            continue
        fence = opening.group("fence")
        closing = re.compile(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence))
                             + r",}[ \t]*")
        for end_index in range(index + 1, len(lines)):
            if closing.fullmatch(lines[end_index][1]):
                break
        else:
            spans.append((start, len(text)))  # unclosed: code to the end
            break
        indent = len(opening.group("indent"))
        body = "".join(
            re.sub(r"^ {0,%d}" % indent, "", raw) if indent else raw
            for _, _, raw in lines[index + 1:end_index])
        # The nearest non-blank line before the fence, across one blank line.
        line_before = ""
        for back in (index - 1, index - 2):
            if back >= 0 and lines[back][1].strip():
                line_before = lines[back][1]
                break
        end =lines[end_index][0] + len(lines[end_index][2])
        blocks.append((start, end, opening.group("info"), body, line_before))
        spans.append((start, end))
        index = end_index + 1
    return blocks, spans


def extract_files(text, max_length=MAX_PATH):
    """The files in ``text``, in order of appearance, at most ``MAX_FILES``.

    A name from the model longer than ``max_length`` characters (after
    making it safe and unique) is replaced by the generic name.
    """
    blocks, spans = _blocks(text)
    found = []  # (offset, source, name hint or None, generic name, content)
    for number, (start, _, info, body, line_before) in enumerate(blocks, start=1):
        if not body.strip():
            continue
        language, hint = _parse_info(info)
        if hint is None and line_before:
            hint = _hint_from_line(line_before)
        generic = f"block-{number:02d}.{_extension(language, hint)}"
        found.append((start, "fence", hint, generic, body))
    documents = 0
    # Search only up to the last closing tag, so a run of unclosed "<html"
    # tags cannot make each failed match scan to the end (quadratic time).
    last = text.lower().rfind("</html")
    closing = text.find(">", last) if last >= 0 else -1
    for match in _HTML_DOCUMENT.finditer(text, 0, closing + 1):
        if any(start < match.end() and match.start() < end for start, end in spans):
            continue
        documents += 1
        found.append((match.start(), "html", None,
                      f"document-{documents:02d}.html", match.group(0)))
    found.sort(key=lambda item: item[0])
    names, files = _Names(), []
    for _, source, hint, generic, content in found[:MAX_FILES]:
        path = safe_path(hint) if hint else None
        allocated = names.allocate(path, max_length) if path else None
        if allocated is None:
            allocated = names.allocate(generic)
        files.append(ExtractedFile(allocated, content, source))
    return files


# --- Writing --------------------------------------------------------------------


def write_files(directory, files, prefix=PREFIX):
    """Write ``files`` under ``directory/prefix`` and return their record
    ``files`` entries (paths relative to ``directory``).

    Text is written as UTF-8 (a lone surrogate becomes ``?``). A file that
    already exists is never overwritten: :class:`FileExistsError`.
    """
    base = Path(directory)
    root = base / prefix if prefix else base
    inside = root.resolve()
    for item in files:  # check every path before creating anything
        relative = f"{prefix}/{item.path}" if prefix else item.path
        if not _is_relative_path(relative):
            raise RecordError(f"unsafe file path {item.path!r}")
        if len(str(inside)) + 1 + len(item.path) > MAX_FULL_PATH:
            raise RecordError(f"file path {item.path!r} is too long: the whole "
                              f"path would pass {MAX_FULL_PATH} characters")
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for item in files:
        relative = f"{prefix}/{item.path}" if prefix else item.path
        target = root.joinpath(*item.path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.parent.resolve().is_relative_to(inside):
            raise RecordError(f"file path {item.path!r} leaves its directory")
        with open(target, "xb") as handle:
            handle.write(item.content.encode("utf-8", "replace"))
        entries.append(file_entry(base, relative))
    return entries


def save_files(directory, text, prefix=PREFIX):
    """Extract the files in ``text`` and write them under ``directory/prefix``,
    with names short enough that no whole path passes ``MAX_FULL_PATH``.
    Returns the record ``files`` entries; raises ``OSError`` or
    :class:`RecordError` (then some files may already be written)."""
    root = (Path(directory) / prefix).resolve() if prefix else Path(directory).resolve()
    budget = MAX_FULL_PATH - len(str(root)) - 1
    return write_files(directory, extract_files(text, min(MAX_PATH, budget)), prefix)
