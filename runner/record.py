"""The run record format (task T0.4): one JSON object per run, one per line.

This module is the single definition of the format; ``docs/record-format.md``
describes it for readers. The validator uses only the standard library: the
rules that matter most here (UTC-only timestamps, portable relative paths,
"an ok record needs its raw response", null allowed only for imports) are
plain Python checks either way, and a schema library would add dependencies
without removing any of that code.

Public interface:

- :func:`build_record` makes a valid record, filling defaults.
- :func:`validate_record` returns every problem with a record (empty if valid).
- :func:`append_record`, :func:`read_records`, :func:`repair_tail` and
  :func:`write_records` (atomic rewrite) handle the JSON Lines file;
  :func:`dumps_record` gives the exact line written and :func:`parse_line`
  reads one.
- :func:`format_timestamp` and :func:`utc_now` give record timestamps.
- :func:`cell_key` names the grid cell a record fills, for resuming.
- :func:`files_dir`, :func:`file_entry`, :func:`check_files` handle the files
  stored beside a record.
- :func:`with_features` adds or replaces one extractor's features and marks
  that it ran.

Run ``python -m runner.record [--files] FILE...`` to validate files.
"""

import copy
import datetime
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

SCHEMA_VERSION = 1

LEVELS = ("L0", "L1", "L2")
WORDINGS = ("A", "B")
SURFACES = ("api", "product")
SOURCES = ("controlled", "uncontrolled_import", "manual")
STATUSES = ("ok", "failed", "refused", "truncated")
CHECK_OUTCOMES = ("ok", "failed", "error")
# Project types in use so far. New types need no schema change: any slug is
# accepted, and this tuple is for reference only.
KNOWN_PROJECT_TYPES = ("website", "pipeline", "math", "engineering")

# Every top-level field, in the order records are written. All are required;
# a field that does not apply holds null (or an empty list).
FIELDS = (
    "schema_version", "record_id", "batch_id", "source", "source_note",
    "project_type", "task_id", "prompt_set_version", "level", "wording",
    "run_index", "prompt_text", "provider", "gateway", "model_id",
    "model_id_returned", "surface", "system_prompt", "settings", "timestamp",
    "tokens", "cost_usd", "status", "error", "stop_reason", "request_id",
    "raw_response", "files", "checks", "extractors", "features",
)
# Fields that may be null only on an uncontrolled import, whose source did not
# follow the level / wording / run grid.
GRID_FIELDS = ("prompt_set_version", "level", "wording", "run_index")
TOKEN_FIELDS = ("input", "output", "reasoning")
FILE_FIELDS = ("path", "sha256", "size")
CHECK_FIELDS = ("name", "tool", "tool_version", "outcome", "detail", "files")
FEATURE_FIELDS = ("name", "value", "extractor", "extractor_version")
EXTRACTOR_FIELDS = ("extractor", "extractor_version")
# Windows refuses these file names, with or without an extension.
RESERVED_STEMS = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{n}" for n in range(1, 10)] + [f"LPT{n}" for n in range(1, 10)]
)


class RecordError(ValueError):
    """A record, record file or file path breaks the format.

    ``errors`` holds every problem found, one message each.
    """

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


class CellKey(NamedTuple):
    """The grid cell a record fills; a resumed run skips completed cells.

    It includes the batch and prompt-set version, so a new batch or a revised
    prompt set never counts older records as filling its cells.
    """

    batch_id: Optional[str]
    project_type: str
    task_id: str
    prompt_set_version: Optional[str]
    level: Optional[str]
    wording: Optional[str]
    model_id: str
    surface: str
    run_index: Optional[int]


# --- Value tests -------------------------------------------------------------

_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
_TOKEN = re.compile(r"\S+")  # one word: no spaces, tabs or newlines
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)(Z|[+-]\d{2}:\d{2})?"
)
_PATH_PART = re.compile(r"[^\x00-\x1f\\:/]+")

SLUG = "a slug (lower-case letters, digits, '.', '_' or '-')"
WORD = "text with no spaces"
TEXT = "non-empty text"
COUNT = "a whole number of at least 0"
PATH = ("a relative path using / with no empty, '.' or '..' parts, no part "
        "ending in a space or dot, no Windows reserved name (CON, NUL, COM1...), "
        "and no drive, colon or backslash")
