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

``prepared``  the requests, their keys, attempts and ledger call ids, and the
              ledger file and batch; written before the ledger reservations
              (whose ids it names) and before anything is sent
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

``prepared`` also names the ledger file and ledger batch the job is reserved
in, and its call ids are chosen and written before any reservation is made:
a crash between the two leaves reservations the next run can find.

**The run list** (``<cache>.runs``, beside the cache) names every job log
that has used the cache. A request in flight in any of them is not sent
again by another run, whatever its ``--run``: it is collected by the run
that sent it. The run list is written only under the cache's lock.

**Reading only** (``read_only=True``, for the dry run): nothing is written,
and a cut last line is left on disk and skipped instead of repaired.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from runner.record import RecordError, append_line, parse_json, repair_tail, utc_now

SCHEMA_VERSION = 1


class StoreError(ValueError):
    """A cache or job log file is unreadable."""


def _read(path, read_only=False):
    path = Path(path)
    if not path.exists():
        return []
    data = path.read_bytes()
    if data[-1:] not in (b"", b"\n"):
        if read_only:
            data = data[:data.rfind(b"\n") + 1]  # skipped, the file left alone
        else:
            repair_tail(path)
            data = path.read_bytes()
    out = []
    for number, line in enumerate(data.split(b"\n"), start=1):
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


def _refuse_write(path, read_only):
    if read_only:
        raise StoreError(f"{Path(path).name}: opened for reading only")


class Cache:
    def __init__(self, path, read_only=False):
        self.path = Path(path)
        self.read_only = read_only
        self.runs_path = self.path.with_name(self.path.name + ".runs")
        self.entries = {}
        for entry in _read(self.path, read_only):
            self.entries[entry["key"]] = entry

    def get(self, key):
        return self.entries.get(key)

    def put(self, **entry):
        _refuse_write(self.path, self.read_only)
        written = _append(self.path, entry)
        self.entries[written["key"]] = written
        return written

    def runs(self):
        """The job logs that have used this cache (resolved paths)."""
        return [Path(e["job_log"]) for e in _read(self.runs_path, self.read_only)]

    def register(self, job_log):
        """Add a job log to the run list (once)."""
        _refuse_write(self.runs_path, self.read_only)
        job_log = Path(job_log).resolve()
        if job_log not in self.runs():
            _append(self.runs_path, {"job_log": str(job_log)})

    def in_flight_elsewhere(self, job_log):
        """``{cache key: job log}`` for requests in flight in the job logs of
        the run list other than ``job_log``."""
        own, out = Path(job_log).resolve(), {}
        for path in self.runs():
            if path == own or not path.exists():
                continue
            for key in JobLog(path, read_only=True).in_flight():
                out.setdefault(key, path)
        return out


@dataclass
class Job:
    submission: str
    requests: list                       # dicts: custom_id, key, record_id, attempt, call_id
    prepared_at: str
    ledger: str = None                   # the ledger file the job is reserved in
    ledger_batch: str = None             # and its ledger batch
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
    def __init__(self, path, read_only=False):
        self.path = Path(path)
        self.read_only = read_only
        self.jobs = {}
        for entry in _read(self.path, read_only):
            self._apply(entry)

    def _apply(self, entry):
        event, submission = entry["event"], entry["submission"]
        if event == "prepared":
            self.jobs[submission] = Job(submission, entry["requests"],
                                        entry["timestamp"], entry.get("ledger"),
                                        entry.get("ledger_batch"))
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
        _refuse_write(self.path, self.read_only)
        entry = _append(self.path, {"event": event, "submission": submission, **fields})
        self._apply(entry)
        return entry

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
