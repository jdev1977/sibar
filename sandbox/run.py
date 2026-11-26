"""Run an output's files in the sandbox and say what happened (T2.7).

:func:`run_folder` copies the files into a fresh box, surveys them (inside
the sandbox), runs the output's tests if it has any and its entry point if
one can be found (or the command given), and returns the ``detail`` of a
``sandbox`` check: the outcome, the runs and their limits, what the task's
fixtures and measurements found. See docs/sandbox.md.

Outcomes (``detail["result"]``):

- ``ran``: the entry point (or, with no entry point, the test run) ended by
  itself with exit code 0.
- ``failed``: it ended by itself with another exit code, and nothing points
  to a limit or a boundary.
- ``timeout``: the wall-clock or CPU-time limit ended it.
- ``memory``: the memory limit refused memory and it then failed.
- ``blocked``: it ran into a boundary and then failed (the network, files
  outside its folder, the process limit), or the disk limit ended it.
- ``not-runnable``: the sandbox could not run it: no Python files (and why),
  modules outside the sandbox's package set, or nothing to run.
- ``error``: the sandbox itself failed; nothing is said about the output.
"""

import json
import re
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Optional

from sandbox import runtime
from sandbox.box import Box, Limits, SandboxError
from sandbox.files import copy_files, read_file

TOOLS = Path(__file__).with_name("tools")
OUTCOMES = ("ran", "failed", "timeout", "memory", "blocked", "not-runnable", "error")
TEXT_LIMIT = 4000  # characters of stdout or stderr kept in a record
# Names an entry point most often has, best first.
ENTRY_NAMES = ("main.py", "__main__.py", "app.py", "run.py", "cli.py", "pipeline.py")
LANGUAGES = {
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin", ".cs": "C#", ".c": "C", ".cpp": "C++",
    ".rb": "Ruby", ".php": "PHP", ".r": "R", ".jl": "Julia", ".m": "MATLAB",
    ".sh": "shell", ".ps1": "PowerShell", ".bat": "batch", ".sql": "SQL",
    ".ipynb": "notebook", ".scad": "OpenSCAD", ".swift": "Swift", ".scala": "Scala",
}
NOT_RUN = ("only Python runs in the sandbox: no other language runtime is installed "
           "(installing one would be a system change), and shell scripts would run "
           "commands on Windows that were written for another system")
BLOCKED_SIGNS = (
    ("network", re.compile(r"WinError 10013|forbidden by its access permissions|"
                           r"getaddrinfo failed|the sandbox has no sockets|"
                           r"Failed to establish a new connection|"
                           r"Temporary failure in name resolution|Errno 1100[13]")),
    ("files outside the folder", re.compile(
        r"(?:PermissionError|OSError): \[(?:WinError 5|Errno 13)\][^\n]*'([^'\n]+)'")),
)
OUTSIDE_PACKAGES = "imports modules outside the sandbox's package set: "


@dataclass(frozen=True)
class Settings:
    """How to run one output."""

    limits: Limits = Limits()
    command: Optional[tuple] = None  # argv; a first item "python" is the runtime's
    tests: bool = True  # run the output's tests, if it has any
    entry: bool = True  # run its entry point (or the command)
    task: Optional[tuple] = None  # (project_type, task_id, level) for task hooks
    clock: Optional[str] = None  # a fixed start time; the task's when None
    scale_mb: int = 0  # larger generated inputs, for tasks that have them


def text(data, folder=None, limit=TEXT_LIMIT):
    """Output bytes as text for a record: decoded, the runtime's start-up
    warning removed, local folders replaced, at most ``limit`` characters
    (head and tail)."""
    value = data.decode("utf-8", "replace").replace("\r\n", "\n")
    value = re.sub(r"Failed to find real location of [^\n]*python\.exe\n?", "", value)
    if folder is not None:
        value = value.replace(str(folder), "<folder>")
        value = value.replace(str(Path(folder).parents[1]), "<root>")
    if len(value) > limit:
        half = limit // 2
        value = value[:half] + "\n[...]\n" + value[-half:]
    return value


def blocked_signs(stderr_text, folder="<folder>"):
    """What boundaries the error output shows the program ran into."""
    found = []
    for name, pattern in BLOCKED_SIGNS:
        for match in pattern.finditer(stderr_text):
            if match.groups() and match.group(1).startswith(folder):
                continue  # inside its own folder: not a boundary
            found.append(name)
            break
    return found


