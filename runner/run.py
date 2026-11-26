"""Command line for generation runs (T0.5): ``python -m runner.run``.

    python -m runner.run --prompts PATH... --batch-id ID --dry-run
    python -m runner.run --prompts PATH... --batch-id ID --paid \\
        --batch-cap USD --total-cap USD [--ledger PATH]

``--dry-run`` lists the cells still to run and their worst-case cost and
sends nothing. ``--paid`` spends money: it needs both caps, a key for every
chosen model, and ``confirmed_by_human: true`` in models.yaml. See
``docs/runner.md``.
"""

import argparse
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

# The ledger's operating-system file lock also guards the record file.
from runner.ledger import (
    DEFAULT_PATH, ROOT, Ledger, LedgerError, _lock, _text, _unlock, call_cost,
    estimate_prompt_tokens, read_ledger,
)
from runner.loop import DEFAULT_RERUN, Runner, RunError, pending_cells, plan_cells
from runner.models import ModelsError, load_models
from runner.prompts import PromptError, load_prompts
from runner.providers import adapter_for
from runner.record import LEVELS, STATUSES, WORDINGS
from runner.retry import RetryPolicy

DEFAULT_RPM = 30
RUNS_DIR = ROOT / "data" / "runs"
_BATCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_KEY = re.compile(r"[\x21-\x7e]+")  # printable ASCII, no spaces
EXIT_OK, EXIT_FAILED, EXIT_REFUSED, EXIT_BUDGET, EXIT_STOPPED = 0, 1, 2, 3, 4
EXIT_INTERRUPTED = 130


class Refusal(Exception):
    """The command refuses to run; the message says why."""


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m runner.run",
        description="Send prompts to the models under test and save run records.")
    parser.add_argument("--prompts", nargs="+", required=True, metavar="PATH",
                        help="prompt files or folders (prompts/<type>/)")
    parser.add_argument("--batch-id", required=True,
                        help="the batch these runs belong to, such as pilot-1")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="list cells and worst-case cost; send nothing")
    mode.add_argument("--paid", action="store_true",
                      help="send the requests (spends money)")
    parser.add_argument("--models", default="all",
                        help="all (default), pilot, or model ids separated by commas")
    parser.add_argument("--levels", default=",".join(LEVELS))
    parser.add_argument("--wordings", default=",".join(WORDINGS))
    parser.add_argument("--runs", type=int, default=1,
                        help="runs per prompt and model (default 1)")
    parser.add_argument("--batch-cap", metavar="USD",
                        help="spending limit for this batch (required with --paid)")
    parser.add_argument("--total-cap", metavar="USD",
                        help="spending limit for the whole ledger (required with --paid)")
    parser.add_argument("--ledger", metavar="PATH",
                        help=f"ledger file (default {DEFAULT_PATH})")
    parser.add_argument("--out", metavar="PATH",
                        help="record file (default data/runs/<batch-id>/records.jsonl)")
    parser.add_argument("--rerun", default="",
                        help="statuses to run again besides failed: refused, truncated")
    parser.add_argument("--workers", type=int, default=1,
                        help="requests in flight at once (default 1)")
    parser.add_argument("--max-attempts", type=int, default=RetryPolicy.max_attempts,
                        help="attempts per cell, including the first")
    parser.add_argument("--rpm", action="append", default=[], metavar="PROVIDER=N",
                        help=f"requests per minute for a provider (default {DEFAULT_RPM})")
    parser.add_argument("--read-timeout", type=float, default=900.0, metavar="SECONDS",
                        help="give up on a response silent this long (default 900)")
    parser.add_argument("--total-timeout", type=float, default=3600.0,
                        metavar="SECONDS",
                        help="give up on a response taking longer (default 3600)")
    parser.add_argument("--models-file", default=str(ROOT / "models.yaml"),
                        help="the model list (default models.yaml)")
    return parser


def _choose_models(model_list, choice):
    if choice == "all":
        return list(model_list.models)
    ids = list(model_list.pilot) if choice == "pilot" else [
        part.strip() for part in choice.split(",") if part.strip()]
    chosen = []
    for model_id in ids:
        try:
            chosen.append(model_list.get(model_id))
        except KeyError:
            raise Refusal(f"--models: {model_id!r} is not in the model list") from None
    if not chosen:
        raise Refusal("--models: no model chosen")
    return chosen


def _choices(text, allowed, option):
    values = [part.strip() for part in text.split(",") if part.strip()]
    for value in values:
        if value not in allowed:
            raise Refusal(f"{option}: {value!r} is not one of {', '.join(allowed)}")
    if not values:
        raise Refusal(f"{option}: choose at least one of {', '.join(allowed)}")
    return tuple(values)


