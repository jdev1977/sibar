"""Renders as ``render`` checks, in a run record or beside a directory."""

import json
from collections import Counter
from importlib.metadata import version as package_version
from pathlib import Path

from renderer import TOOL, TOOL_VERSION
from renderer.browser import BrowserUnavailable, Settings, render_page
from renderer.entry import find_entry
from runner.files import PREFIX
from runner.ledger import LedgerError, _lock, _unlock
from runner.record import (
    check_files, file_entry, files_dir, read_records, write_records,
)

CHECK = "render"
OUTPUT = "render"  # folder of the images, in a record's files directory
RENDERED_TYPES = ("website",)
RENDERED_STATUSES = ("ok", "truncated")
MAX_CANDIDATES = 20


class RenderRefused(Exception):
    """Nothing was rendered; the message says why."""


def _check(outcome, detail, files=()):
    return {"name": CHECK, "tool": TOOL, "tool_version": TOOL_VERSION,
            "outcome": outcome, "detail": detail, "files": list(files)}


def _settings_detail(settings):
    return {"clock": settings.clock.isoformat(), "timezone": settings.timezone,
            "locale": settings.locale, "settle_ms": settings.settle_ms,
            "timeout": settings.timeout, "max_height": settings.max_height,
            "memory_mb": settings.memory_mb}


def _variant_detail(variant, result):
    return {
        "outcome": result.outcome, "viewport": [variant.width, variant.height],
        "scale": variant.scale, "mobile": variant.mobile,
        "scheme": variant.scheme, "width": result.width, "height": result.height,
        "content_width": result.content_width,
        "content_height": result.content_height, "truncated": result.truncated,
        "error": result.error}


def _render_check(root, candidates_from, out, base, entry, settings, render):
    """Render the page under ``root`` into ``out`` and return the check entry,
    with file paths relative to ``base``."""
    detail = {"settings": _settings_detail(settings),
              "playwright": package_version("playwright")}
    chosen, candidates = find_entry(root, candidates_from)
    entry = entry or chosen
    detail["entry"] = entry
    detail["candidates"] = candidates[:MAX_CANDIDATES]
    detail["candidate_count"] = len(candidates)
    if entry is None:
        detail["error"] = "no HTML file"
        return _check("failed", detail)
    result = render(root, entry, out, settings)
    shown = {variant.name: variant for variant in settings.variants}
    detail.update(
        browser=result.browser_version, memory_limited=result.memory_limited,
        variants={r.name: _variant_detail(shown[r.name], r) for r in result.variants},
        blocked=result.blocked, blocked_dropped=result.blocked_dropped,
        missing=result.missing, dialogs=result.dialogs,
        dialog_count=result.dialog_count, popups=result.popups,
        downloads=result.downloads)
    prefix = out.relative_to(base).as_posix()
    files = [file_entry(base, r.file if prefix == "." else f"{prefix}/{r.file}")
             for r in result.variants if r.file]
    return _check(result.outcome, detail, files)


def _describe(error):
    """An error as text without local paths."""
    if isinstance(error, OSError) and error.strerror:
        return f"{type(error).__name__}: {error.strerror}"
    return f"{type(error).__name__}: {error}"[:300]


def _record_check(record, records_path, settings, render):
    directory = files_dir(records_path, record["record_id"])
    paths = [entry["path"] for entry in record["files"]]
    try:
        # Earlier renders are left out: this one replaces them.
        problems = check_files({**record, "checks": []}, directory)
        if problems:
            return _check("error", {"error": "; ".join(problems)[:1000]})
        if any(p.casefold().split("/")[0] == OUTPUT for p in paths):
            return _check("error", {"error": f"the record's own files use the "
                                             f"{OUTPUT}/ folder"})
        # The page sees the extracted files only, not other results.
        prefix = f"{PREFIX}/"
        if paths and all(p.startswith(prefix) for p in paths):
            root, listed = directory / PREFIX, [p[len(prefix):] for p in paths]
        else:
            root, listed = directory, paths
        return _render_check(root, listed, directory / OUTPUT, directory, None,
                             settings, render)
    except BrowserUnavailable:
        raise
    except Exception as error:  # one record must not end the batch
        return _check("error", {"error": _describe(error)})


def _wanted(record, record_ids):
    if record_ids:
        return record["record_id"] in record_ids
    return (record["project_type"] in RENDERED_TYPES
            and record["status"] in RENDERED_STATUSES)


def _done(record):
    return any(c["name"] == CHECK and c["outcome"] != "error"
               for c in record["checks"])


def render_file(records_path, settings=Settings(), record_ids=(), force=False,
                say=print, render=render_page):
    """Render the records of ``records_path`` and store each ``render`` check,
    rewriting the file after every record. Returns a count of the outcomes
    (and of ``skipped`` records, which already have a render).

    By default the ``website`` records with status ok or truncated are
    rendered; ``record_ids`` names others instead. A record whose render ended
    in ``error`` is tried again; ``force`` renders all of them again.
    """
    path = Path(records_path)
    if not path.is_file():
        raise RenderRefused(f"{path}: no such record file")
    try:
        # The runner's lock: one writer per record file.
        lock = _lock(path.with_name(path.name + ".lock"))
    except LedgerError:
        raise RenderRefused(
            f"{path}: the record file is in use by another run") from None
    try:
        found = read_records(path)
        bad = list(found.problems)
        if found.truncated_tail:
            bad.append(found.truncated_tail)
        if bad:
            raise RenderRefused(f"{path}: not rewriting it, as line {bad[0].line} "
                                f"is not a valid record: {bad[0].errors[0]}")
        records = found.records
        unknown = set(record_ids) - {r["record_id"] for r in records}
        if unknown:
            raise RenderRefused(f"{path}: no record {', '.join(sorted(unknown))}")
        counts = Counter()
        for index, record in enumerate(records):
            if not _wanted(record, record_ids):
                continue
            if not force and _done(record):
                counts["skipped"] += 1
                continue
            check = _record_check(record, path, settings, render)
            others = [c for c in record["checks"] if c["name"] != CHECK]
            records[index] = {**record, "checks": others + [check]}
            write_records(path, records)
            counts[check["outcome"]] += 1
            error = check["detail"].get("error")
            say(f"{record['record_id']}: {check['outcome']}"
                + (f" ({error})" if error else ""))
        return counts
    finally:
        _unlock(lock)


def render_directory(directory, out_dir, settings=Settings(), entry=None,
                     render=render_page):
    """Render the page in ``directory`` into ``out_dir``; write the ``render``
    check to ``out_dir/render.json`` and return it."""
    root, out = Path(directory).resolve(), Path(out_dir).resolve()
    if not root.is_dir():
        raise RenderRefused(f"{directory}: not a directory")
    if out == root or out.is_relative_to(root):
        raise RenderRefused(f"{out_dir}: the output may not be inside the page's "
                            "folder")
    if entry is not None:
        _, candidates = find_entry(root)
        if entry not in candidates:
            raise RenderRefused(f"entry {entry!r}: not an HTML file in the folder "
                                "(give a relative path using /)")
    out.mkdir(parents=True, exist_ok=True)
    check = _render_check(root, None, out, out, entry, settings, render)
    (out / "render.json").write_text(json.dumps(check, indent=2) + "\n",
                                     encoding="utf-8")
    return check
