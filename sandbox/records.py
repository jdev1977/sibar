"""Sandbox runs as ``sandbox`` checks, in a run record or beside a folder."""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from runner.files import PREFIX
from runner.ledger import LedgerError, lock_file, unlock_file
from runner.record import check_files, files_dir, read_records, write_records
from sandbox import TOOL, TOOL_VERSION
from sandbox.run import Settings, check_outcome, run_folder

CHECK = "sandbox"
RUN_TYPES = ("pipeline", "math", "engineering")
RUN_STATUSES = ("ok", "truncated")


class RunRefused(Exception):
    """Nothing was run; the message says why."""


def make_check(detail):
    return {"name": CHECK, "tool": TOOL, "tool_version": TOOL_VERSION,
            "outcome": check_outcome(detail), "detail": detail, "files": []}


def _error(message):
    return {"result": "error", "reason": message[:1000]}


def _record_check(record, records_path, settings, run):
    directory = files_dir(records_path, record["record_id"])
    paths = [entry["path"] for entry in record["files"]]
    task = (record["project_type"], record["task_id"], record["level"] or "")
    try:
        # Earlier sandbox checks are left out: this one replaces them.
        problems = check_files({**record, "checks": []}, directory)
        if problems:
            return make_check(_error("; ".join(problems)))
        if not paths:
            return make_check({"result": "not-runnable", "reason": "the record has no files",
                               "files": 0})
        prefix = f"{PREFIX}/"
        if all(path.startswith(prefix) for path in paths):
            root, listed = directory / PREFIX, [p[len(prefix):] for p in paths]
        else:
            root, listed = directory, paths
        return make_check(run(root, listed, replace(settings, task=task)))
    except Exception as error:  # one record must not end the batch
        return make_check(_error(f"{type(error).__name__}: {error}"))


def _wanted(record, record_ids):
    if record_ids:
        return record["record_id"] in record_ids
    return record["project_type"] in RUN_TYPES and record["status"] in RUN_STATUSES


def _done(record):
    """A sandbox check that should not be redone without ``force``: any but
    one where the sandbox itself failed."""
    return any(check["name"] == CHECK and check["detail"].get("result") != "error"
               for check in record["checks"])


def run_file(records_path, settings=Settings(), record_ids=(), force=False, say=print,
             run=run_folder):
    """Run the records of ``records_path`` in the sandbox and store each
    ``sandbox`` check, rewriting the file after every record. Returns a count
    of the results (and of ``skipped`` records, which already have one).

    By default the pipeline, math and engineering records with status ok or
    truncated are run; ``record_ids`` names others instead. A record whose
    run ended in a sandbox error is run again; ``force`` runs all again."""
    path = Path(records_path)
    if not path.is_file():
        raise RunRefused(f"{path}: no such record file")
    try:
        lock = lock_file(path.with_name(path.name + ".lock"))  # the runner's lock
    except LedgerError:
        raise RunRefused(f"{path}: the record file is in use by another run") from None
    try:
        found = read_records(path)
        bad = list(found.problems)
        if found.truncated_tail:
            bad.append(found.truncated_tail)
        if bad:
            raise RunRefused(f"{path}: not rewriting it, as line {bad[0].line} is not a "
                             f"valid record: {bad[0].errors[0]}")
        records = found.records
        unknown = set(record_ids) - {r["record_id"] for r in records}
        if unknown:
            raise RunRefused(f"{path}: no record {', '.join(sorted(unknown))}")
        counts = Counter()
        for index, record in enumerate(records):
            if not _wanted(record, record_ids):
                continue
            if not force and _done(record):
                counts["skipped"] += 1
                continue
            check = _record_check(record, path, settings, run)
            others = [c for c in record["checks"] if c["name"] != CHECK]
            records[index] = {**record, "checks": others + [check]}
            write_records(path, records)
            result = check["detail"].get("result")
            cleanup = check["detail"].get("cleanup_error")
            counts["error" if cleanup else result] += 1
            reason = check["detail"].get("reason")
            say(f"{record['record_id']}: {result}" + (f" ({reason})" if reason else "")
                + (f"; cleanup failed: {cleanup}" if cleanup else ""))
        return counts
    finally:
        unlock_file(lock)


def run_directory(directory, out_file, settings=Settings(), run=run_folder):
    """Run the output in ``directory``; write the ``sandbox`` check to
    ``out_file`` (which may not be inside the folder) and return it."""
    root, out = Path(directory).resolve(), Path(out_file).resolve()
    if not root.is_dir():
        raise RunRefused(f"{directory}: not a directory")
    if out == root or out.is_relative_to(root):
        raise RunRefused(f"{out_file}: the result may not be inside the output's folder")
    check = make_check(run(root, None, settings))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(check, indent=2) + "\n", encoding="utf-8")
    return check