JSON_VALUE = ("JSON (finite numbers, text, true/false, null, lists, "
              "objects with text keys)")


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_slug(value):
    return isinstance(value, str) and _SLUG.fullmatch(value) is not None


def _is_word(value):
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _is_count(value):
    return type(value) is int and value >= 0


def _is_money(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _is_relative_path(value):
    if not isinstance(value, str) or not value:
        return False
    return all(
        _PATH_PART.fullmatch(part)
        and not part.endswith((" ", "."))  # also rules out "." and ".."
        and part.split(".")[0].rstrip(" ").upper() not in RESERVED_STEMS
        for part in value.split("/")
    )


def _json_problem(value, where):
    """Where ``value`` stops being plain JSON, or None if it is plain JSON."""
    if value is None or type(value) in (str, bool, int):
        return None
    if type(value) is float:
        return None if math.isfinite(value) else where
    if isinstance(value, list):
        for index, item in enumerate(value):
            problem = _json_problem(item, f"{where}[{index}]")
            if problem:
                return problem
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return where
            problem = _json_problem(item, f"{where}.{key}")
            if problem:
                return problem
        return None
    return where


def _timestamp_problem(value):
    """Why ``value`` is not a UTC timestamp, or None."""
    match = _TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return ("must be an ISO 8601 date and time in UTC, "
                "such as 2026-11-25T14:03:07Z")
    if match.group(2) is None:
        return "has no time zone (naive); it must end in Z"
    if match.group(2) == "-00:00":  # RFC 3339: "UTC time, local offset unknown"
        return "must be in UTC (Z or +00:00)"
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        return "is not a real date and time"
    if moment.utcoffset() != datetime.timedelta(0):
        return "must be in UTC (Z or +00:00)"
    return None


# --- The validator -----------------------------------------------------------


class _Problems:
    def __init__(self):
        self.items = []

    def add(self, where, message):
        self.items.append(f"{where}: {message}")

    def expect(self, ok, where, expected):
        if not ok:
            self.add(where, f"must be {expected}")
        return ok


def _keys(problems, mapping, where, names):
    """Report missing and unknown keys; return False if not a mapping."""
    if not isinstance(mapping, dict):
        problems.add(where, "must be a JSON object")
        return False
    for name in names:
        if name not in mapping:
            problems.add(where, f"missing field {name!r}")
    for name in mapping:
        if name not in names:
            problems.add(where, f"unknown field {name!r}")
    return True


def _check_file_list(problems, entries, where, seen_paths):
    if not problems.expect(isinstance(entries, list), where, "a list"):
        return
    for index, entry in enumerate(entries):
        at = f"{where}[{index}]"
        if not _keys(problems, entry, at, FILE_FIELDS):
            continue
        if "path" in entry:
            path = entry["path"]
            if problems.expect(_is_relative_path(path), f"{at}.path", PATH):
                # Windows and macOS file systems ignore case by default.
                folded = path.casefold()
                if folded in seen_paths:
                    problems.add(at, f"repeats the file path {path!r} "
                                     "(compared ignoring case)")
                seen_paths.add(folded)
        if "sha256" in entry:
            problems.expect(
                isinstance(entry["sha256"], str)
                and _SHA256.fullmatch(entry["sha256"]),
                f"{at}.sha256", "64 lower-case hex digits",
            )
        if "size" in entry:
            problems.expect(_is_count(entry["size"]), f"{at}.size", COUNT)


def _check_checks(problems, entries, seen_paths):
    if not problems.expect(isinstance(entries, list), "checks", "a list"):
        return
    for index, entry in enumerate(entries):
        at = f"checks[{index}]"
        if not _keys(problems, entry, at, CHECK_FIELDS):
            continue
        for key in ("name", "tool"):
            if key in entry:
                problems.expect(_is_slug(entry[key]), f"{at}.{key}", SLUG)
        if "tool_version" in entry:
            problems.expect(_is_word(entry["tool_version"]),
                            f"{at}.tool_version", WORD)
        if "outcome" in entry:
            problems.expect(entry["outcome"] in CHECK_OUTCOMES, f"{at}.outcome",
                            "one of " + ", ".join(CHECK_OUTCOMES))
        if "detail" in entry:
            bad = _json_problem(entry["detail"], f"{at}.detail")
            if bad:
                problems.add(bad, f"must be {JSON_VALUE}")
        if "files" in entry:
            _check_file_list(problems, entry["files"], f"{at}.files", seen_paths)


def _check_extractors(problems, entries):
    """Check the ``extractors`` list; return {extractor: version}, or None if
    the list is too broken to check features against."""
    if not problems.expect(isinstance(entries, list), "extractors", "a list"):
        return None
    listed, whole = {}, True
    for index, entry in enumerate(entries):
        at = f"extractors[{index}]"
        if not _keys(problems, entry, at, EXTRACTOR_FIELDS):
            whole = False
            continue
        valid = True
        if "extractor" in entry:
            valid &= problems.expect(_is_slug(entry["extractor"]),
                                     f"{at}.extractor", SLUG)
        if "extractor_version" in entry:
            valid &= problems.expect(_is_word(entry["extractor_version"]),
                                     f"{at}.extractor_version", WORD)
        if not valid or any(key not in entry for key in EXTRACTOR_FIELDS):
            whole = False
            continue
        name = entry["extractor"]
        if name in listed:
            problems.add(at, f"repeats extractor {name!r}")
            whole = False
            continue
        listed[name] = entry["extractor_version"]
    return listed if whole else None


def _check_features(problems, entries, listed):
    if not problems.expect(isinstance(entries, list), "features", "a list"):
        return
    seen = set()
    for index, entry in enumerate(entries):
        at = f"features[{index}]"
        if not _keys(problems, entry, at, FEATURE_FIELDS):
            continue
        valid = True
        for key in ("name", "extractor"):
            if key in entry:
                valid &= problems.expect(_is_slug(entry[key]), f"{at}.{key}", SLUG)
        if "extractor_version" in entry:
            valid &= problems.expect(_is_word(entry["extractor_version"]),
                                     f"{at}.extractor_version", WORD)
        if "value" in entry:
            bad = _json_problem(entry["value"], f"{at}.value")
            if bad:
                problems.add(bad, f"must be {JSON_VALUE}")
        if not valid or any(key not in entry for key in FEATURE_FIELDS):
            continue
        name, extractor = entry["name"], entry["extractor"]
        version = entry["extractor_version"]
        if (extractor, name) in seen:
            problems.add(at, f"repeats feature {name!r} from extractor {extractor!r}")
        seen.add((extractor, name))
        if listed is None:
            continue
        if extractor not in listed:
            problems.add(at, f"extractor {extractor!r} is not listed in extractors")
        elif listed[extractor] != version:
            problems.add(at, f"extractor {extractor!r} version {version!r} does not "
                             f"match extractors ({listed[extractor]!r})")


def validate_record(record):
    """Return a list of every problem with ``record``; empty means valid."""
    problems = _Problems()
    if not isinstance(record, dict):
        return ["record: must be a JSON object"]
    for name in FIELDS:
        if name not in record:
            problems.items.append(f"missing field {name!r}")
    for name in record:
        if name not in FIELDS:
            problems.items.append(f"unknown field {name!r}")

    def has(name):
        return name in record

    def get(name):
        return record.get(name)

    source = get("source")
    source_ok = has("source") and problems.expect(
        source in SOURCES, "source", "one of " + ", ".join(SOURCES))
    imported = source_ok and source == "uncontrolled_import"
    controlled = source_ok and source == "controlled"

    if has("schema_version"):
        version = get("schema_version")
        problems.expect(type(version) is int and version == SCHEMA_VERSION,
                        "schema_version", str(SCHEMA_VERSION))
    if has("record_id"):
        problems.expect(isinstance(get("record_id"), str)
                        and _UUID.fullmatch(get("record_id")),
                        "record_id", "a lower-case UUID")
    if has("source_note"):
        problems.expect(get("source_note") is None or _is_text(get("source_note")),
                        "source_note", TEXT + " or null")

    if has("batch_id"):
        problems.expect(get("batch_id") is None or _is_word(get("batch_id")),
                        "batch_id", WORD + " or null")
    for name in ("project_type", "task_id", "provider"):
        if has(name):
            problems.expect(_is_slug(get(name)), name, SLUG)
    if has("gateway"):
        problems.expect(get("gateway") is None or _is_slug(get("gateway")),
                        "gateway", SLUG + " or null")
    if has("model_id"):
        problems.expect(_is_word(get("model_id")), "model_id", WORD)
    for name in ("model_id_returned", "request_id"):
        if has(name):
            problems.expect(get(name) is None or _is_word(get(name)),
                            name, WORD + " or null")
    if has("prompt_text"):
        problems.expect(_is_text(get("prompt_text")), "prompt_text", TEXT)

    grid_rules = {
        "prompt_set_version": (_is_word, WORD),
        "level": (lambda v: v in LEVELS, "one of " + ", ".join(LEVELS)),
        "wording": (lambda v: v in WORDINGS, "one of " + ", ".join(WORDINGS)),
        "run_index": (lambda v: type(v) is int and v >= 1,
                      "a whole number of at least 1"),
    }
    for name, (valid, expected) in grid_rules.items():
        if not has(name):
            continue
        value = get(name)
        if value is None and (imported or not source_ok):
            continue  # null is allowed, or depends on a source already reported
        problems.expect(value is not None and valid(value), name, expected)

    surface_ok = has("surface") and problems.expect(
        get("surface") in SURFACES, "surface", "one of " + ", ".join(SURFACES))
    if controlled and surface_ok and get("surface") != "api":
        problems.add("surface", "a controlled record must be on the api surface")

    if has("system_prompt"):
        prompt = get("system_prompt")
        if problems.expect(prompt is None or _is_text(prompt),
                           "system_prompt", TEXT + " or null"):
            if controlled and prompt is not None:
                problems.add("system_prompt", "must be null for a controlled record")

    if has("settings"):
        settings = get("settings")
        if problems.expect(isinstance(settings, dict), "settings", "a JSON object"):
            bad = _json_problem(settings, "settings")
            if bad:
                problems.add(bad, f"must be {JSON_VALUE}")

    if has("timestamp"):
        problem = _timestamp_problem(get("timestamp"))
        if problem:
            problems.add("timestamp", problem)

    if has("tokens") and _keys(problems, get("tokens"), "tokens", TOKEN_FIELDS):
        for key in TOKEN_FIELDS:
            value = get("tokens").get(key)
            if key in get("tokens"):
                problems.expect(value is None or _is_count(value),
                                f"tokens.{key}", COUNT + " or null")

    if has("cost_usd"):
        cost = get("cost_usd")
        problems.expect(cost is None or _is_money(cost),
                        "cost_usd", "a number of at least 0 or null")

    status = get("status")
    status_ok = has("status") and problems.expect(
        status in STATUSES, "status", "one of " + ", ".join(STATUSES))

    if has("error"):
        error = get("error")
        if problems.expect(error is None or _is_text(error), "error",
                           TEXT + " or null") and status_ok:
            if status == "failed" and error is None:
                problems.add("error", "a failed record needs an error message")
            if status == "ok" and error is not None:
                problems.add("error", "must be null for an ok record")

    if has("stop_reason"):
        problems.expect(get("stop_reason") is None or _is_text(get("stop_reason")),
                        "stop_reason", TEXT + " or null")

    if has("raw_response"):
        raw = get("raw_response")
        if problems.expect(raw is None or isinstance(raw, str),
                           "raw_response", "text or null"):
            # Stored unedited; stripping is only for this test.
            if status_ok and status == "ok" and not (raw or "").strip():
                problems.add("raw_response", "an ok record needs the raw response "
                                             "(not empty or only whitespace)")

    seen_paths = set()
    if has("files"):
        _check_file_list(problems, get("files"), "files", seen_paths)
    if has("checks"):
        _check_checks(problems, get("checks"), seen_paths)
    listed = _check_extractors(problems, get("extractors")) if has("extractors") else None
    if has("features"):
        _check_features(problems, get("features"), listed)

    return problems.items


def _raise_if_invalid(record):
    errors = validate_record(record)
    if errors:
        raise RecordError(errors)


# --- Building records --------------------------------------------------------


def format_timestamp(moment):
    """A timezone-aware datetime as the record's UTC timestamp text."""
    if not isinstance(moment, datetime.datetime) or moment.utcoffset() is None:
        raise RecordError("timestamp: has no time zone (naive); "
                          "give a timezone-aware datetime")
    moment = moment.astimezone(datetime.timezone.utc)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now():
    """The current time as a record timestamp."""
    return format_timestamp(datetime.datetime.now(datetime.timezone.utc))


def build_record(
    *,
    project_type,
    task_id,
    prompt_text,
    provider,
    model_id,
    status,
    level=None,
    wording=None,
    run_index=None,
    prompt_set_version=None,
    surface="api",
    source="controlled",
    source_note=None,
    system_prompt=None,
    settings=None,
    timestamp=None,
    tokens=None,
    cost_usd=None,
    error=None,
    stop_reason=None,
    raw_response=None,
    files=(),
    checks=(),
    features=(),
    extractors=None,
    record_id=None,
    batch_id=None,
    gateway=None,
    model_id_returned=None,
    request_id=None,
):
    """Return a new valid record; raise :class:`RecordError` listing all problems.

    ``timestamp`` may be a timezone-aware datetime or record timestamp text and
    defaults to now. ``tokens`` may give only the counts that are known.
    ``record_id`` defaults to a new random UUID. ``extractors`` defaults to
    the extractors named in ``features``. Inputs are copied.
    """
    if isinstance(timestamp, datetime.datetime):
        timestamp = format_timestamp(timestamp)
    features = list(features)  # once: it may be a generator, and is read twice
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id if record_id is not None else str(uuid.uuid4()),
        "batch_id": batch_id,
        "source": source,
        "source_note": source_note,
        "project_type": project_type,
        "task_id": task_id,
        "prompt_set_version": prompt_set_version,
        "level": level,
        "wording": wording,
        "run_index": run_index,
        "prompt_text": prompt_text,
        "provider": provider,
        "gateway": gateway,
        "model_id": model_id,
        "model_id_returned": model_id_returned,
        "surface": surface,
        "system_prompt": system_prompt,
        "settings": {} if settings is None else settings,
        "timestamp": utc_now() if timestamp is None else timestamp,
        "tokens": {**dict.fromkeys(TOKEN_FIELDS), **(tokens or {})},
        "cost_usd": cost_usd,
        "status": status,
        "error": error,
        "stop_reason": stop_reason,
        "request_id": request_id,
        "raw_response": raw_response,
        "files": list(files),
        "checks": list(checks),
        "extractors": (_extractors_of(features) if extractors is None
                       else list(extractors)),
        "features": features,
    }
    record = copy.deepcopy(record)
    _raise_if_invalid(record)
    return record


