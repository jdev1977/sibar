"""WebDev Arena preference rows to run records (task T5.2).

Read docs/webdev-arena.md first: the dataset has its own licence agreement,
which is accepted by accessing the data, and it may not be passed on. This
module downloads nothing and accepts nothing. It reads a file that is already
on this machine, and writes records only outside git or to an ignored folder.

    python -m importers.webdev_arena SOURCE OUTPUT.jsonl --revision SHA

The dataset card names the columns but does not describe what is inside them,
and no dataset row was read while writing this. The shapes accepted here
(see docs/webdev-arena.md, "Assumed row shape") are assumptions: anything else
is skipped and counted, never guessed at.

Every record has source ``uncontrolled_import``, so the metrics leave it out.
The input is read as a stream, one row in memory at a time. It is untrusted:
it is only parsed as JSON, and file names go through :mod:`runner.files`.
"""

import argparse
import datetime
import itertools
import json
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from runner.files import (MAX_FULL_PATH, MAX_PATH, PREFIX, ExtractedFile,
                          extract_files, safe_path, write_files)
from runner.record import (RecordError, append_record, build_record, files_dir,
                           parse_json)

DATASET = "lmarena-ai/webdev-arena-preference-10k"
DATASET_NAME = "WebDev Arena Preference Dataset"
# The records carry no task of ours: users typed whatever they liked.
TASK_ID = "uncontrolled-prompt"
MAX_ROW = 16 * 1024 * 1024  # bytes of JSON in one row
CHUNK = 1 << 16
# Output inside a git checkout must be under one of these ignored folders.
IGNORED_FOLDERS = ("data", "runs", "outputs")
# Seconds since 1970 outside this range are another unit or a mistake. WebDev
# Arena opened in December 2024.
EARLIEST = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

# A model's maker, only where the model name starts with the maker's own brand.
_PROVIDERS = (
    ("anthropic", r"claude"),
    ("openai", r"gpt|chatgpt|o1|o3|o4"),
    ("google", r"gemini|gemma"),
    ("deepseek", r"deepseek"),
    ("meta", r"llama|meta-llama"),
    ("alibaba", r"qwen"),
    ("mistral", r"mistral|codestral"),
)
_STRUCTURAL = re.compile(rb'[\\"{}\[\],]')
_IN_STRING = re.compile(rb'[\\"]')
_BOM = b"\xef\xbb\xbf"


class ImportRefused(Exception):
    """The import cannot run; the message says why."""


@dataclass(frozen=True)
class BadRow:
    """A row of the input that could not be read."""

    reason: str


class _Skip(Exception):
    """A row or one side of it cannot become a record; the text is the reason."""


@dataclass
class Counts:
    rows: int = 0
    records: int = 0
    skipped_rows: Counter = field(default_factory=Counter)
    skipped_sides: Counter = field(default_factory=Counter)


# --- Reading the input --------------------------------------------------------------


def _parse(data):
    try:
        return parse_json(bytes(data))
    except (RecordError, RecursionError):
        return BadRow("not valid JSON")


def _array_rows(handle, first, chunk_size, max_row):
    """The elements of a top-level JSON array; ``first`` is what follows ``[``.

    Only brackets, commas and strings are followed to find where each element
    ends, so a bad element is reported and reading goes on. An element with
    unbalanced brackets or quotes takes what follows with it.
    """
    element, too_large = bytearray(), False
    depth, in_string, skip = 0, False, 0
    chunk = first
    while True:
        start = 0  # of the part of this chunk not yet added to the element
        position, skip = skip, 0
        while True:
            pattern = _IN_STRING if in_string else _STRUCTURAL
            match = pattern.search(chunk, position)
            if match is None:
                break
            char, position = match.group(), match.end()
            if char == b"\\":
                if in_string:
                    position += 1  # the escaped character
                    skip = max(0, position - len(chunk))
            elif char == b'"':
                in_string = not in_string
            elif char in (b"{", b"["):
                depth += 1
            elif depth and char in (b"}", b"]"):
                depth -= 1
            elif not depth and char in (b",", b"]"):
                if not too_large:
                    element += chunk[start:match.start()]
                start = position
                if too_large or len(element) > max_row:
                    yield BadRow("row too large")
                elif element.strip():
                    yield _parse(element)
                elif char == b",":
                    yield BadRow("not valid JSON")
                element, too_large = bytearray(), False
                if char == b"]":
                    return
        if not too_large:
            element += chunk[start:]
            if len(element) > max_row:
                element, too_large = bytearray(), True
        chunk = handle.read(chunk_size)
        if not chunk:
            yield BadRow("file ends inside the array")
            return