def classify(run, stderr_text):
    """``(outcome, reason)`` for a finished run (a RunResult)."""
    if run.cause == "timeout":
        return "timeout", "the wall-clock limit ended it"
    if run.cause == "cpu":
        return "timeout", "the CPU-time limit ended it"
    if run.cause in ("disk", "writes"):
        return "blocked", ("the disk limit ended it" if run.cause == "disk"
                           else "the limit on bytes written ended it")
    if run.exit_code == 0:
        return "ran", None
    if run.memory_refused or "MemoryError" in stderr_text:
        return "memory", "the memory limit refused memory"
    signs = blocked_signs(stderr_text)
    if signs:
        return "blocked", "it ran into the sandbox's boundaries: " + ", ".join(signs)
    if run.process_refused:
        return "blocked", "the process limit refused a process"
    return "failed", None


def local_modules(paths):
    """Top-level module names an output's own files provide."""
    names = set()
    for path in paths:
        parts = path.split("/")
        for depth, part in enumerate(parts):
            if part.endswith(".py"):
                names.add(part[:-3])
            elif depth < len(parts) - 1:
                names.add(part)
    return names


def missing_modules(survey, paths, files=None):
    """Modules imported (outside try blocks) by ``files`` (default: all) that
    are neither in the runtime nor in the output."""
    local = local_modules(paths)
    wanted = set()
    for entry in survey["files"]:
        if files is None or entry["path"] in files:
            wanted.update(entry.get("imports", []))
    return sorted(name for name in wanted
                  if not survey["available"].get(name, False) and name not in local)


def choose_entry(survey, paths):
    """``(argv after "python", candidates)``: the output's entry point, or
    None. Candidates are files that run code when started (a main guard, or
    statements at the top level) and are not tests nor imported by the
    output; packages with a ``__main__.py``; console scripts in
    pyproject.toml. A file with a usual entry name comes first, then a
    package, a console script, and the other files."""
    files = {entry["path"]: entry for entry in survey["files"]}
    imported = {name for entry in survey["files"] for name in entry.get("imports", [])}
    candidates = []
    for path, entry in files.items():
        if entry.get("test") or "syntax_error" in entry or "error" in entry:
            continue
        name = path.rsplit("/", 1)[-1]
        if name == "__main__.py" and "/" in path:
            continue  # run as a package below
        if entry.get("main_guard") or (entry.get("runs_code") and name[:-3] not in imported):
            candidates.append(path)
    packages = sorted({path.rsplit("/", 1)[0] for path in files
                       if path.endswith("/__main__.py") and path.count("/") == 1})

    def order(path):
        name = path.rsplit("/", 1)[-1]
        rank = ENTRY_NAMES.index(name) if name in ENTRY_NAMES else len(ENTRY_NAMES)
        return (rank, path.count("/"), not files[path].get("main_guard"), path)

    candidates.sort(key=order)
    scripts = survey.get("scripts") or {}
    listed = ([f"-m {package}" for package in packages]
              + [f"script {name}" for name in sorted(scripts)] + candidates)
    if candidates and order(candidates[0])[0] < len(ENTRY_NAMES):
        return [candidates[0].replace("/", "\\")], listed
    if packages:
        return ["-m", packages[0]], listed
    for name, target in sorted(scripts.items()):
        module, _, function = target.partition(":")
        function = function or "main"
        if (re.fullmatch(r"[A-Za-z_][\w.]*", module)
                and re.fullmatch(r"[A-Za-z_]\w*", function)):
            return ["-c", f"import sys; from {module} import {function} as main; "
                          "sys.exit(main())"], listed
    if candidates:
        return [candidates[0].replace("/", "\\")], listed
    return None, listed


def other_languages(paths):
    return sorted({LANGUAGES[Path(path).suffix.lower()] for path in paths
                   if Path(path).suffix.lower() in LANGUAGES})


def _run_detail(run, folder, command=None):
    stderr = text(run.stderr, folder)
    outcome, reason = classify(run, stderr)
    detail = {
        "outcome": outcome, "reason": reason, "exit_code": run.exit_code,
        "seconds": run.seconds, "cpu_seconds": run.cpu_seconds,
        "peak_memory_mb": run.peak_memory_mb, "processes": run.processes,
        "ended_by": run.cause, "memory_refused": run.memory_refused,
        "process_refused": run.process_refused,
        "stdout": text(run.stdout, folder), "stderr": stderr,
        "stdout_bytes": run.stdout_bytes, "stderr_bytes": run.stderr_bytes,
    }
    if command is not None:
        detail["command"] = command
    if outcome == "failed" and _asks_for_arguments(run.exit_code, stderr):
        detail["needs_arguments"] = True
    return detail


