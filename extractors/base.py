"""The extractor interface: what an extractor is, what it reads and how it runs.

An **extractor** (:class:`Extractor`) has a name (a slug such as
``website.palette``), its own version, the project type it applies to, and a
function from :class:`Inputs` to a mapping of feature name to JSON value. The
mapping becomes the record's feature entries through
:func:`runner.record.with_features`, so every value carries the extractor's
name and version.

**Inputs** are the record (read-only) and the files stored beside it, read
once with size limits. Extractors never execute output code and never use the
network: they read bytes.

Every result has a ``status`` feature:

- ``ok``: the extractor read its input; empty lists, ``0``, ``false`` or
  ``"none"`` mean "looked, not present".
- ``partial``: as ``ok``, but some files were skipped (too large, too many,
  missing or changed); ``skipped_files`` gives how many.
- ``no-input``: there was nothing for this extractor to read (no HTML or CSS,
  say). Its other features are absent: "could not determine".
- ``error``: the extractor failed; ``error`` holds the exception type and
  message (local paths removed). Other extractors still run.

Within an ``ok`` result a feature value of ``null`` also means "could not
determine" for that one feature (for example a font given only through an
unresolved ``var()``). Values are sorted, so the same input gives
byte-identical features.
"""

import hashlib
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Mapping

from runner.files import PREFIX
from runner.record import _is_slug, _is_word, _json_problem, files_dir

MAX_FILES = 500
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000
STATUSES = ("ok", "partial", "no-input", "error")
MAX_ERROR = 300

# Local paths in error text: C:\..., \\server\..., or /... not inside a word.
_PATHS = re.compile(
    r"(?:(?<![\w])[A-Za-z]:[\\/]|\\\\|(?<![\w.~-])/(?=[A-Za-z]))[^\s'\"<>|]{0,400}")


@dataclass(frozen=True)
class InputFile:
    """One file of an output: its relative ``/`` path and its bytes."""

    path: str
    data: bytes

    @cached_property
    def text(self):
        """The file as text: UTF-8 (a byte-order mark dropped), with bad
        bytes replaced."""
        return self.data.decode("utf-8-sig", "replace")

    @property
    def suffix(self):
        """The lower-case extension without its dot, or ``""``."""
        name = self.path.rsplit("/", 1)[-1]
        stem, dot, ext = name.rpartition(".")
        return ext.lower() if dot and stem else ""


class Inputs:
    """What every extractor of one output reads.

    ``files`` are sorted by path; ``skipped`` lists ``(path, reason)`` for
    files not read. ``record`` is the run record, or None outside a record.
    Extractors must not change any of these. :meth:`cached` shares work
    (such as parsing HTML once) between the extractors of one output.
    """

    def __init__(self, files, skipped=(), record=None):
        self.files = tuple(sorted(files, key=lambda f: f.path))
        self.skipped = tuple(sorted(skipped))
        self.record = record
        self._cache = {}

    def cached(self, key, build):
        """``build()``, computed once per key for these inputs. If it raises,
        the error is raised again for every caller."""
        if key not in self._cache:
            try:
                self._cache[key] = (True, build())
            except Exception as error:  # noqa: BLE001 - re-raised per caller
                self._cache[key] = (False, error)
        ok, value = self._cache[key]
        if not ok:
            raise value
        return value

    @classmethod
    def _read(cls, root, paths, record=None, expected=None):
        files, skipped, total = [], [], 0
        inside = Path(root).resolve()
        for path in sorted(paths):
            if len(files) >= MAX_FILES:
                skipped.append((path, "too many files"))
                continue
            target = Path(root, *path.split("/"))
            try:
                if (target.is_symlink() or not target.is_file()
                        or not target.resolve().is_relative_to(inside)):
                    skipped.append((path, "missing"))
                    continue
                size = target.stat().st_size
                if size > MAX_FILE_BYTES:
                    skipped.append((path, "too large"))
                    continue
                if total + size > MAX_TOTAL_BYTES:
                    skipped.append((path, "total size limit"))
                    continue
                data = target.read_bytes()
            except OSError:
                skipped.append((path, "missing"))
                continue
            if expected and hashlib.sha256(data).hexdigest() != expected.get(path):
                skipped.append((path, "changed"))
                continue
            total += len(data)
            files.append(InputFile(path, data))
        return cls(files, skipped, record)

    @classmethod
    def from_directory(cls, directory, record=None):
        """The regular files under ``directory`` (symbolic links skipped)."""
        root = Path(directory)
        paths = [p.relative_to(root).as_posix() for p in root.rglob("*")
                 if not p.is_dir()]
        return cls._read(root, paths, record)

    @classmethod
    def from_record(cls, record, records_path):
        """The files listed in ``record["files"]``, read from its data
        directory and checked against their sha256. When every path starts
        with ``extracted/`` (the runner's folder), that prefix is dropped, so
        paths are as the output named them."""
        directory = files_dir(records_path, record["record_id"])
        entries = {entry["path"]: entry["sha256"] for entry in record["files"]}
        prefix = f"{PREFIX}/"
        if entries and all(path.startswith(prefix) for path in entries):
            directory = directory / PREFIX
            entries = {path[len(prefix):]: sha for path, sha in entries.items()}
        return cls._read(directory, list(entries), record, expected=entries)


@dataclass(frozen=True)
class Extractor:
    """A named, versioned function from :class:`Inputs` to feature values.

    ``extract`` returns a mapping of feature name (a slug) to a JSON value
    (text, number, true/false, null, lists, objects). Raise the version
    whenever the same input could give a different result.
    """

    name: str
    version: str
    project_type: str
    extract: Callable[[Inputs], Mapping[str, Any]] = field(repr=False)
    summary: str = ""

    def __post_init__(self):
        if not _is_slug(self.name):
            raise ValueError(f"extractor name {self.name!r} is not a slug")
        if not _is_word(self.version):
            raise ValueError(f"extractor version {self.version!r} has spaces")
        if not _is_slug(self.project_type):
            raise ValueError(f"project type {self.project_type!r} is not a slug")


def describe_error(error):
    """An exception as short text without local paths."""
    text = f"{type(error).__name__}: {error}"
    return _PATHS.sub("<path>", text)[:MAX_ERROR]


def _problems(values):
    if not isinstance(values, Mapping):
        return ["the result is not a mapping"]
    problems = []
    for name, value in values.items():
        if not _is_slug(name):
            problems.append(f"feature name {name!r} is not a slug")
        elif _json_problem(value, name):
            problems.append(f"feature {name!r} is not plain JSON")
    status = values.get("status", "ok")
    if status not in STATUSES or status == "error":
        problems.append(f"status {status!r} is not one of ok, partial, no-input")
    return problems


def run_extractor(extractor, inputs):
    """Run one extractor; return its feature values, sorted by name, with a
    ``status``. Never raises for a failure inside the extractor."""
    try:
        values = extractor.extract(inputs)
        problems = _problems(values)
        if problems:
            raise ValueError("; ".join(problems))
        values = dict(values)
    except Exception as error:  # noqa: BLE001 - one failure must not stop others
        return {"error": describe_error(error), "status": "error"}
    values.setdefault("status", "ok")
    if inputs.skipped:
        values["skipped_files"] = len(inputs.skipped)
        if values["status"] == "ok":
            values["status"] = "partial"
    return {name: values[name] for name in sorted(values)}


def run_extractors(extractors, inputs):
    """``{name: (version, values)}`` for each extractor, in the given order."""
    return {e.name: (e.version, run_extractor(e, inputs)) for e in extractors}