def _line_rows(handle, max_row):
    while True:
        line = handle.readline(max_row + 1)
        if not line:
            return
        if len(line.rstrip(b"\r\n")) > max_row:
            while line and not line.endswith(b"\n"):
                line = handle.readline(CHUNK)
            yield BadRow("row too large")
        elif line.strip():
            yield _parse(line)


def iter_rows(path, chunk_size=CHUNK, max_row=MAX_ROW):
    """The rows of a JSON array or JSON Lines file, one at a time: each is the
    parsed value or a :class:`BadRow`. At most about ``max_row`` bytes of the
    file are held."""
    with open(path, "rb") as handle:
        start = 0
        if handle.read(len(_BOM)) == _BOM:
            start = len(_BOM)
        handle.seek(start)
        while True:
            chunk = handle.read(chunk_size)
            rest = chunk.lstrip()
            if rest or not chunk:
                break
        if rest.startswith(b"["):
            yield from _array_rows(handle, rest[1:], chunk_size, max_row)
        else:
            handle.seek(start)
            yield from _line_rows(handle, max_row)


# --- One row to records -------------------------------------------------------------


def _question_id(row):
    value = row.get("question_id")
    if type(value) is int:
        return str(value)
    if (isinstance(value, str) and value.strip() and len(value) <= 200
            and value.isprintable()):
        return value
    raise _Skip("no question_id")


def _timestamp(value):
    """``tstamp`` as an aware datetime: seconds since 1970, or ISO 8601 text
    that states its time zone."""
    try:
        if type(value) in (int, float):
            moment = datetime.datetime.fromtimestamp(value, datetime.timezone.utc)
        elif isinstance(value, str):
            moment = datetime.datetime.fromisoformat(value)
        else:
            moment = None
        if (moment is not None and moment.utcoffset() is not None
                and EARLIEST <= moment <= datetime.datetime.now(datetime.timezone.utc)):
            return moment
    except (ValueError, OverflowError, OSError):
        pass
    raise _Skip("no usable tstamp")


def _provider(model):
    name = model.lower()
    for provider, prefixes in _PROVIDERS:
        if re.match(rf"(?:{prefixes})(?![a-z0-9])", name):
            return provider
    return "unknown"


def _text(content):
    """(text, number of non-text parts) of a message's content: text, or a
    list of parts of which those of type ``text`` are joined."""
    if isinstance(content, str):
        return content, 0
    if isinstance(content, list) and all(
            isinstance(part, dict) and isinstance(part.get("type"), str)
            for part in content):
        texts = [part.get("text") for part in content if part["type"] == "text"]
        if all(isinstance(text, str) for text in texts):
            return "".join(texts), len(content) - len(texts)
    raise _Skip("unrecognised conversation")


def _first_turn(conversation):
    """The system text, first user message, first reply and user turn count."""
    if not isinstance(conversation, list) or not all(
            isinstance(m, dict) and m.get("role") in ("system", "user", "assistant")
            and "content" in m for m in conversation):
        raise _Skip("unrecognised conversation")
    roles = [message["role"] for message in conversation]
    if "user" not in roles:
        raise _Skip("no prompt text")
    asked = roles.index("user")
    system = None
    before = [m for m in conversation[:asked] if m["role"] == "system"]
    if before:
        system = _text(before[0]["content"])[0]
    prompt, dropped = _text(conversation[asked]["content"])
    if not prompt.strip():
        raise _Skip("no prompt text")
    if roles[asked + 1:asked + 2] != ["assistant"]:
        raise _Skip("no response text")
    response, other = _text(conversation[asked + 1]["content"])
    if other:
        raise _Skip("unrecognised conversation")
    if not response.strip():
        raise _Skip("no response text")
    return system, prompt, dropped, response, roles.count("user")


def _response_files(text, budget):
    """The files of a reply. WebDev Arena asked models for a JSON object with
    ``file_path`` and ``code``; any other reply is read as ordinary text."""
    try:
        reply = json.loads(text) if text.lstrip().startswith("{") else None
    except (ValueError, RecursionError):
        reply = None
    if isinstance(reply, dict):
        name, code = reply.get("file_path"), reply.get("code")
        if isinstance(name, str) and isinstance(code, str) and code.strip():
            path = safe_path(name)
            if path is None or len(path) > budget:
                path = "document-01.txt"
            return [ExtractedFile(path, code, "json")]
    return extract_files(text, budget)