def _extractors_of(features):
    """The extractors named in feature entries, first appearance first.

    Entries without a text extractor name are skipped; validation reports them.
    """
    listed = {}
    for entry in features:
        if isinstance(entry, dict) and isinstance(entry.get("extractor"), str):
            listed.setdefault(entry["extractor"], entry.get("extractor_version"))
    return [{"extractor": name, "extractor_version": version}
            for name, version in listed.items()]


def cell_key(record):
    """The :class:`CellKey` of a record: batch, type, task, prompt-set
    version, level, wording, model, surface and run index."""
    return CellKey(*(record[name] for name in CellKey._fields))


def with_features(record, extractor, extractor_version, values):
    """A copy of ``record`` whose features from ``extractor`` are replaced by
    ``values`` (a mapping of feature name to JSON value), all at
    ``extractor_version``, and whose ``extractors`` entry for it is set to that
    version. Empty ``values`` records that the extractor ran and found nothing.
    Entries from other extractors are kept. To store the result, rewrite the
    file with :func:`write_records`."""
    record = copy.deepcopy(record)
    marker = {"extractor": extractor, "extractor_version": extractor_version}
    listed = record.get("extractors", [])
    if not isinstance(listed, list):
        listed = []
    for index, entry in enumerate(listed):
        if isinstance(entry, dict) and entry.get("extractor") == extractor:
            listed[index] = marker
            break
    else:
        listed.append(marker)
    record["extractors"] = listed
    kept = [entry for entry in record.get("features", [])
            if not (isinstance(entry, dict) and entry.get("extractor") == extractor)]
    added = [
        {"name": name, "value": copy.deepcopy(value), "extractor": extractor,
         "extractor_version": extractor_version}
        for name, value in values.items()
    ]
    record["features"] = kept + added
    _raise_if_invalid(record)
    return record