def _rerun_statuses(text):
    extra = [part.strip() for part in text.split(",") if part.strip()]
    for status in extra:
        if status not in STATUSES or status == "ok":
            raise Refusal(f"--rerun: {status!r} is not refused, truncated or failed")
    return tuple(dict.fromkeys(DEFAULT_RERUN + tuple(extra)))


def _rpm(values, providers):
    limits = dict.fromkeys(providers, DEFAULT_RPM)
    for value in values:
        provider, equals, number = value.partition("=")
        if not equals:
            raise Refusal(f"--rpm: {value!r} must be PROVIDER=N")
        try:
            per_minute = float(number)
        except ValueError:
            per_minute = -1
        if not per_minute > 0 or per_minute == float("inf"):
            raise Refusal(f"--rpm: {provider} must have a number above 0")
        limits[provider.strip()] = per_minute
    return limits


def _keys(models, environ):
    keys, missing, bad = {}, [], []
    for name in sorted({model.api_key_env for model in models}):
        value = (environ.get(name) or "").strip()
        if not value:
            missing.append(name)
        elif not _KEY.fullmatch(value):
            bad.append(name)
        else:
            keys[name] = value
    if bad:
        raise Refusal("these keys contain spaces, line breaks or other characters "
                      f"a key cannot have (values not shown): {', '.join(bad)}")
    return keys, missing


def _worst_case(runner_cell, adapter_for_cell):
    model = runner_cell.model
    prepared = adapter_for_cell(model.provider).prepare(
        model, runner_cell.prompt_text, "dry-run-placeholder")
    limit = prepared.max_output_tokens or model.defaults.max_output_tokens
    return call_cost(model, estimate_prompt_tokens(runner_cell.prompt_text), limit)


def _batches_in(ledger_path):
    if not Path(ledger_path).exists():
        return None
    return sorted({entry["batch_id"] for entry in read_ledger(ledger_path).entries})


def _dry_run(cells, todo, done, args, model_list, environ, ledger_path, out):
    adapters = {}

    def adapter(provider):
        if provider not in adapters:
            adapters[provider] = adapter_for(provider)
        return adapters[provider]

    out("Dry run: no request is sent.")
    flag = model_list.confirmed_by_human
    out(f"Model list: {args.models_file} (confirmed_by_human: "
        f"{'true' if flag else 'false'}"
        f"{'' if flag else '; a paid run would be refused'})")
    out(f"{done} of {len(cells)} cells already done; {len(todo)} to run.")
    costs = [(cell, _worst_case(cell, adapter)) for cell in todo]
    width = max([len(cell.label()) for cell in todo] + [4])
    for cell, cost in costs:
        out(f"  {cell.label().ljust(width)}  ${cost:.4f}")
    per_model = Counter()
    for cell, cost in costs:
        per_model[cell.model.id] += cost
    for model_id, cost in per_model.items():
        out(f"Worst case for {model_id}: ${cost:.4f}")
    total = sum((cost for _, cost in costs), Decimal(0))
    out(f"Worst case for {len(todo)} cells: ${total:.4f} (one attempt each; each "
        "retry can add as much again)")
    batches = _batches_in(ledger_path) or []
    if args.batch_id in batches:
        spent = sum(Decimal(e["cost_usd"]) for e in
                    {e["call_id"]: e for e in read_ledger(ledger_path).entries}.values()
                    if e["batch_id"] == args.batch_id)
        out(f"Batch {args.batch_id} has ${_text(spent)} spent or reserved in the ledger.")
    else:
        out(f"Batch {args.batch_id} is new to the ledger.")
    if args.batch_cap is not None and total > Decimal(args.batch_cap):
        out(f"The worst case is more than the batch cap (${args.batch_cap}); a paid "
            "run would stop at the cap.")
    _, missing = _keys([cell.model for cell in cells], environ)
    if missing:
        out("No key in the environment for: " + ", ".join(missing)
            + " (a paid run would refuse)")
    return EXIT_OK


