"""Tagging runs: ``python -m tagger tag`` (T2.6).

    python -m tagger tag --records FILE... --type pipeline \\
        --tagger claude-haiku-5-5 --run cal-1 --dry-run
    python -m tagger tag ... --paid --batch-cap USD --total-cap USD [--wait]

Each invocation does what can be done now and stops; run it again to go on:

1. **Recover.** A job written ``prepared`` but never ``sending`` was never
   sent: its ledger reservations are settled at zero. A job ``sending`` with
   no provider id may exist: the provider's job list is searched (an OpenAI
   job by its metadata; an Anthropic job, which holds no metadata, by its
   size and creation time). One match is adopted and its result ids are
   checked when they come; none or several blocks the run until a person
   checks the provider's console and runs ``--abandon JOB``. So a job is never
   created twice.
2. **Collect.** Every open job is looked up; an ended one has its results
   read, each request settled in the ledger from the reported usage (errored,
   canceled and expired requests are not billed and settle at zero; a billed
   request without usage settles at its worst case), its reply checked, and
   its final features cached, or a retry queued.
3. **Submit.** Records with no cached answer and no request in flight are sent
   as one job (up to ``--max-requests``), after every request is reserved in
   the ledger at its worst case: the prompt estimate and the full output limit
   at the standard rate. Requests that do not fit under the caps are left for
   later; if none fits, the run stops with exit code 3.
4. **Write** a copy of the record files with the tags as features of
   ``rubric.<type>`` at version ``<rubric version>@<tagger id>``.

``--wait`` repeats 2 to 4 until nothing is left, polling every
``--poll-seconds``.

Exit codes: 0 every selected record is tagged; 1 records are still waiting (a
job in flight, a retry queued) or ended with ``status: error``; 2 refused; 3
the budget cap stops the next job; 4 blocked by a job that may exist; 130
interrupted.
"""

import os
import re
import time
import uuid
from decimal import Decimal
from pathlib import Path

from runner.ledger import (
    DEFAULT_PATH, BudgetExceeded, Ledger, LedgerError, Usage, _lock, _text,
    _unlock, call_cost, read_ledger,
)
from runner.models import ModelsError, load_models
from runner.record import RecordError, read_records, with_features, write_records
from runner.scrub import Scrubber
from tagger import answers
from tagger.backends import BackendError, Line, backend_for, parse_time
from tagger.models import (
    MODELS_PATH, TAGGERS_PATH, TaggersError, ledger_models, load_taggers,
    with_max_tokens,
)
from tagger.prompt import PromptError, build_request, canonical
from tagger.rubric import RubricError, load_checked
from tagger.store import Cache, JobLog, StoreError

ROOT = Path(__file__).resolve().parents[1]
TAGGER_DIR = ROOT / "data" / "tagger"
DEFAULT_CACHE = TAGGER_DIR / "cache.jsonl"
_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_KEY = re.compile(r"[\x21-\x7e]+")
EXIT_OK, EXIT_WAITING, EXIT_REFUSED, EXIT_BUDGET, EXIT_BLOCKED = 0, 1, 2, 3, 4
EXIT_INTERRUPTED = 130
BYTE_SHARE = Decimal("0.9")   # of a provider's job size limit
MAX_SENDS = 4                 # jobs one request may be in (two attempts, two lost)


class Refusal(Exception):
    """The command refuses to run; the message says why."""


class Blocked(Exception):
    """A job may exist at the provider and could not be found."""


class NoRoom(Exception):
    """The caps leave no room for the next request's worst case."""


def ledger_batch_id(run):
    """The ledger batch of a tagging run: its own, apart from generation."""
    return f"tag-{run}"


def select_records(records, rubric, statuses):
    """Records the run tags: of the rubric's type and tasks, with a status
    in ``statuses`` (default ``ok``)."""
    return [r for r in records if r["project_type"] == rubric.project_type
            and r["status"] in statuses and r["task_id"] in rubric.tasks
            and r["level"] is not None]


