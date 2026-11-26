"""The generation run loop (T0.5): one call per (prompt, model, run).

For each planned cell (task, level, wording, run index, model) the loop sends
the prompt with no system prompt and default settings, and writes one run
record per attempt. Every attempt is reserved in the cost ledger before it is
sent and settled after, so the budget cap holds across retries and crashes.

Rules (documented in ``docs/runner.md``):

- Resume: a cell is done when the record file holds a record for it whose
  status is not in ``rerun_statuses`` (by default only ``failed`` cells run
  again; refused and truncated ones count as done).
- Retries: only results the adapter marks retryable, with backoff, up to the
  policy's attempt limit, each attempt reserved separately.
- Billing: reported tokens when the provider gave them; nothing when the
  request never left the machine; otherwise the worst case.
- Stops: a budget refusal, a ledger failure or a call that cost more than its
  reservation stops the run; an account error stops calls to that provider; an
  error that would repeat for every prompt stops calls to that model.
"""

import dataclasses
import random
import shutil
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from runner.files import save_files
from runner.ledger import BudgetExceeded, LedgerError, Usage, estimate_prompt_tokens
from runner.providers import adapter_for
from runner.providers.base import ParseError, Result
from runner.ratelimit import RateLimiter
from runner.record import (
    LEVELS, WORDINGS, CellKey, RecordError, append_record, build_record,
    cell_key, files_dir, read_records, repair_tail, utc_now,
)
from runner.retry import RetryPolicy
from runner.scrub import Scrubber
from runner.transport import NotSentError, SendError, TotalTimeoutError

DEFAULT_RERUN = ("failed",)
# HTTP 429 answers in a row from one provider, across cells, before it is
# stopped for the run: a daily quota or billing limit answers 429 to every
# request, and each one is charged at the worst case.
DEFAULT_MAX_CONSECUTIVE_429 = 6


class RunError(Exception):
    """The run cannot start: bad input files or settings. Nothing was sent."""


@dataclass(frozen=True)
class Cell:
    """One grid cell: a prompt variant sent to one model for one run."""

    task: object  # runner.prompts.PromptTask
    level: str
    wording: str
    run_index: int
    model: object  # runner.models.Model

    @property
    def prompt_text(self):
        return self.task.text(self.level, self.wording)

    def key(self, batch_id):
        return CellKey(batch_id, self.task.project_type, self.task.task_id,
                       self.task.prompt_set_version, self.level, self.wording,
                       self.model.id, "api", self.run_index)

    def label(self):
        return (f"{self.model.id} {self.task.project_type}/{self.task.task_id} "
                f"{self.level}{self.wording} run {self.run_index}")


def plan_cells(tasks, models, runs, levels=LEVELS, wordings=WORDINGS):
    """Every cell, prompt by prompt: each prompt and run goes to every model
    before the next."""
    if type(runs) is not int or runs < 1:
        raise RunError("the number of runs must be a whole number of at least 1")
    cells = []
    for task in tasks:
        for level, wording, _ in task.variants():
            if level not in levels or wording not in wordings:
                continue
            for run_index in range(1, runs + 1):
                cells.extend(Cell(task, level, wording, run_index, model)
                             for model in models)
    return cells


def pending_cells(cells, records_path, batch_id, rerun_statuses=DEFAULT_RERUN,
                  *, repair=True, out=print):
    """(cells still to run, number already done) given the record file.

    Cuts an unfinished last line first when ``repair`` is true. Raises
    :class:`RunError` if the file has bad lines, or if a record for a planned
    cell holds different prompt text under the same prompt-set version.
    """
    path = Path(records_path)
    if not path.exists():
        return list(cells), 0
    found = read_records(path)
    if found.problems:
        listed = "; ".join(f"line {p.line}: {', '.join(p.errors)}"
                           for p in found.problems[:5])
        raise RunError(f"{path}: the record file has bad lines, so finished cells "
                       f"are unknown. Fix or move the file. {listed}")
    if found.truncated_tail is not None:
        if repair:
            removed = repair_tail(path)
            out(f"{path}: removed an unfinished last line ({len(removed or b'')} "
                "bytes) left by an interrupted run; that cell runs again")
        else:
            out(f"{path}: the last line is unfinished (an interrupted run); a "
                "paid run will remove it")
    planned = {cell.key(batch_id): cell for cell in cells}
    done = set()
    for record in found.records:
        key = cell_key(record)
        cell = planned.get(key)
        if cell is None:
            continue
        if record["prompt_text"] != cell.prompt_text:
            raise RunError(
                f"{path}: record {record['record_id']} for {cell.label()} has "
                "different prompt text under the same prompt_set_version "
                f"{cell.task.prompt_set_version!r}; raise prompt_set_version in "
                f"{cell.task.path.name} after changing a prompt")
        if record["status"] not in rerun_statuses:
            done.add(key)
    todo = [cell for cell in cells if cell.key(batch_id) not in done]
    return todo, len(cells) - len(todo)