def _record(row, side, question_id, moment, revision):
    model = row.get(f"model_{side}")
    if not (isinstance(model, str) and model.isprintable() and model
            and not any(c.isspace() for c in model)):
        raise _Skip("no usable model name")
    system, prompt, dropped, response, turns = _first_turn(
        row.get(f"conversation_{side}"))
    provider = _provider(model)
    notes = [
        f"{DATASET_NAME} ({DATASET}), revision {revision}",
        f"question_id {question_id}, side {side}",
        "uncontrolled user prompt typed into WebDev Arena",
        "timestamp is the row's tstamp",
        "provider " + ("not known" if provider == "unknown"
                       else "inferred from the model name"),
        "status ok means reply text is present; completion is not reported",
        "settings, tokens, cost, stop reason, request id and returned model id "
        "are not given: empty or null",
        "system_prompt " + ("is from the conversation" if system and system.strip()
                            else "is null: not given, though the arena may have "
                                 "sent one"),
    ]
    if turns > 1:
        notes.append(f"only the first of {turns} user turns is imported")
    if dropped:
        notes.append(f"{dropped} non-text prompt part{'s' if dropped > 1 else ''} "
                     "not imported")
    return build_record(
        record_id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                                 f"{DATASET}/{question_id}/{side}")),
        source="uncontrolled_import",
        source_note="; ".join(notes),
        project_type="website",
        task_id=TASK_ID,
        prompt_text=prompt,
        provider=provider,
        model_id=model,
        surface="product",
        system_prompt=system if system and system.strip() else None,
        timestamp=moment,
        status="ok",
        raw_response=response,
    )


# --- The import ---------------------------------------------------------------------


def _check_output(output):
    if output.exists():
        raise ImportRefused(f"{output.name} already exists; choose a new file")
    resolved = output.resolve()
    for folder in resolved.parents:
        if (folder / ".git").exists():
            parts = resolved.relative_to(folder).parts
            if len(parts) < 2 or parts[0] not in IGNORED_FOLDERS:
                raise ImportRefused(
                    "dataset content must not enter git: inside a checkout, write "
                    f"under {', '.join(IGNORED_FOLDERS)}")
            return


def import_file(source, output, *, revision, limit=None, max_row=MAX_ROW):
    """Import the rows of ``source`` into the new record file ``output``, with
    the files of each reply beside it. ``revision`` is the dataset revision the
    file came from. Reads at most ``limit`` rows. Returns :class:`Counts`."""
    source, output = Path(source), Path(output)
    if not (isinstance(revision, str) and revision.split() == [revision]):
        raise ImportRefused("give the dataset revision, one word")
    if not source.is_file():
        raise ImportRefused(f"{source.name} is not a file")
    _check_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.open("xb").close()
    counts, seen = Counts(), set()
    for row in itertools.islice(iter_rows(source, max_row=max_row), limit):
        counts.rows += 1
        try:
            if isinstance(row, BadRow):
                raise _Skip(row.reason)
            if not isinstance(row, dict):
                raise _Skip("not a JSON object")
            question_id = _question_id(row)
            moment = _timestamp(row.get("tstamp"))
        except _Skip as skip:
            counts.skipped_rows[str(skip)] += 1
            continue
        for side in "ab":
            try:
                record = _record(row, side, question_id, moment, revision)
                if record["record_id"] in seen:
                    raise _Skip("repeats an earlier question_id and side")
                directory = files_dir(output, record["record_id"])
                budget = MAX_FULL_PATH - len(str((directory / PREFIX).resolve())) - 1
                found = _response_files(record["raw_response"],
                                        min(MAX_PATH, budget))
                if found:
                    try:
                        record["files"] = write_files(directory, found)
                    except FileExistsError:
                        raise _Skip("files for this record already exist") from None
            except _Skip as skip:
                counts.skipped_sides[str(skip)] += 1
                continue
            append_record(output, record)
            seen.add(record["record_id"])
            counts.records += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m importers.webdev_arena",
        description="Import WebDev Arena rows from a local file as run records. "
                    "Read docs/webdev-arena.md about the licence first.")
    parser.add_argument("source", help="a JSON array or JSON Lines file")
    parser.add_argument("output", help="the new record file, such as "
                        "data/webdev-arena/records.jsonl")
    parser.add_argument("--revision", required=True,
                        help="the dataset revision (commit) the file came from")
    parser.add_argument("--limit", type=int, help="read at most this many rows")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be 0 or more")
    try:
        counts = import_file(args.source, args.output, revision=args.revision,
                             limit=args.limit)
    except (ImportRefused, RecordError, OSError) as error:
        print(f"import stopped: {error}", file=sys.stderr)
        return 2
    print(f"rows read: {counts.rows}")
    print(f"records written: {counts.records}")
    for title, skipped in (("rows", counts.skipped_rows),
                           ("sides", counts.skipped_sides)):
        print(f"{title} skipped: {sum(skipped.values())}")
        for reason, number in sorted(skipped.items()):
            print(f"  {reason}: {number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