def usage_of(line):
    """What the ledger is told a request cost (None: its worst case)."""
    if not line.billed:
        return Usage(input=0, output=0)
    tokens = line.tokens
    if tokens is None or not tokens.complete:
        return None
    return Usage(input=tokens.input, output=tokens.output, reasoning=tokens.reasoning,
                 reasoning_in_output=True)


class Tagging:
    """One tagging run over a set of records, with its cache and job log."""

    def __init__(self, *, rubric, tagger, records, cache, jobs, out=print,
                 effort=None, statuses=("ok",), retry_errors=False):
        self.rubric, self.tagger, self.out = rubric, tagger, out
        self.cache, self.jobs, self.retry_errors = cache, jobs, retry_errors
        self.records = records
        self.requests, self.skipped = [], []
        for record in select_records(records, rubric, statuses):
            try:
                self.requests.append(build_request(rubric, tagger, record, effort))
            except PromptError as error:
                self.skipped.append(str(error))
        self.version = f"{rubric.version}@{tagger.id}"

    # --- state ------------------------------------------------------------------

    def final(self, key):
        """The cache entry that answers ``key``, or None."""
        entry = self.cache.get(key)
        if entry is None:
            return None
        if self.retry_errors and entry["features"].get("status") == "error" \
                and not entry.get("retried"):
            return None
        return entry

    def _since(self, key):
        entry = self.cache.get(key)
        return entry["timestamp"] if entry is not None else None

    def attempts(self, key):
        since = self._since(key)
        return sum(1 for job in self.jobs.jobs.values() for r in job.results.values()
                   if r["key"] == key and r["attempted"]
                   and (since is None or r["timestamp"] > since))

    def sends(self, key):
        """Jobs that have returned a result for ``key`` (processed or not)."""
        since = self._since(key)
        return sum(1 for job in self.jobs.jobs.values() for r in job.results.values()
                   if r["key"] == key and (since is None or r["timestamp"] > since))

    def pending(self):
        """Requests to send now, each with its attempt number."""
        in_flight = self.jobs.in_flight()
        out, seen = [], set()
        for request in self.requests:
            if request.key in seen or self.final(request.key) or request.key in in_flight:
                continue
            seen.add(request.key)  # two records with one request: send it once
            out.append((request, self.attempts(request.key) + 1))
        return out

    def counts(self):
        done = sum(1 for r in self.requests if self.final(r.key))
        in_flight = self.jobs.in_flight()
        flying = sum(1 for r in self.requests if not self.final(r.key)
                     and r.key in in_flight)
        return done, flying, len(self.requests) - done - flying

    def worst_case(self, request):
        return call_cost(self.tagger.model, request.prompt_tokens, self.tagger.max_tokens)

    # --- results ----------------------------------------------------------------

    def _settle(self, ledger, call_id, line):
        try:
            reservation = ledger.reopen(call_id)
        except LedgerError:
            return None  # settled already (a run that stopped after settling)
        return ledger.settle(reservation, usage_of(line), request_id=None)

    def record_result(self, job, request, line, ledger, scrub):
        tokens = line.tokens
        result = self.jobs.add(
            "result", job.submission, custom_id=request["custom_id"],
            key=request["key"], record_id=request["record_id"],
            attempt=request["attempt"], attempted=line.attempted, billed=line.billed,
            status=line.status, stop_reason=line.stop_reason,
            text=scrub.exact(line.text) if line.text is not None else None,
            tokens=None if tokens is None else {
                "input": tokens.input, "output": tokens.output,
                "reasoning": tokens.reasoning},
            error=scrub(line.error) if line.error else None,
            request_id=line.request_id, model_id_returned=line.model_id_returned,
            service_tier=line.service_tier)
        self._settle(ledger, request["call_id"], line)
        self.finish(request, result)

    def finish(self, request, result):
        """Cache the final features of a request, or leave it for a retry."""
        if not result["attempted"]:
            # Canceled, expired or never run: sent again in a later job, up
            # to MAX_SENDS jobs in all, so a job that never runs cannot loop.
            if self.sends(request["key"]) >= MAX_SENDS:
                self._cache(request, None, f"sent {MAX_SENDS} times without being "
                            f"processed (last: {result['error'] or result['status']})")
            return
        items = request["items"]
        parsed = None
        if result["status"] == "ok":
            parsed = answers.parse_reply(self.rubric, items, result["text"])
            if not answers.needs_retry(self.rubric, parsed):
                return self._cache(request, parsed)
        if request["attempt"] < answers.MAX_ATTEMPTS:
            return  # queued: pending() sends it again
        self._cache(request, parsed, result["error"] or result["status"])

    def _cache(self, request, parsed, failure=None):
        features = answers.stored_features(self.rubric, request["items"], parsed, failure)
        attempts = [{k: r[k] for k in ("submission", "custom_id", "attempt", "status",
                                       "stop_reason", "tokens", "error", "text")}
                    for job in self.jobs.jobs.values() for r in job.results.values()
                    if r["key"] == request["key"]]
        previous = self.cache.get(request["key"])
        self.cache.put(key=request["key"], tagger=self.tagger.id, rubric=self.rubric.name,
                       record_id=request["record_id"], features=features,
                       evidence=parsed.evidence if parsed else {}, attempts=attempts,
                       retried=bool(previous))

    # --- output -----------------------------------------------------------------

    def tagged_records(self):
        """Every input record, with its tags where an answer is final."""
        by_record = {r.record_id: r for r in self.requests}
        out = []
        for record in self.records:
            request = by_record.get(record["record_id"])
            entry = self.final(request.key) if request else None
            if entry is not None:
                record = with_features(record, self.rubric.extractor, self.version,
                                       entry["features"])
            out.append(record)
        return out