def _paid(cells, args, model_list, environ, ledger_path, transport, out):
    if not model_list.confirmed_by_human:
        raise Refusal(f"{args.models_file} has confirmed_by_human: false. A person "
                      "must check the model list and set it to true before a paid run.")
    for option, value in (("--batch-cap", args.batch_cap),
                          ("--total-cap", args.total_cap)):
        if value is None:
            raise Refusal(f"a paid run needs {option} (in US dollars)")
    keys, missing = _keys([cell.model for cell in cells], environ)
    if missing:
        raise Refusal("no key in the environment for: " + ", ".join(missing)
                      + ". Set them, or leave those models out with --models.")
    retry = RetryPolicy(max_attempts=args.max_attempts)
    batches = _batches_in(ledger_path)
    if batches is None:
        out(f"warning: the ledger {ledger_path} does not exist yet; batch "
            f"{args.batch_id!r} is new to the ledger and starts from $0.")
    elif args.batch_id not in batches:
        known = ", ".join(batches[:10]) or "none"
        out(f"warning: batch {args.batch_id!r} is new to the ledger and starts "
            f"from $0. Batches already in it: {known}.")
    if transport is None:
        from runner.transport import UrllibTransport
        transport = UrllibTransport(read_timeout=args.read_timeout,
                                    total_timeout=args.total_timeout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        records_lock = _lock(args.out.with_name(args.out.name + ".lock"))
    except LedgerError:
        raise Refusal(f"{args.out}: the record file is in use by another run") from None
    try:
        with Ledger(ledger_path, batch_id=args.batch_id,
                    batch_cap_usd=args.batch_cap, total_cap_usd=args.total_cap,
                    models=model_list) as ledger:
            if ledger.repaired_tail:
                out(f"{ledger_path}: removed an unfinished last line left by an "
                    "interrupted run")
            rerun = _rerun_statuses(args.rerun)
            todo, done = pending_cells(cells, args.out, args.batch_id, rerun,
                                       repair=True, out=out)
            out(f"{done} of {len(cells)} cells already done; {len(todo)} to run.")
            runner = Runner(
                batch_id=args.batch_id, records_path=args.out, ledger=ledger,
                transport=transport, keys=keys, retry=retry,
                rpm=_rpm(args.rpm, {c.model.provider for c in cells}),
                workers=args.workers, rerun_statuses=rerun, out=out,
                anthropic_workspace_id=(environ.get("ANTHROPIC_WORKSPACE_ID")
                                        or "").strip() or None)
            summary = runner.run(todo)
            spent, total = ledger.spent_usd, ledger.total_spent_usd
    finally:
        _unlock(records_lock)
    finished = ", ".join(f"{status} {number}" for status, number in
                         sorted(summary.finished.items())) or "none"
    out(f"Finished {sum(summary.finished.values())} of {summary.cells} cells: "
        f"{finished}. Requests: {summary.attempts}. Skipped (model or provider "
        f"stopped): {summary.skipped}. Not started: {summary.not_started}.")
    out(f"Batch {args.batch_id}: ${_text(spent)} spent or reserved; whole ledger: "
        f"${_text(total)}. Records: {args.out}")
    if summary.stopped == "budget":
        return EXIT_BUDGET
    if summary.stopped == "interrupted":
        return EXIT_INTERRUPTED
    if summary.stopped:
        return EXIT_STOPPED
    unfinished = summary.finished.get("failed", 0) + summary.skipped
    return EXIT_FAILED if unfinished else EXIT_OK


def main(argv=None, *, transport=None, environ=None, out=print):
    """Run the command; return the exit status. ``transport`` and
    ``environ`` are for tests (default: HTTPS and ``os.environ``)."""
    import os
    args = build_parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    try:
        if not _BATCH.fullmatch(args.batch_id):
            raise Refusal("--batch-id must be letters, digits, '.', '_' or '-' "
                          "(it names a folder), starting with a letter or digit")
        if args.workers < 1:
            raise Refusal("--workers must be at least 1")
        for option, value in (("--read-timeout", args.read_timeout),
                              ("--total-timeout", args.total_timeout)):
            if not 0 < value < float("inf"):
                raise Refusal(f"{option} must be a number of seconds above 0")
        try:
            RetryPolicy(max_attempts=args.max_attempts)
        except ValueError as error:
            raise Refusal(f"--max-attempts: {error}") from None
        model_list = load_models(args.models_file)
        models = _choose_models(model_list, args.models)
        levels = _choices(args.levels, LEVELS, "--levels")
        wordings = _choices(args.wordings, WORDINGS, "--wordings")
        _rerun_statuses(args.rerun)
        _rpm(args.rpm, {model.provider for model in models})
        tasks = load_prompts(args.prompts)
        cells = plan_cells(tasks, models, args.runs, levels, wordings)
        if not cells:
            raise Refusal("no cells: the prompts have none of the chosen levels "
                          "and wordings")
        args.out = Path(args.out) if args.out else RUNS_DIR / args.batch_id / "records.jsonl"
        ledger_path = Path(args.ledger) if args.ledger else DEFAULT_PATH
        out(f"Ledger: {ledger_path}{'' if args.ledger else ' (default)'}")
        out(f"Records: {args.out}")
        if args.dry_run:
            todo, done = pending_cells(cells, args.out, args.batch_id,
                                       _rerun_statuses(args.rerun),
                                       repair=False, out=out)
            return _dry_run(cells, todo, done, args, model_list, environ,
                            ledger_path, out)
        return _paid(cells, args, model_list, environ, ledger_path, transport, out)
    except (Refusal, RunError, ModelsError, PromptError, LedgerError,
            OSError) as error:
        out(f"refused: {error}")
        return EXIT_REFUSED
    except KeyboardInterrupt:
        out("interrupted")
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
