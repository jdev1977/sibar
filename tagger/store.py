"""The tagger's two files: the tag cache and a run's job log (T2.6).

Both are append-only JSON Lines, written with ``runner.record.append_line``
(flushed to disk before the call returns). An unterminated last line, left by
a crash, is cut when the file is opened, as the ledger does.

**The cache** (``data/tagger/cache.jsonl`` by default) holds one final answer
per cache key: the stored features, the evidence quotes and every attempt
(reply text, tokens, status). A later line for the same key replaces an
earlier one (only ``--retry-errors`` writes one). Tagging an output whose key
is in the cache sends nothing and stores the cached features: this is what
makes tagging the same output twice give the same tags. A live model would
not: see ``tagger/README.md``.

**The job log** (``<run folder>/jobs.jsonl``) records each job (one provider
batch) as it goes:

``prepared``  the requests, their keys, attempts and ledger call ids; written
              after the ledger reservations and before anything is sent
``sending``   written just before the create request leaves
``submitted`` the provider's job id (``reconciled`` when found afterwards)
``not_sent``  the create certainly made no job; its reservations are settled
              at zero
``result``    one per request once the job has ended: the outcome, settled in
              the ledger
``collected`` every result of the job is in
``abandoned`` a person declared an unresolved job dead (``--abandon``)

A job ``prepared`` without ``sending`` was never sent. A job ``sending``
without ``submitted`` or ``not_sent`` may exist at the provider: it blocks
new jobs until ``tagger/run.py`` finds it, or a person abandons it.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from runner.record import RecordError, append_line, parse_json, repair_tail, utc_now

SCHEMA_VERSION = 1


class StoreError(ValueError):
    """A cache or job log file is unreadable."""


def _read(path):
    path = Path(path)
    if not path.exists():
        return []
    if path.read_bytes()[-1:] not in (b"", b"\n"):
        repair_tail(path)
    out = []
    for number, line in enumerate(path.read_bytes().split(b"\n"), start=1):
        if not line.strip():
            continue
        try:
            entry = parse_json(line)
        except RecordError as error:
            raise StoreError(f"{path.name}: line {number}: {error}") from None
        if not isinstance(entry, dict) or entry.get("schema_version") != SCHEMA_VERSION:
            raise StoreError(f"{path.name}: line {number}: not a schema version "
                             f"{SCHEMA_VERSION} entry")
        out.append(entry)
    return out


def _append(path, entry):
    entry = {"schema_version": SCHEMA_VERSION, "timestamp": utc_now(), **entry}
    append_line(path, json.dumps(entry, ensure_ascii=True, allow_nan=False,
                                 separators=(",", ":")).encode("ascii"))
    return entry


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = {}
        for entry in _read(self.path):
            self.entries[entry["key"]] = entry

    def get(self, key):
        return self.entries.get(key)

    def put(self, **entry):
        written = _append(self.path, entry)
        self.entries[written["key"]] = written
        return written


@dataclass
class Job:
    submission: str
    requests: list                       # dicts: custom_id, key, record_id, attempt, call_id
    prepared_at: str
    sending_at: str = None
    batch_id: str = None
    reconciled: bool = False
    state: str = "prepared"              # prepared, sending, submitted, not_sent, collected, abandoned
    results: dict = field(default_factory=dict)   # custom_id -> result event

    @property
    def open(self):
        """Sent, or maybe sent, and not finished with."""
        return self.state in ("sending", "submitted")


class JobLog:
    def __init__(self, path):
        self.path = Path(path)
        self.jobs = {}
        for entry in _read(self.path):
            self._apply(entry)

    def _apply(self, entry):
        event, submission = entry["event"], entry["submission"]
        if event == "prepared":
            self.jobs[submission] = Job(submission, entry["requests"],
                                        entry["timestamp"])
            return
        job = self.jobs.get(submission)
        if job is None:
            raise StoreError(f"{self.path.name}: {event} for unknown job {submission}")
        if event == "sending":
            job.sending_at, job.state = entry["timestamp"], "sending"
        elif event == "submitted":
            job.batch_id, job.state = entry["batch_id"], "submitted"
            job.reconciled = bool(entry.get("reconciled"))
        elif event == "result":
            job.results[entry["custom_id"]] = entry
        elif event in ("not_sent", "collected", "abandoned"):
            job.state = event
        else:
            raise StoreError(f"{self.path.name}: unknown event {event!r}")

    def add(self, event, submission, **fields):
        entry = _append(self.path, {"event": event, "submission": submission, **fields})
        self._apply(entry)
        return entry

    def attempts(self, key):
        """Attempts made for a cache key (processed requests only)."""
        return sum(1 for job in self.jobs.values() for r in job.results.values()
                   if r["key"] == key and r["attempted"])

    def last_result(self, key):
        found = [r for job in self.jobs.values() for r in job.results.values()
                 if r["key"] == key and r["attempted"]]
        return max(found, key=lambda r: r["attempt"]) if found else None

    def in_flight(self):
        """Cache keys of requests in jobs that are open or never settled."""
        keys = set()
        for job in self.jobs.values():
            if job.open:
                keys.update(r["key"] for r in job.requests
                            if r["custom_id"] not in job.results)
        return keys

    def claimed_batches(self):
        return {job.batch_id for job in self.jobs.values() if job.batch_id}