# --- the job cycle -------------------------------------------------------------------


class Cycle:
    """Recover, collect, submit and write, against a ledger and a backend."""

    def __init__(self, tagging, ledger, backend, scrub, *, out=print, max_requests=1000,
                 abandon=()):
        self.t, self.ledger, self.backend, self.scrub = tagging, ledger, backend, scrub
        self.out, self.max_requests, self.abandon = out, max_requests, set(abandon)

    def recover(self):
        jobs = self.t.jobs
        for submission in sorted(self.abandon):
            job = jobs.jobs.get(submission)
            if job is None or job.state not in ("sending", "submitted"):
                raise Refusal(f"--abandon {submission}: no such open job in this run")
            jobs.add("abandoned", submission)
            self.out(f"Job {submission} abandoned: its requests may be sent again; "
                     "its reservations stay in the ledger at their worst case.")
        for job in list(jobs.jobs.values()):
            if job.state == "prepared":
                for request in job.requests:
                    self.t._settle(self.ledger, request["call_id"],
                                   Line(request["custom_id"], False, False, "not_run"))
                jobs.add("not_sent", job.submission,
                         error="the run stopped before the job was sent")
            elif job.state == "sending":
                sent_at = parse_time(job.sending_at)
                found = [b for b in self.backend.find(job.submission, len(job.requests),
                                                      sent_at)
                         if b not in jobs.claimed_batches()]
                if len(found) == 1:
                    jobs.add("submitted", job.submission, batch_id=found[0], reconciled=True)
                    self.out(f"Job {job.submission}: found at the provider as {found[0]}.")
                    continue
                raise Blocked(
                    f"job {job.submission} ({len(job.requests)} requests, sent at "
                    f"{job.sending_at}) may exist at the provider, and "
                    f"{'no' if not found else len(found)} matching job was found. "
                    "Check the provider's console. If it exists, wait and run again; "
                    f"if it does not, run again with --abandon {job.submission}.")

    def collect(self):
        for job in list(self.t.jobs.jobs.values()):
            if job.state != "submitted":
                continue
            batch = self.backend.retrieve(job.batch_id)
            if not self.backend.ended(batch):
                self.out(f"Job {job.submission} ({job.batch_id}): "
                         f"{self.backend.describe(batch)}")
                continue
            never_ran = self.backend.never_ran(batch)
            lines = {} if never_ran else {line.custom_id: line
                                          for line in self.backend.results(batch)}
            ours = {r["custom_id"] for r in job.requests}
            strange = set(lines) - ours
            if strange:
                raise Blocked(f"job {job.submission}: provider job {job.batch_id} has "
                              f"results this run did not send ({len(strange)}); it is "
                              "not this run's job. Nothing was settled.")
            for request in job.requests:
                if request["custom_id"] in job.results:
                    # Recorded by a run that stopped before the job was done.
                    result = job.results[request["custom_id"]]
                    self.t._settle(self.ledger, request["call_id"], _line_of(result))
                    if not self.t.final(request["key"]):
                        self.t.finish(request, result)
                    continue
                line = lines.get(request["custom_id"]) or Line(
                    request["custom_id"], False, not never_ran, "not_run",
                    error="no result line" if not never_ran else "the job never ran")
                self.t.record_result(job, request, line, self.ledger, self.scrub)
            self.t.jobs.add("collected", job.submission)
            self.out(f"Job {job.submission} ({job.batch_id}) collected.")

    def submit_one(self):
        """Send one job of pending requests; return how many were sent."""
        pending = self.t.pending()
        if not pending:
            return 0
        chosen, size = [], 0
        limit = min(self.max_requests, self.backend.max_requests)
        for request, attempt in pending[:limit]:
            bytes_ = len(canonical(request.params)) + 200
            if size + bytes_ > self.backend.max_bytes * BYTE_SHARE:
                break
            chosen.append((request, attempt))
            size += bytes_
        room, fitting, total = self.ledger.remaining_usd, [], Decimal(0)
        for request, attempt in chosen:
            worst = self.t.worst_case(request)
            if total + worst > room:
                break
            fitting.append((request, attempt))
            total += worst
        if not chosen:
            raise Refusal("one request is larger than the provider's job size limit")
        if not fitting:
            raise NoRoom(f"${_text(room)} left under the caps; the next request "
                         f"could cost ${_text(self.t.worst_case(chosen[0][0]))}")
        submission = "s" + uuid.uuid4().hex[:12]
        entries, reservations = [], []
        try:
            for index, (request, attempt) in enumerate(fitting):
                reservation = self.ledger.reserve(
                    model_id=self.t.tagger.id, record_id=request.record_id,
                    prompt_tokens=request.prompt_tokens,
                    max_output_tokens=self.t.tagger.max_tokens)
                reservations.append(reservation)
                entries.append({"custom_id": f"{submission}-{index}", "key": request.key,
                                "record_id": request.record_id, "attempt": attempt,
                                "items": list(request.items),
                                "call_id": reservation.call_id})
        except BudgetExceeded:
            for reservation in reservations:  # nothing was sent
                self.ledger.settle(reservation, Usage(input=0, output=0))
            raise
        jobs = self.t.jobs
        jobs.add("prepared", submission, requests=entries)
        jobs.add("sending", submission)
        try:
            batch = self.backend.create(submission, [
                (entry["custom_id"], request.params)
                for entry, (request, _) in zip(entries, fitting)])
        except BackendError as error:
            if error.ambiguous:
                raise Blocked(f"job {submission}: {error}. Run again: the job is "
                              "looked for before anything else is sent.") from None
            for reservation in reservations:
                self.ledger.settle(reservation, Usage(input=0, output=0))
            jobs.add("not_sent", submission, error=str(error))
            raise
        if not isinstance(batch, dict) or not isinstance(batch.get("id"), str):
            raise Blocked(f"job {submission}: the provider's answer has no job id")
        jobs.add("submitted", submission, batch_id=batch["id"])
        self.out(f"Job {submission} sent as {batch['id']}: {len(fitting)} requests, "
                 f"${_text(total)} reserved at standard rates.")
        if len(fitting) < len(chosen):
            raise NoRoom(f"{len(chosen) - len(fitting)} requests did not fit under "
                         "the caps and wait for more room")
        return len(fitting)