# --- JSON Lines files ----------------------------------------------------------


@dataclass(frozen=True)
class LineProblem:
    """A line of a record file that is not a valid record."""

    line: int  # 1-based
    errors: Tuple[str, ...]


@dataclass(frozen=True)
class ReadResult:
    """What :func:`read_records` found in a record file.

    ``records`` holds every valid, newline-terminated record in file order.
    ``problems`` lists bad complete lines. ``truncated_tail`` is the last line
    when it has no closing newline (an interrupted write); it is never counted
    as a record, and a file with only that wrong is still ``ok``.
    """

    records: list
    problems: Tuple[LineProblem, ...]
    truncated_tail: Optional[LineProblem]

    @property
    def ok(self):
        return not self.problems


def dumps_record(record):
    """The record as the single line (without newline) that is written.

    Non-ASCII characters are escaped, so a line can only end at ``\\n`` in any
    reader. Raises :class:`RecordError` if the record is invalid.
    """
    _raise_if_invalid(record)
    return json.dumps(record, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":"))


def _ends_unterminated(path):
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            return False
        handle.seek(-1, os.SEEK_END)
        return handle.read(1) != b"\n"


def append_line(path, line):
    """Append ``line`` (bytes without a newline) to the JSON Lines file at
    ``path`` and flush it to disk before returning.

    Creates the file and its directory if needed. Refuses (``RecordError``) a
    file whose last line is unterminated: call :func:`repair_tail` first.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and _ends_unterminated(path):
        raise RecordError(f"{path.name}: the last line has no newline (an "
                          "interrupted write?); call repair_tail first")
    with open(path, "ab") as handle:
        handle.write(line + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_record(path, record):
    """Validate ``record`` and append it as one line to the file at ``path``.

    Creates the file and its directory if needed and flushes the line to disk
    before returning. A record counts as written only once its newline is on
    disk. Refuses (``RecordError``) an invalid record, or a file whose last
    line is unterminated: call :func:`repair_tail` first. One writer per file.
    """
    append_line(path, dumps_record(record).encode("ascii"))


def repair_tail(path):
    """Cut an unterminated last line from the file at ``path``.

    Returns the bytes removed, so the caller can log them, or None if the file
    already ended with a newline (or was empty).
    """
    path = Path(path)
    with open(path, "r+b") as handle:
        data = handle.read()
        if not data or data.endswith(b"\n"):
            return None
        keep = data.rfind(b"\n") + 1
        handle.truncate(keep)
        handle.flush()
        os.fsync(handle.fileno())
    return data[keep:]


def write_records(path, records, *, discard_problem_lines=False):
    """Replace the file at ``path`` with ``records``, atomically.

    For rewriting a file, such as after re-running an extractor over every
    record. All records are validated (and record ids checked for repeats)
    before anything is written. The new content goes to a temporary file in
    the same directory, is flushed to disk, then replaces the old file with
    ``os.replace``, so a crash leaves either the old file or the new one.

    If the existing file has bad lines or an unterminated last line, they are
    not in ``records`` and would be lost, so this raises :class:`RecordError`
    unless ``discard_problem_lines`` is true. One writer per file.
    """
    path = Path(path)
    records = list(records)
    errors, seen = [], {}
    for index, record in enumerate(records):
        errors += [f"records[{index}]: {message}"
                   for message in validate_record(record)]
        if isinstance(record, dict) and isinstance(record.get("record_id"), str):
            first = seen.setdefault(record["record_id"], index)
            if first != index:
                errors.append(f"records[{index}]: repeats record_id "
                              f"{record['record_id']} from records[{first}]")
    if errors:
        raise RecordError(errors)
    if path.exists() and not discard_problem_lines:
        existing = read_records(path)
        lost = list(existing.problems)
        if existing.truncated_tail:
            lost.append(existing.truncated_tail)
        if lost:
            lines = ", ".join(str(problem.line) for problem in lost)
            raise RecordError(f"{path.name}: lines {lines} are not valid records "
                              "and would be lost; fix them or pass "
                              "discard_problem_lines=True")
    data = b"".join((dumps_record(record) + "\n").encode("ascii")
                    for record in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _no_constant(name):
    raise ValueError(f"{name} is not allowed")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"repeated key {key!r}")
        result[key] = value
    return result


def parse_json(line):
    """Parse one line (bytes or text) of strict JSON; raise RecordError.

    Rejects text that is not UTF-8, NaN, Infinity and repeated keys.
    """
    try:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        return json.loads(line, parse_constant=_no_constant,
                          object_pairs_hook=_unique_pairs)
    except UnicodeDecodeError as error:
        raise RecordError(f"not UTF-8: {error}") from error
    except ValueError as error:  # includes json.JSONDecodeError
        raise RecordError(f"not valid JSON: {error}") from error


def parse_line(line):
    """Parse one line (bytes or text) into a record; raise RecordError.

    Rejects NaN and Infinity, repeated keys and invalid records.
    """
    record = parse_json(line)
    _raise_if_invalid(record)
    return record


def read_records(path):
    """Read and validate every line of a record file; return a :class:`ReadResult`.

    Raises OSError if the file cannot be read.
    """
    data = Path(path).read_bytes()
    lines = data.split(b"\n")
    tail = lines.pop()  # empty when the file ends with a newline
    records, problems, seen = [], [], {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            problems.append(LineProblem(number, ("blank line",)))
            continue
        try:
            record = parse_line(line)
        except RecordError as error:
            problems.append(LineProblem(number, error.errors))
            continue
        first = seen.setdefault(record["record_id"], number)
        if first != number:
            problems.append(LineProblem(
                number, (f"repeats record_id {record['record_id']} "
                         f"from line {first}",)))
            continue
        records.append(record)
    truncated = None
    if tail:
        truncated = LineProblem(len(lines) + 1,
                                ("unterminated last line (interrupted write?)",))
    return ReadResult(records, tuple(problems), truncated)


# --- Files stored beside a record --------------------------------------------------


def files_dir(jsonl_path, record_id):
    """The record's data directory: ``files/<record_id>/`` beside its JSONL file.

    Paths in a record's ``files`` and ``checks[].files`` are relative to it.
    """
    if not (isinstance(record_id, str) and _UUID.fullmatch(record_id)):
        raise RecordError(f"record_id: must be a lower-case UUID, not {record_id!r}")
    return Path(jsonl_path).parent / "files" / record_id


def _sha256_and_size(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def file_entry(directory, relative_path):
    """A ``files`` entry for the file at ``directory/relative_path``."""
    if not _is_relative_path(relative_path):
        raise RecordError(f"path {relative_path!r}: must be {PATH}")
    sha256, size = _sha256_and_size(Path(directory, *relative_path.split("/")))
    return {"path": relative_path, "sha256": sha256, "size": size}


def check_files(record, directory):
    """Compare a valid record's file entries with the files in ``directory``.

    Returns a list of problems (missing file, size or sha256 mismatch).
    """
    entries = [(f"files[{i}]", entry) for i, entry in enumerate(record["files"])]
    for c, check in enumerate(record["checks"]):
        entries += [(f"checks[{c}].files[{i}]", entry)
                    for i, entry in enumerate(check["files"])]
    problems = []
    for where, entry in entries:
        path = Path(directory, *entry["path"].split("/"))
        if not path.is_file():
            problems.append(f"{where}: {entry['path']} is missing")
            continue
        sha256, size = _sha256_and_size(path)
        if size != entry["size"]:
            problems.append(f"{where}: {entry['path']} size is {size}, "
                            f"record says {entry['size']}")
        elif sha256 != entry["sha256"]:
            problems.append(f"{where}: {entry['path']} sha256 does not match")
    return problems


# --- Command line ------------------------------------------------------------------


def main(argv=None):
    """Validate record files; with ``--files`` also check stored files."""
    args = list(sys.argv[1:] if argv is None else argv)
    with_files = "--files" in args
    paths = [arg for arg in args if arg != "--files"]
    if not paths:
        print("usage: python -m runner.record [--files] FILE.jsonl...")
        return 2
    failed = False
    for path in paths:
        try:
            result = read_records(path)
        except OSError as error:
            print(f"{path}: cannot read: {error}")
            failed = True
            continue
        for problem in result.problems:
            failed = True
            for message in problem.errors:
                print(f"{path}: line {problem.line}: {message}")
        if result.truncated_tail:
            print(f"{path}: line {result.truncated_tail.line}: "
                  f"{result.truncated_tail.errors[0]} (ignored)")
        if with_files:
            for record in result.records:
                directory = files_dir(path, record["record_id"])
                for message in check_files(record, directory):
                    failed = True
                    print(f"{path}: record {record['record_id']}: {message}")
        count = len(result.records)
        print(f"{path}: {count} valid record{'' if count == 1 else 's'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
