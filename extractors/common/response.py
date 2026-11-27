"""One output of a pipeline, math or engineering run, as its extractors read
it: the reply's text and the files extracted from it.

With a record, the text is ``raw_response`` and the files are the record's.
With a folder (``--dir``), the text is ``response.md`` if there is one, and
its fenced blocks are the files when the folder holds nothing else;
otherwise the folder's ``.md`` and ``.txt`` files are the text.
"""

import re
from dataclasses import dataclass

from extractors.base import InputFile
from extractors.common import code
from runner.files import extract_files

MAX_TEXT = 1_000_000          # characters of reply text read
MAX_SOURCE = 1_000_000        # characters of file text read, all files together
RESPONSE_FILE = "response.md"
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})([^\n]{0,200})")
_GENERIC = re.compile(r"(?:block|document)-\d{1,4}(?:-\d{1,4})?\.[a-z0-9]{1,10}")
# Fence languages whose content may be the reply's working, not a program.
PLAIN = ("", "text", "txt", "plain", "plaintext", "math", "latex", "tex")


@dataclass(frozen=True)
class Block:
    """A fenced block: the first word of its info string and its body."""

    language: str
    body: str


@dataclass(frozen=True)
class Source:
    """A file of the output. ``language`` is None for what is not
    recognised; ``named`` is False for a generic ``block-NN`` name."""

    path: str
    language: object
    text: str
    named: bool

    @property
    def name(self):
        return self.path.rsplit("/", 1)[-1].lower()


@dataclass(frozen=True)
class Doc:
    text: str           # the whole reply
    prose: str          # outside fenced blocks
    working: str        # prose and the plain-text blocks
    blocks: tuple
    files: tuple        # Source, by path
    prompt: str         # the prompt, when there is a record
    truncated: bool

    @property
    def has_text(self):
        return bool(self.text.strip())


def split_fences(text):
    """``(prose lines, blocks)``. An unclosed block runs to the end: a cut-off
    program is still a program, not prose."""
    prose, blocks = [], []
    fence = language = None
    body = []
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if fence is None:
            opening = _FENCE.match(line)
            if opening and not (opening[1][0] == "`" and "`" in opening[2]):
                fence = opening[1]
                words = opening[2].strip().strip("{}.").split(None, 1)
                language = words[0].split(":")[0].lower() if words else ""
                body = []
                prose.append("")
            else:
                prose.append(line)
        else:
            stripped = line.strip()
            if stripped.startswith(fence) and not stripped.strip(fence[0]):
                blocks.append(Block(language, "\n".join(body)))
                fence = None
            else:
                body.append(line)
    if fence is not None:
        blocks.append(Block(language, "\n".join(body)))
    return prose, blocks


def _sources(files):
    out, left, cut = [], MAX_SOURCE, False
    for item in files:
        text = item.text[:max(left, 0)]
        cut = cut or len(text) < len(item.text)
        left -= len(text)
        text = text.replace("\r\n", "\n")     # patterns read line ends as \n
        name = item.path.rsplit("/", 1)[-1]
        out.append(Source(item.path, code.language_of(item.path, text), text,
                          not _GENERIC.fullmatch(name)))
    return tuple(out), cut


def _build(inputs):
    files = list(inputs.files)
    record = inputs.record
    prompt = ""
    if record is not None:
        text = record.get("raw_response") or ""
        prompt = (record.get("prompt_text") or "")[:MAX_TEXT]
    else:
        reply = next((f for f in files if f.path.lower() == RESPONSE_FILE), None)
        if reply is not None:
            text = reply.text
            files = [f for f in files if f is not reply]
            if not files:
                files = sorted(
                    (InputFile(f.path, f.content.encode("utf-8", "replace"))
                     for f in extract_files(text[:MAX_TEXT])),
                    key=lambda f: f.path)
        else:
            text = "\n\n".join(f.text[:MAX_TEXT] for f in files
                               if f.suffix in ("md", "txt"))
    truncated = len(text) > MAX_TEXT
    text = text[:MAX_TEXT].replace("\r\n", "\n")
    prose_lines, blocks = split_fences(text)
    prose = "\n".join(prose_lines)
    plain = [b.body for b in blocks
             if b.language in PLAIN and code.sniff(b.body) is None]
    sources, cut = _sources(files)
    return Doc(text=text, prose=prose, working="\n".join([prose, *plain]),
               blocks=tuple(blocks), files=sources, prompt=prompt,
               truncated=truncated or cut)


def get_doc(inputs):
    """The :class:`Doc` of ``inputs``, built once per output."""
    return inputs.cached("t2.8.doc", lambda: _build(inputs))


def result(doc, values):
    """``values`` with the status the reading earned."""
    return {"status": "partial" if doc.truncated else "ok", **values}


NO_INPUT = {"status": "no-input"}