def _line_of(result):
    from runner.providers.base import Tokens
    tokens = result.get("tokens")
    return Line(result["custom_id"], result["attempted"], result["billed"],
                result["status"],
                tokens=Tokens(**tokens) if tokens else None)


# --- command line --------------------------------------------------------------------


def add_arguments(parser):
    parser.add_argument("--records", nargs="+", required=True, metavar="FILE",
                        help="run record files (JSON Lines)")
    parser.add_argument("--type", required=True, dest="project_type",
                        help="project type: the rubric rubrics/<type>.v<N>.yaml")
    parser.add_argument("--rubric-version", default="1")
    parser.add_argument("--tagger", required=True, help="a tagger id from taggers.yaml")
    parser.add_argument("--run", required=True,
                        help="name of this tagging run (its folder and ledger batch)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="show what would be sent and its worst case; send nothing")
    mode.add_argument("--paid", action="store_true", help="send requests (spends money)")
    parser.add_argument("--batch-cap", metavar="USD",
                        help="limit for this run's ledger batch (required with --paid)")
    parser.add_argument("--total-cap", metavar="USD",
                        help="limit for the whole ledger (required with --paid)")
    parser.add_argument("--ledger", metavar="PATH", help=f"default {DEFAULT_PATH}")
    parser.add_argument("--cache", metavar="PATH", help=f"default {DEFAULT_CACHE}")
    parser.add_argument("--run-dir", metavar="PATH",
                        help="default data/tagger/<run>/")
    parser.add_argument("--out", metavar="PATH",
                        help="tagged copy of the records (default "
                             "<run dir>/records.<tagger>.jsonl)")
    parser.add_argument("--statuses", default="ok",
                        help="record statuses to tag, comma separated (default ok)")
    parser.add_argument("--max-requests", type=int, default=1000,
                        help="requests per job (default 1000)")
    parser.add_argument("--max-tokens", type=int,
                        help="output limit per request (default from taggers.yaml)")
    parser.add_argument("--effort", choices=("low", "medium", "high"),
                        help="reasoning effort sent (default: the model's own)")
    parser.add_argument("--wait", action="store_true",
                        help="keep polling until every record is tagged")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--retry-errors", action="store_true",
                        help="tag again the outputs whose cached answer is an error")
    parser.add_argument("--abandon", action="append", default=[], metavar="JOB",
                        help="declare a job that may exist dead (after checking the "
                             "provider's console)")
    parser.add_argument("--show-prompt", metavar="RECORD_ID",
                        help="with --dry-run: print the request for one record")
    parser.add_argument("--taggers-file", default=str(TAGGERS_PATH))
    parser.add_argument("--models-file", default=str(MODELS_PATH))