def _asks_for_arguments(exit_code, stderr):
    """Whether a failed run stopped for want of command-line arguments:
    argparse's or click's usage error, or an IndexError reading sys.argv."""
    lowered = stderr.lower()
    if exit_code == 2 and ("usage:" in lowered or "missing argument" in lowered):
        return True
    return "sys.argv[" in stderr and "IndexError" in stderr


def _read_json(folder, relative, limit=1 << 20):
    data = read_file(folder, relative, limit)
    if data is None:
        return None
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):  # written by untrusted code
        return None
    return value if isinstance(value, dict) else None


def _install_tools(box):
    """Copy the sandbox's helper scripts into the box, read-only to the
    sandboxed processes (they may read and run them, not change them), and
    make the folder the helpers write their results to."""
    from sandbox import win32

    tools = box.folder / "tools"
    tools.mkdir()
    for script in TOOLS.glob("*.py"):
        shutil.copyfile(script, tools / script.name)
    (tools / "empty-pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    user, read_execute = win32.user_sid().string, runtime.READ_EXECUTE
    win32.set_file_security(
        tools, f"D:P(A;OICI;FA;;;{user})(A;OICI;{read_execute};;;{box.package.string})"
               f"(A;OICI;{read_execute};;;{runtime.RESTRICTED_SID})")
    (box.folder / "out").mkdir()
    return tools


def _no_python(languages):
    return "no Python files" + (f"; found {', '.join(languages)}: {NOT_RUN}"
                                if languages else "")


def run_folder(source, paths=None, settings=Settings(), root=None):
    """Run the output whose files are under ``source`` (only ``paths``,
    relative and ``/`` separated, if given) and return the check detail."""
    from sandbox import tasks

    source = Path(source)
    if paths is None:
        paths = sorted(p.relative_to(source).as_posix() for p in source.rglob("*")
                       if p.is_file())
    detail = {"result": None, "reason": None, "files": len(paths),
              "settings": {"limits": asdict(settings.limits),
                           "command": list(settings.command) if settings.command else None,
                           "task": list(settings.task) if settings.task else None,
                           "clock": settings.clock, "scale_mb": settings.scale_mb}}
    languages = other_languages(paths)
    if languages:
        detail["languages"] = languages
    hook = tasks.hook_for(settings.task, settings.scale_mb)
    runnable = bool(settings.command or any(p.lower().endswith(".py") for p in paths))
    if not runnable and not (hook and hook.configs):
        detail.update(result="not-runnable", reason=_no_python(languages))
        return detail
    try:
        with Box(root, settings.limits) as box:
            if not box.complete:
                raise SandboxError("a box with a layer turned off cannot run outputs")
            detail["runtime"] = {"python": box.manifest["python"],
                                 "requirements_sha256": box.manifest["requirements_sha256"]}
            copy_files(source, paths, box.app)
            tools = _install_tools(box)
            if not runnable:
                detail["task"] = {"configs": tasks.parse_configs(box)}
                detail.update(result="not-runnable", reason=_no_python(languages)
                              + "; a workflow needs its build service, so its files "
                                "were only parse-checked")
                return detail
            survey_run = box.run([box.python(), "-I", str(tools / "survey.py"),
                                  str(box.app), str(box.folder / "out" / "survey.json")],
                                 limits=replace(settings.limits, seconds=60))
            survey = _read_json(box.folder, "out/survey.json")
            if survey is None or not isinstance(survey.get("files"), list):
                raise SandboxError("the survey of the files failed: "
                                   + text(survey_run.stderr, box.folder)[-300:])
            survey.setdefault("available", {})
            environment = hook.prepare(box, settings) if hook else {}
            if settings.clock:
                environment.update(tasks.clock_environment(settings.clock))
                if "SIBAR_SANDBOX_STUB" in environment:
                    environment["SIBAR_SANDBOX_SHIMS"] = "clock,stub"
            detail["environment"] = sorted(environment)
            _run_output(box, tools, survey, paths, settings, environment, detail,
                        hook.arguments if hook else ())
            if hook is not None:
                try:
                    detail["task"] = hook.measure(box, detail)
                except Exception as error:  # the runs' results still stand
                    detail["task"] = {"error": f"{type(error).__name__}: {error}"[:300]}
    except (SandboxError, runtime.RuntimeMissing, OSError) as error:
        detail.update(result="error", reason=f"{type(error).__name__}: {error}"[:500])
    return detail


def _missing_after(run_detail, missing):
    """The modules a failed run could not import that the sandbox lacks."""
    found = set(re.findall(r"No module named '([\w.]+)'", run_detail.get("stderr", "")))
    return sorted({name.split(".")[0] for name in found} & set(missing))


def _run_tests(box, tools, survey, paths, environment):
    tests = [entry["path"] for entry in survey["files"] if entry.get("test")]
    lacking = missing_modules(survey, paths, set(tests))
    if lacking:
        return {"ran": False, "reason": OUTSIDE_PACKAGES + ", ".join(lacking)}
    run = box.run([box.python(), str(tools / "pytest_json.py"),
                   str(box.folder / "out" / "tests.json"), str(box.app),
                   "--basetemp", str(box.home / "pytest")], environment=environment)
    summary = _read_json(box.folder, "out/tests.json") or {}
    return {"ran": True, **_summary(summary), "run": _run_detail(run, box.folder)}


def _run_entry(box, command, settings, environment, arguments):
    argv = [box.python() if command[0] == "python" else command[0]] + command[1:]
    run_detail = _run_detail(box.run(argv, environment=environment), box.folder, command)
    attempts = []
    # The tasks do not fix a command line: if the entry point asks for
    # arguments, try the ones the task's inputs suggest. A command given in
    # the settings is never second-guessed.
    for extra in (() if settings.command else arguments):
        if not run_detail.get("needs_arguments"):
            break
        attempts.append({"command": run_detail["command"],
                         "exit_code": run_detail["exit_code"]})
        run_detail = _run_detail(box.run(argv + list(extra), environment=environment),
                                 box.folder, command + list(extra))
    if attempts:
        run_detail["earlier_attempts"] = attempts
    return run_detail


def _run_output(box, tools, survey, paths, settings, environment, detail, arguments):
    syntax = [f"{entry['path']}: {entry['syntax_error']}" for entry in survey["files"]
              if "syntax_error" in entry]
    if syntax:
        detail["syntax_errors"] = syntax[:20]
    command = list(settings.command) if settings.command else None
    candidates = []
    if command is None and settings.entry:
        entry, candidates = choose_entry(survey, paths)
        command = ["python"] + entry if entry else None
    detail["candidates"] = candidates[:20]
    missing = missing_modules(survey, paths)
    detail["missing_modules"] = missing
    if settings.tests and any(entry.get("test") for entry in survey["files"]):
        detail["tests"] = _run_tests(box, tools, survey, paths, environment)
    if command and settings.entry:
        entry_files = None
        if len(command) > 1 and command[1].lower().endswith(".py"):
            entry_files = {command[1].replace("\\", "/")}
        lacking = missing_modules(survey, paths, entry_files) if entry_files else []
        if lacking:
            detail["entry"] = {"command": command, "ran": False}
            detail.update(result="not-runnable", reason=OUTSIDE_PACKAGES + ", ".join(lacking))
            return
        run_detail = _run_entry(box, command, settings, environment, arguments)
        detail["entry"] = run_detail
        detail.update(result=run_detail["outcome"], reason=run_detail["reason"])
        lacking = _missing_after(run_detail, missing) if run_detail["outcome"] == "failed" else []
        if lacking:
            detail.update(result="not-runnable", reason=OUTSIDE_PACKAGES + ", ".join(lacking))
        return
    tests = detail.get("tests")
    if tests and tests.get("ran"):
        run_detail = tests["run"]
        if run_detail["outcome"] == "failed" and tests.get("exit_code") == 1:
            # pytest's 1 means some tests failed: the tests themselves ran.
            detail.update(result="ran", reason="no entry point; the tests ran")
        else:
            detail.update(result=run_detail["outcome"],
                          reason=run_detail["reason"] or "no entry point; the tests ran")
    elif tests:
        detail.update(result="not-runnable", reason=tests["reason"])
    else:
        detail.update(result="not-runnable", reason="no entry point and no tests found"
                      + ("; syntax errors" if syntax else ""))


def _summary(found):
    keys = ("exit_code", "collected", "passed", "failed", "errors", "skipped",
            "xfailed", "xpassed", "seconds")
    summary = {key: found[key] for key in keys
               if isinstance(found.get(key), (int, float))
               and not isinstance(found.get(key), bool)}
    failures = found.get("failures")
    if isinstance(failures, list):
        summary["failures"] = [str(item)[:200] for item in failures[:20]]
    return summary


def check_outcome(detail):
    """The record's check outcome (ok, failed or error) for a detail."""
    result = detail.get("result")
    tests = detail.get("tests") or {}
    if result in ("not-runnable", "error", None):
        return "error"
    if result != "ran":
        return "failed"
    if tests.get("ran") and (tests.get("failed") or tests.get("errors")
                             or tests.get("exit_code") not in (0, 5, None)):
        return "failed"
    return "ok"
