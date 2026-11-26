"""The ``checker`` check entry of math and engineering run records."""

import hashlib
from collections import Counter
from pathlib import Path

from checker.answers import (EXTRACTED, SUPPLIED, Answers, AnswersError,
                             read_answers_file)
from checker.extract import extract
from checker.formulas import LEVELS, load_reference, reference_paths
from checker.grade import grade
from extractors.base import Inputs
from extractors.common.response import get_doc
from runner.ledger import LedgerError, _lock, _unlock
from runner.record import read_records, write_records

CHECK = "checker"
TOOL = "sibar-checker"
# Raise this whenever the same record and answers could give another result.
VERSION = "1"
TYPES = ("math", "engineering")
CHECKED_STATUSES = ("ok", "truncated")
DOCUMENTS = ("md", "txt")


class CheckRefused(Exception):
    """Nothing was checked; the message says why."""


class Reference:
    """A reference file and the hash of its bytes."""

    def __init__(self, path):
        self.data = load_reference(path)
        self.task = f"{path.parent.name}/{path.stem}"
        text = path.read_bytes().replace(b"\r\n", b"\n")
        self.sha256 = hashlib.sha256(text).hexdigest()


def references():
    """``{"type/task": Reference}`` for every reference file."""
    return {found.task: found for found in map(Reference, reference_paths())}


def evaluate_response(reference, level, text, supplied=None, truncated=False,
                      use_extractor=True):
    """The check detail for one response: the answers found in ``text`` with
    the ``supplied`` ones put over them, graded."""
    answers, sources = Answers(), []
    if use_extractor and text is not None:
        answers = extract(reference.data, level, text, truncated=truncated)
        sources.append(EXTRACTED)
    if supplied is not None:
        answers = answers.merged(supplied)
        sources.append(SUPPLIED)
    detail = {"task": reference.task,
              "prompt_set_version": reference.data["prompt_set_version"],
              "reference_sha256": reference.sha256, "answers_from": sources,
              **grade(reference.data, level, answers)}
    note = reference.data.get("study_data_note")
    if note:
        detail["study_data_note"] = note
    return detail


def response_text(record, records_path):
    """The reply, with any Markdown or text file of the output that holds
    something the reply does not."""
    doc = get_doc(Inputs.from_record(record, records_path))
    parts = [doc.text]
    for source in doc.files:
        suffix = source.name.rpartition(".")[2]
        if source.named and suffix in DOCUMENTS and source.text.strip() not in doc.text:
            parts.append(source.text)
    return "\n\n".join(parts), doc.truncated


def _check(outcome, detail):
    return {"name": CHECK, "tool": TOOL, "tool_version": VERSION, "outcome": outcome,
            "detail": detail, "files": []}


def _problem(record, found):
    key = f"{record['project_type']}/{record['task_id']}"
    reference = found.get(key)
    if reference is None:
        return None, f"no reference file for {key}"
    if record["level"] not in LEVELS:
        return None, "the record has no level"
    wanted = reference.data["prompt_set_version"]
    if record["prompt_set_version"] != wanted:
        return None, (f"the reference was solved from prompt set version {wanted}, "
                      f"not {record['prompt_set_version']}")
    return reference, None


def check_record(record, records_path, found, supplied=None, use_extractor=True):
    """The ``checker`` check entry of ``record``."""
    reference, reason = _problem(record, found)
    if reason:
        return _check("error", {"reason": reason})
    text, truncated = response_text(record, records_path)
    return _check("ok", evaluate_response(
        reference, record["level"], text, supplied,
        truncated=truncated or record["status"] == "truncated",
        use_extractor=use_extractor))


def _wanted(record, record_ids):
    if record["project_type"] not in TYPES:
        return False
    if record_ids:
        return record["record_id"] in record_ids
    return record["status"] in CHECKED_STATUSES


def _supplied(answers_path, wanted):
    """``{record_id: Answers}`` from an answers file, for the wanted records."""
    if answers_path is None:
        return {}
    entries = read_answers_file(answers_path)
    if None in entries:
        if len(entries) != 1 or len(wanted) != 1:
            raise CheckRefused("an answers entry without record_id needs exactly one "
                               "record: name it with --record-id")
        return {wanted[0]: entries[None]}
    unknown = sorted(set(entries) - set(wanted))
    if unknown:
        raise CheckRefused(f"the answers file names records that are not being "
                           f"checked: {', '.join(unknown[:5])}")
    return entries


def run_file(records_path, record_ids=(), answers_path=None, extract=True,
             say=lambda line: None):
    """Check the math and engineering records of ``records_path`` and rewrite
    it once, atomically. An earlier ``checker`` entry is replaced. Returns a
    count of the verdicts (and ``error`` for records that cannot be graded).

    By default every record with status ok or truncated is checked;
    ``record_ids`` names records instead. ``answers_path`` is an answers file
    whose values go over the ones found; ``extract`` False uses only those.
    """
    path = Path(records_path)
    if not path.is_file():
        raise CheckRefused(f"{path}: no such record file")
    try:
        lock = _lock(path.with_name(path.name + ".lock"))  # the runner's lock
    except LedgerError:
        raise CheckRefused(f"{path}: the record file is in use by another run") \
            from None
    try:
        read = read_records(path)
        bad = list(read.problems) + ([read.truncated_tail] if read.truncated_tail else [])
        if bad:
            raise CheckRefused(f"{path}: not rewriting it, as line {bad[0].line} is "
                               f"not a valid record: {bad[0].errors[0]}")
        records = read.records
        unknown = set(record_ids) - {r["record_id"] for r in records}
        if unknown:
            raise CheckRefused(f"{path}: no record {', '.join(sorted(unknown))}")
        wanted = [r["record_id"] for r in records if _wanted(r, record_ids)]
        supplied = _supplied(answers_path, wanted)
        found = references()
        counts = Counter()
        for index, record in enumerate(records):
            identifier = record["record_id"]
            if identifier not in wanted:
                continue
            try:
                check = check_record(record, path, found, supplied.get(identifier),
                                     use_extractor=extract)
            except AnswersError as error:
                raise CheckRefused(f"{identifier}: {error}") from None
            others = [c for c in record["checks"] if c["name"] != CHECK]
            records[index] = {**record, "checks": others + [check]}
            verdict = check["detail"].get("verdict", "error")
            counts[verdict] += 1
            reason = check["detail"].get("reason")
            say(f"{identifier}: {verdict}" + (f" ({reason})" if reason else ""))
        if counts:
            write_records(path, records)
        return counts
    finally:
        _unlock(lock)