def _load_records(paths):
    records, seen = [], set()
    for path in paths:
        found = read_records(path)
        if found.problems:
            problem = found.problems[0]
            raise Refusal(f"{path}: line {problem.line} is not a valid record: "
                          f"{'; '.join(problem.errors)}")
        for record in found.records:
            if record["record_id"] in seen:
                raise Refusal(f"record {record['record_id']} is in two files")
            seen.add(record["record_id"])
        records.extend(found.records)
    return records


def _spent(ledger_path, batch_id):
    if not Path(ledger_path).exists():
        return None
    calls = {e["call_id"]: e for e in read_ledger(ledger_path).entries}
    return sum((Decimal(e["cost_usd"]) for e in calls.values()
                if e["batch_id"] == batch_id), Decimal(0))


def _dry_run(tagging, args, taggers, environ, ledger_path, out):
    tagger = tagging.tagger
    out("Dry run: no request is sent.")
    out(f"Tagger list: {args.taggers_file} (confirmed_by_human: "
        f"{'true' if taggers.confirmed_by_human else 'false; a paid run would be refused'})")
    if args.show_prompt:
        request = next((r for r in tagging.requests if r.record_id == args.show_prompt),
                       None)
        if request is None:
            raise Refusal(f"--show-prompt: record {args.show_prompt} is not tagged here")
        out(canonical(request.params))
    done, flying, todo = tagging.counts()
    out(f"{len(tagging.requests)} records to tag with {tagger.id}: {done} answered "
        f"(cache), {flying} in a job, {todo} to send.")
    pending = tagging.pending()
    worst = sum((tagging.worst_case(r) for r, _ in pending), Decimal(0))
    out(f"Worst case for {len(pending)} requests: ${_text(worst)} at standard rates "
        f"(each reserved in full: prompt estimate and {tagger.max_tokens} output "
        f"tokens). At the batch price (x{tagger.batch_discount}) at most "
        f"${_text(worst * tagger.batch_discount)}. A faulty answer is asked once more, "
        "which can add as much again for that request.")
    spent = _spent(ledger_path, ledger_batch_id(args.run))
    out(f"Ledger batch {ledger_batch_id(args.run)}: "
        + (f"${_text(spent)} spent or reserved." if spent is not None else "new."))
    if not (environ.get(tagger.model.api_key_env) or "").strip():
        out(f"No key in {tagger.model.api_key_env} (a paid run would refuse).")
    for note in tagging.skipped:
        out(f"skipped: {note}")
    return EXIT_OK


