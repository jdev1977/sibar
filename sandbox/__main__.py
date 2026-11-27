"""Command line of the sandbox (T2.7): ``python -m sandbox``.

    python -m sandbox setup [--wheelhouse FOLDER]
    python -m sandbox status
    python -m sandbox clean
    python -m sandbox remove
    python -m sandbox run --records FILE [--record-id ID] [--force] [limits]
    python -m sandbox run --dir FOLDER [--task TYPE/TASK/LEVEL] [--command ...]

See ``docs/sandbox.md``.
"""

import argparse
import shlex
import sys
from dataclasses import fields
from pathlib import Path

from sandbox import runtime
from sandbox.box import Limits, SandboxError, leftover_processes, sweep
from sandbox.records import RunRefused, run_directory, run_file
from sandbox.run import Settings

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
LIMIT_OPTIONS = {
    "seconds": "wall-clock seconds per run", "cpu_seconds": "CPU seconds per run",
    "memory_mb": "memory for all processes of a run",
    "processes": "processes alive at once", "disk_mb": "size of the working folder",
    "files": "files and folders in the working folder",
    "write_mb": "megabytes written per run", "cpu_percent": "CPU rate cap, of all cores",
    "free_disk_mb": "free space the drive must keep",
}


def build_parser():
    defaults = Limits()
    parser = argparse.ArgumentParser(
        prog="python -m sandbox",
        description="Run untrusted, model-generated code in a Windows sandbox.")
    commands = parser.add_subparsers(dest="action", required=True)
    setup = commands.add_parser("setup", help="build the private Python runtime")
    setup.add_argument("--wheelhouse", metavar="FOLDER",
                       help="install the pinned packages from this folder, not PyPI")
    commands.add_parser("status", help="check the runtime and look for leftovers")
    commands.add_parser("clean", help="remove AppContainer profiles and working "
                                      "folders left by runs that crashed")
    commands.add_parser("remove", help="delete the runtime and anything left by runs")
    run = commands.add_parser("run", help="run outputs in the sandbox")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", metavar="FILE", help="a record file")
    source.add_argument("--dir", metavar="FOLDER", help="a folder holding one output")
    run.add_argument("--record-id", action="append", default=[], metavar="ID",
                     help="with --records: this record only (repeatable)")
    run.add_argument("--force", action="store_true",
                     help="with --records: run again records already run")
    run.add_argument("--out", metavar="FILE",
                     help="with --dir: where the result goes (default <folder>-sandbox.json)")
    run.add_argument("--task", metavar="TYPE/TASK/LEVEL",
                     help="with --dir: the task, for its fixtures (such as "
                          "pipeline/data-validation/L2)")
    run.add_argument("--command", metavar="COMMAND",
                     help="with --dir: the command to run, such as \"python main.py\"")
    run.add_argument("--no-tests", action="store_true", help="do not run the output's tests")
    run.add_argument("--clock", help="a fixed start time, ISO 8601 with a time zone")
    run.add_argument("--scale-mb", type=int, default=0,
                     help="size of generated large inputs, for tasks that have them")
    for name, description in LIMIT_OPTIONS.items():
        run.add_argument("--" + name.replace("_", "-"), type=type(getattr(defaults, name)),
                         default=getattr(defaults, name),
                         help=f"{description} (default %(default)s)")
    return parser


def _settings(args):
    try:
        limits = Limits(**{item.name: getattr(args, item.name) for item in fields(Limits)
                           if item.name in LIMIT_OPTIONS})
    except ValueError as error:
        raise RunRefused(str(error)) from None
    task = None
    if args.task:
        parts = args.task.split("/")
        if len(parts) != 3:
            raise RunRefused("--task: give TYPE/TASK/LEVEL, such as pipeline/log-aggregation/L2")
        task = tuple(parts)
    command = tuple(shlex.split(args.command, posix=False)) if args.command else None
    return Settings(limits=limits, command=command, tests=not args.no_tests, task=task,
                    clock=args.clock, scale_mb=args.scale_mb)


def _status():
    root = runtime.default_root()
    try:
        found = runtime.check(root)
    except runtime.RuntimeMissing as error:
        print(f"runtime: {error}")
        return EXIT_REFUSED
    print(f"runtime: {runtime.runtime_dir(root)}, Python {found['python']}, "
          f"{len(found['packages'])} packages")
    from sandbox import win32

    left = [name for name in win32.profile_names() if name.startswith("sibar.sb.")]
    work = root / "work"
    folders = sorted(p.name for p in work.iterdir()) if work.is_dir() else []
    running = []
    for handle, pid, image in leftover_processes(root):
        win32.close(handle)
        running.append(f"{pid} ({image})")
    print(f"AppContainer profiles of this sandbox: {', '.join(left) or 'none'}")
    print(f"working folders: {', '.join(folders) or 'none'}")
    print(f"processes of the runtime: {', '.join(running) or 'none'}")
    return EXIT_OK


def _clean():
    from runner.ledger import LedgerError, lock_file, unlock_file

    root = runtime.default_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        lock = lock_file(root / "sandbox.lock")
    except LedgerError:
        print(f"refused: a sandbox run is using {root}")
        return EXIT_REFUSED
    try:
        removed, problems = sweep(root)
    finally:
        unlock_file(lock)
    print("removed: " + (", ".join(removed) or "nothing"))
    for problem in problems:
        print(f"could not remove {problem}")
    return EXIT_FAILED if problems else EXIT_OK


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "setup":
            runtime.setup(wheelhouse=args.wheelhouse)
            return EXIT_OK
        if args.action == "status":
            return _status()
        if args.action == "clean":
            return _clean()
        if args.action == "remove":
            code = _clean()
            runtime.remove()
            print("runtime removed")
            return code
        wrong = ((("--out", args.out), ("--task", args.task), ("--command", args.command))
                 if args.records else
                 (("--record-id", args.record_id), ("--force", args.force)))
        for option, value in wrong:
            if value:
                parser.error(f"{option} cannot be used with "
                             f"{'--records' if args.records else '--dir'}")
        settings = _settings(args)
        if args.records:
            counts = run_file(args.records, settings, args.record_id, args.force)
            print(", ".join(f"{n} {result}" for result, n in sorted(counts.items()))
                  or "no records to run")
            bad = sum(n for result, n in counts.items()
                      if result not in ("ran", "skipped"))
        else:
            folder = Path(args.dir).resolve()
            out = args.out or folder.with_name(folder.name + "-sandbox.json")
            check = run_directory(args.dir, out, settings)
            detail = check["detail"]
            print(f"{detail['result']}: {detail.get('reason') or 'see ' + str(out)}")
            if detail.get("cleanup_error"):
                print(f"cleanup failed: {detail['cleanup_error']}")
            bad = check["outcome"] != "ok"
    except (RunRefused, SandboxError, runtime.RuntimeMissing, OSError) as error:
        print(f"refused: {error}")
        return EXIT_REFUSED
    except KeyboardInterrupt:
        print("interrupted; finished runs are saved")
        return 130
    except Exception as error:  # never a traceback for what a run left behind
        print(f"error: {type(error).__name__}: {error}"[:1000])
        return EXIT_REFUSED
    return EXIT_FAILED if bad else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