@dataclass
class Summary:
    cells: int = 0  # cells this run set out to complete
    finished: Counter = field(default_factory=Counter)  # last status per cell
    attempts: int = 0  # requests reserved (and so sent or tried)
    skipped: int = 0  # cells not tried: their model or provider was stopped
    not_started: int = 0  # cells not reached because the run stopped
    stopped: Optional[str] = None  # budget, ledger, over_reservation, error,
    stop_message: Optional[str] = None  # interrupted


class Runner:
    """Runs cells against the providers through ``transport``.

    ``keys`` maps environment variable names (``api_key_env`` in models.yaml)
    to keys. ``ledger`` is an open :class:`runner.ledger.Ledger`. ``rpm`` maps
    a provider to its requests-per-minute limit (``None``: no limit, for
    tests). ``sleep`` waits between retries (default: an interruptible wait).
    """

    def __init__(self, *, batch_id, records_path, ledger, transport, keys,
                 retry=None, rpm=None, workers=1, rerun_statuses=DEFAULT_RERUN,
                 adapters=None, sleep=None, rng=None, out=print,
                 anthropic_workspace_id=None,
                 max_consecutive_429=DEFAULT_MAX_CONSECUTIVE_429):
        if type(workers) is not int or workers < 1:
            raise RunError("workers must be a whole number of at least 1")
        if type(max_consecutive_429) is not int or max_consecutive_429 < 1:
            raise RunError("max_consecutive_429 must be a whole number of at least 1")
        self.max_consecutive_429 = max_consecutive_429
        self._consecutive_429 = Counter()
        self.batch_id = batch_id
        self.records_path = Path(records_path)
        self.ledger = ledger
        self.transport = transport
        self.keys = dict(keys)
        self.retry = retry or RetryPolicy()
        self.workers = workers
        self.rerun_statuses = tuple(rerun_statuses)
        self._adapters = dict(adapters or {})
        self._anthropic_workspace_id = anthropic_workspace_id
        self._scrub = Scrubber(value for value in self.keys.values() if value)
        self._stop_event = threading.Event()
        self._sleep = sleep or self._wait
        self._crash = None
        self._rng = rng or random.Random()
        self._out = out
        self._lock = threading.Lock()  # summary, stops, queue, output
        self._write_lock = threading.Lock()  # the record file
        self._limiters = {}
        if rpm is not None:
            for provider, per_minute in rpm.items():
                self._limiters[provider] = RateLimiter(per_minute)
        self._stopped_models = {}
        self._stopped_providers = {}
        self.summary = Summary()

    # --- Output and stops -------------------------------------------------------------

    def say(self, message):
        with self._lock:
            self._out(self._scrub(message))

    def _halt(self, reason, message):
        with self._lock:
            if self.summary.stopped is None:
                self.summary.stopped = reason
                self.summary.stop_message = self._scrub(message)
                self._out(f"stopping the run ({reason}): "
                          f"{self.summary.stop_message}")
        self._stop_event.set()

    def _block(self, scope, model, reason):
        name = model.provider if scope == "provider" else model.id
        table = self._stopped_providers if scope == "provider" else self._stopped_models
        with self._lock:
            if name in table:
                return
            table[name] = reason
        self.say(f"stopping calls to {scope} {name} for this run: {reason}")

    def _blocked(self, model):
        with self._lock:
            return (model.provider in self._stopped_providers
                    or model.id in self._stopped_models)

    def _count(self, **changes):
        with self._lock:
            for name, value in changes.items():
                if name == "finished":
                    self.summary.finished[value] += 1
                else:
                    setattr(self.summary, name, getattr(self.summary, name) + value)

    # --- Running ----------------------------------------------------------------------

    def adapter(self, provider):
        if provider not in self._adapters:
            options = {}
            if provider == "anthropic" and self._anthropic_workspace_id:
                options["workspace_id"] = self._anthropic_workspace_id
            self._adapters[provider] = adapter_for(provider, **options)
        return self._adapters[provider]

    def run(self, cells):
        """Run ``cells`` (already filtered by :func:`pending_cells`) and return
        the :class:`Summary`. Raises :class:`RunError` before any call if a
        key is missing or a provider has no adapter."""
        cells = list(cells)
        missing = sorted({cell.model.api_key_env for cell in cells
                          if not self.keys.get(cell.model.api_key_env)})
        if missing:
            raise RunError("no key in the environment for: " + ", ".join(missing))
        for provider in {cell.model.provider for cell in cells}:
            try:
                self.adapter(provider)
            except KeyError as error:
                raise RunError(str(error)) from None
        self.summary.cells = len(cells)
        self._queue = iter(cells)
        # Work happens in threads even with one worker: on Windows a blocking
        # read cannot be interrupted, but the main thread, waiting in short
        # slices, still sees Ctrl-C. The first Ctrl-C lets calls in flight
        # finish and be recorded; a second abandons them (the ledger then
        # counts them at their worst case).
        threads = [threading.Thread(target=self._work, daemon=True)
                   for _ in range(self.workers)]
        for thread in threads:
            thread.start()
        try:
            self._join(threads)
        except KeyboardInterrupt:
            self._halt("interrupted", "interrupted by the user")
            self.say("waiting for calls in flight to finish and be recorded "
                     "(interrupt again to abandon them)")
            self._join(threads)
        if self._crash is not None:
            raise self._crash
        with self._lock:
            self.summary.not_started += sum(1 for _ in self._queue)
        return self.summary

    @staticmethod
    def _join(threads):
        for thread in threads:
            while thread.is_alive():
                thread.join(0.25)

    def _wait(self, seconds):
        """Sleep, in short slices, unless the run is stopping."""
        deadline = time.monotonic() + seconds
        while not self._stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._stop_event.wait(min(remaining, 0.5))

    def _work(self):
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    cell = next(self._queue, None)
                if cell is None:
                    return
                try:
                    self._run_cell(cell)
                except Exception as error:  # a bug: stop rather than spend on it
                    self._halt("error", f"{type(error).__name__}: {error}")
                    return
        except BaseException as error:  # not an Exception: re-raised in run()
            with self._lock:
                self._crash = self._crash or error
            self._stop_event.set()

    def _run_cell(self, cell):
        attempts, last = 0, None
        while True:
            if self._stop_event.is_set() or self._blocked(cell.model):
                if attempts == 0:
                    self._count(**({"not_started": 1} if self._stop_event.is_set()
                                   else {"skipped": 1}))
                else:
                    self._count(finished=last.status)
                return
            result = self._attempt(cell, attempts + 1)
            if result is None:  # the run stopped before this attempt was sent
                if attempts == 0:
                    self._count(not_started=1)
                else:
                    self._count(finished=last.status)
                return
            attempts, last = attempts + 1, result
            self._watch_429(cell.model, result)
            if result.premium:
                self._block("provider", cell.model,
                            f"the response reports {result.premium}, which is not "
                            "priced at the list rates the ledger uses")
            if (result.status == "failed" and result.retryable
                    and self.retry.may_retry(attempts)
                    and not self._blocked(cell.model)):
                wait = self.retry.delay(attempts, result.retry_after, self._rng)
                if wait is not None:
                    self.say(f"  retrying {cell.label()} in {wait:.1f} s")
                    self._sleep(wait)
                    continue
                self.say(f"  not retrying {cell.label()}: the provider asked to "
                         f"wait {result.retry_after:.0f} s")
            if result.stop:
                self._block(result.stop, cell.model, result.error or result.status)
            self._count(finished=result.status)
            return

    def _watch_429(self, model, result):
        """Stop a provider after too many HTTP 429 answers in a row."""
        with self._lock:
            if result.http_status == 429:
                self._consecutive_429[model.provider] += 1
            else:
                self._consecutive_429[model.provider] = 0
            reached = self._consecutive_429[model.provider] >= self.max_consecutive_429
        if reached:
            self._block("provider", model,
                        f"{self.max_consecutive_429} HTTP 429 answers in a row (a "
                        "daily quota or billing limit?)")

    def _attempt(self, cell, number):
        """Reserve, send, settle and record one attempt; None if the run
        stopped before anything was sent."""
        model = cell.model
        adapter = self.adapter(model.provider)
        prepared = adapter.prepare(model, cell.prompt_text,
                                   self.keys[model.api_key_env])
        limiter = self._limiters.get(model.provider)
        if limiter is not None:
            limiter.acquire()
        if self._stop_event.is_set():
            return None
        record_id = str(uuid.uuid4())
        try:
            reservation = self.ledger.reserve(
                model_id=model.id, record_id=record_id,
                prompt_tokens=estimate_prompt_tokens(cell.prompt_text),
                max_output_tokens=prepared.max_output_tokens)
        except BudgetExceeded as error:
            self._halt("budget", str(error))
            return None
        except LedgerError as error:
            self._halt("ledger", str(error))
            return None
        self._count(attempts=1)
        sent_at = utc_now()
        result, usage, charge = None, None, None
        try:
            result, sent = self._send(adapter, prepared)
            if not sent:
                usage = Usage(input=0, output=0)  # nothing left the machine
            elif result.premium:
                pass  # priced above list rates: charge the worst case
            elif result.tokens is not None and result.tokens.complete:
                usage = Usage(input=result.tokens.input, output=result.tokens.output,
                              reasoning=result.tokens.reasoning,
                              reasoning_in_output=True)  # normalised by adapters
        finally:
            try:
                charge = self.ledger.settle(
                    reservation, usage,
                    request_id=result.request_id if result is not None else None)
            except LedgerError as error:
                self._halt("ledger", f"a charge could not be written: {error}")
        self._record(cell, number, record_id, prepared, result, charge, sent_at)
        if charge is not None and charge.over_reservation:
            self._halt("over_reservation",
                       f"{cell.label()} cost ${charge.cost_usd}, more than the "
                       f"${reservation.worst_case_usd} reserved: an assumption "
                       "behind the cap is wrong (see docs/ledger.md)")
        return result

    def _send(self, adapter, prepared):
        """(result, whether the request may have left the machine)."""
        try:
            response = self.transport.send(prepared.request)
        except NotSentError as error:
            return Result("failed", retryable=True, error=f"not sent: {error}"), False
        except SendError as error:
            return Result("failed", retryable=True, error=f"no response: {error}"), True
        except Exception as error:  # a transport bug: record it, do not repeat it
            return Result("failed", stop="model",
                          error=f"the transport failed: "
                                f"{type(error).__name__}: {error}"), True
        try:
            result = adapter.parse(response)
        except TotalTimeoutError as error:  # sending again would run as long
            result = Result("failed", stop="model",
                            request_id=adapter.header_request_id(response),
                            error=f"{error}; not retried")
        except SendError as error:
            result = Result("failed", retryable=True,
                            request_id=adapter.header_request_id(response),
                            error=f"the response was cut off: {error}")
        except ParseError as error:
            result = Result("failed", stop="model",
                            request_id=adapter.header_request_id(response),
                            error=f"unreadable response: {error}")
        except Exception as error:  # an undocumented shape: do not repeat it
            result = Result("failed", stop="model",
                            error=f"could not read the response: "
                                  f"{type(error).__name__}: {error}")
        try:
            response.close()
        except Exception as error:  # keep what was read; record the failure
            result = dataclasses.replace(
                result, status="failed", retryable=False, stop="model",
                error=f"closing the response failed: {type(error).__name__}: "
                      f"{error}" + (f" (after: {result.error})" if result.error else ""))
        return result, True

    def _record(self, cell, number, record_id, prepared, result, charge, sent_at):
        status = result.status
        # Model output keeps key-shaped text the model wrote; only the keys in
        # use are removed. Error text gets the full scrub.
        text = self._scrub.exact(result.text) if result.text else None
        error = self._scrub(result.error) if result.error else None
        if status == "ok":
            error = None
        elif status == "failed" and not error:
            error = "failed with no detail"
        files = []
        if text and status != "failed":
            directory = files_dir(self.records_path, record_id)
            try:
                files = save_files(directory, text)
            except (OSError, RecordError) as problem:
                # Never lose a paid response over a file: the record keeps the
                # full text, and extraction can be redone from it.
                files = []
                shutil.rmtree(directory, ignore_errors=True)
                self.say(f"warning: files from {cell.label()} could not be saved "
                         f"({type(problem).__name__}: {problem}); the record "
                         "keeps the whole response")
        settings = dict(prepared.settings)
        for name, value in (result.reported or {}).items():
            settings[f"reported_{name}"] = value
        tokens = {}
        if result.tokens is not None:
            tokens = {"input": result.tokens.input, "output": result.tokens.output,
                      "reasoning": result.tokens.reasoning}
        cost = (float(charge.cost_usd)
                if charge is not None and not charge.estimated else None)
        stop_reason = result.stop_reason
        if not (isinstance(stop_reason, str) and stop_reason.strip()):
            stop_reason = None
        record = build_record(
            record_id=record_id, batch_id=self.batch_id,
            project_type=cell.task.project_type, task_id=cell.task.task_id,
            prompt_set_version=cell.task.prompt_set_version, level=cell.level,
            wording=cell.wording, run_index=cell.run_index,
            prompt_text=cell.prompt_text, provider=cell.model.provider,
            model_id=cell.model.id, model_id_returned=result.model_id_returned,
            settings=settings, timestamp=sent_at, tokens=tokens,
            cost_usd=cost, status=status, error=error, stop_reason=stop_reason,
            request_id=result.request_id, raw_response=text, files=files)
        with self._write_lock:
            append_record(self.records_path, record)
        detail = (f"{tokens.get('output')} output tokens" if tokens.get("output")
                  is not None else "no token counts")
        if cost is not None:
            detail += f", ${cost:.4f}"
        elif charge is not None:
            detail += (f", cost unknown: the ledger charges the worst case, "
                       f"${float(charge.cost_usd):.4f}")
        else:
            detail += ", cost unknown"
        if error:
            detail += f"; {error}"
        self.say(f"{cell.label()} (attempt {number}): {status} ({detail})")
        return record