def _paid(tagging, args, taggers, model_list, environ, ledger_path, out, transport,
          sleep):
    tagger = tagging.tagger
    if not taggers.confirmed_by_human:
        raise Refusal(f"{args.taggers_file} has confirmed_by_human: false. A person "
                      "must check the tagger list and set it to true before a paid run.")
    for option, value in (("--batch-cap", args.batch_cap), ("--total-cap", args.total_cap)):
        if value is None:
            raise Refusal(f"a paid run needs {option} (in US dollars)")
    key = (environ.get(tagger.model.api_key_env) or "").strip()
    if not key:
        raise Refusal(f"no key in the environment variable {tagger.model.api_key_env}")
    if not _KEY.fullmatch(key):
        raise Refusal(f"{tagger.model.api_key_env} holds characters a key cannot have "
                      "(value not shown)")
    scrub = Scrubber([key])
    if transport is None:
        from runner.transport import UrllibTransport
        transport = UrllibTransport(read_timeout=600.0, total_timeout=3600.0)
    backend = backend_for(tagger.provider, transport, key, scrub, sleep=sleep,
                          workspace_id=(environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()
                          or None)
    with Ledger(ledger_path, batch_id=ledger_batch_id(args.run),
                batch_cap_usd=args.batch_cap, total_cap_usd=args.total_cap,
                models=ledger_models(model_list, taggers)) as ledger:
        cycle = Cycle(tagging, ledger, backend, scrub, out=out,
                      max_requests=args.max_requests, abandon=args.abandon)
        status = EXIT_OK
        try:
            cycle.recover()
            while True:
                cycle.collect()
                try:
                    while cycle.submit_one():
                        pass
                except (BudgetExceeded, NoRoom) as error:
                    out(f"budget: {error}")
                    status = EXIT_BUDGET
                _write(tagging, args, out)
                done, flying, todo = tagging.counts()
                out(f"{done} of {len(tagging.requests)} records tagged; {flying} in a "
                    f"job; {todo} waiting. Ledger batch {ledger.batch_id}: "
                    f"${_text(ledger.spent_usd)} spent or reserved.")
                if not args.wait or status == EXIT_BUDGET or (not flying and not todo):
                    break
                sleep(args.poll_seconds)
        except Blocked as error:
            out(f"blocked: {error}")
            _write(tagging, args, out)
            return EXIT_BLOCKED
        except BackendError as error:
            out(f"stopped: {error}")
            _write(tagging, args, out)
            return EXIT_REFUSED if error.stop else EXIT_WAITING
    if status != EXIT_OK:
        return status
    done, flying, todo = tagging.counts()
    errors = sum(1 for r in tagging.requests if (tagging.final(r.key) or {}).get(
        "features", {}).get("status") == "error")
    return EXIT_OK if done == len(tagging.requests) and not errors else EXIT_WAITING


def _write(tagging, args, out):
    write_records(args.out, tagging.tagged_records())
    out(f"Tagged records: {args.out}")


def run_tag(args, *, environ=None, out=print, transport=None, sleep=time.sleep):
    environ = os.environ if environ is None else environ
    try:
        if not _RUN.fullmatch(args.run):
            raise Refusal("--run must be letters, digits, '.', '_' or '-' (it names "
                          "a folder), starting with a letter or digit")
        if args.max_requests < 1:
            raise Refusal("--max-requests must be at least 1")
        if not 0 < args.poll_seconds < float("inf"):
            raise Refusal("--poll-seconds must be above 0")
        model_list = load_models(args.models_file)
        taggers = load_taggers(args.taggers_file, model_list)
        tagger = taggers.get(args.tagger)
        if args.max_tokens is not None:
            tagger = with_max_tokens(tagger, args.max_tokens)
        rubric = load_checked(args.project_type, args.rubric_version)
        statuses = tuple(s.strip() for s in args.statuses.split(",") if s.strip())
        records = _load_records(args.records)
        run_dir = Path(args.run_dir) if args.run_dir else TAGGER_DIR / args.run
        args.out = Path(args.out) if args.out else run_dir / f"records.{tagger.id}.jsonl"
        cache_path = Path(args.cache) if args.cache else DEFAULT_CACHE
        ledger_path = Path(args.ledger) if args.ledger else DEFAULT_PATH
        out(f"Rubric {rubric.name}; tagger {tagger.id}; run folder {run_dir}; "
            f"cache {cache_path}; ledger {ledger_path}")
        if args.dry_run:
            tagging = Tagging(rubric=rubric, tagger=tagger, records=records,
                              cache=Cache(cache_path), jobs=JobLog(run_dir / "jobs.jsonl"),
                              out=out, effort=args.effort, statuses=statuses,
                              retry_errors=args.retry_errors)
            return _dry_run(tagging, args, taggers, environ, ledger_path, out)
        run_dir.mkdir(parents=True, exist_ok=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        locks = []
        try:
            for path in (run_dir / "jobs.jsonl.lock", cache_path.with_name(
                    cache_path.name + ".lock")):
                try:
                    locks.append(_lock(path))
                except LedgerError:
                    raise Refusal(f"{path.name}: in use by another tagging run") from None
            tagging = Tagging(rubric=rubric, tagger=tagger, records=records,
                              cache=Cache(cache_path), jobs=JobLog(run_dir / "jobs.jsonl"),
                              out=out, effort=args.effort, statuses=statuses,
                              retry_errors=args.retry_errors)
            for note in tagging.skipped:
                out(f"skipped: {note}")
            return _paid(tagging, args, taggers, model_list, environ, ledger_path, out,
                         transport, sleep)
        finally:
            for handle in locks:
                _unlock(handle)
    except (Refusal, TaggersError, ModelsError, RubricError, RecordError, StoreError,
            LedgerError, OSError) as error:
        out(f"refused: {error}")
        return EXIT_REFUSED
    except KeyboardInterrupt:
        out("interrupted")
        return EXIT_INTERRUPTED

