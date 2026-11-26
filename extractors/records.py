"""Running extractors over the records of a record file."""

from collections import Counter
from pathlib import Path

from extractors.base import Inputs, run_extractors
from extractors.registry import by_name, extractors_for
from runner.ledger import LedgerError, _lock, _unlock
from runner.record import read_records, with_features, write_records

EXTRACTED_STATUSES = ("ok", "truncated")


class ExtractRefused(Exception):
    """Nothing was extracted; the message says why."""


def extract_record(record, records_path, extractors):
    """A copy of ``record`` with the features of each extractor in
    ``extractors`` added (replacing that extractor's earlier entries)."""
    inputs = Inputs.from_record(record, records_path)
    for name, (version, values) in run_extractors(extractors, inputs).items():
        record = with_features(record, name, version, values)
    return record


def _chosen(only):
    if not only:
        return None
    known = by_name()
    unknown = sorted(set(only) - set(known))
    if unknown:
        raise ExtractRefused(f"no extractor named {', '.join(unknown)}")
    return [known[name] for name in known if name in set(only)]


def extract_file(records_path, record_ids=(), only=(), say=print):
    """Run the extractors over the records of ``records_path`` and rewrite it
    once, atomically. Returns counts: ``records`` processed and ``error``
    (extractor runs that failed).

    By default every record with status ok or truncated whose project type
    has extractors is processed; ``record_ids`` names records instead.
    ``only`` limits the run to the named extractors.
    """
    path = Path(records_path)
    if not path.is_file():
        raise ExtractRefused(f"{path}: no such record file")
    chosen = _chosen(only)
    try:
        lock = _lock(path.with_name(path.name + ".lock"))
    except LedgerError:
        raise ExtractRefused(f"{path}: the record file is in use by another run") \
            from None
    try:
        found = read_records(path)
        bad = list(found.problems) + ([found.truncated_tail]
                                      if found.truncated_tail else [])
        if bad:
            raise ExtractRefused(f"{path}: not rewriting it, as line {bad[0].line} "
                                 f"is not a valid record: {bad[0].errors[0]}")
        records = found.records
        unknown = set(record_ids) - {r["record_id"] for r in records}
        if unknown:
            raise ExtractRefused(f"{path}: no record {', '.join(sorted(unknown))}")
        counts = Counter(records=0, error=0)
        for index, record in enumerate(records):
            if record_ids:
                if record["record_id"] not in record_ids:
                    continue
            elif record["status"] not in EXTRACTED_STATUSES:
                continue
            extractors = [e for e in (chosen or extractors_for(record["project_type"]))
                          if e.project_type == record["project_type"]]
            if not extractors:
                continue
            records[index] = extract_record(record, path, extractors)
            counts["records"] += 1
            failed = sorted(
                f["extractor"] for f in records[index]["features"]
                if f["name"] == "status" and f["value"] == "error"
                and f["extractor"] in {e.name for e in extractors})
            counts["error"] += len(failed)
            if failed:
                say(f"{record['record_id']}: error in {', '.join(failed)}")
        write_records(path, records)
        return counts
    finally:
        _unlock(lock)
