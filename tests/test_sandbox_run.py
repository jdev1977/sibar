"""Running outputs in the sandbox and reading what happened (T2.7).

The first part needs no sandbox: it checks how runs are classified and how
the entry point is chosen. The rest runs small, bounded programs written
here in the sandbox. None contacts anything: the one that tries the network
aims at a closed port on 127.0.0.1, and the sandbox refuses the socket first.
"""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from sandbox.box import Limits, RunResult
from sandbox.run import (Settings, blocked_signs, check_outcome, choose_entry, classify,
                         local_modules, missing_modules, other_languages, run_folder,
                         text)


def result(**changes):
    values = dict(exit_code=0, stdout=b"", stderr=b"", stdout_bytes=0, stderr_bytes=0,
                  seconds=0.1, cpu_seconds=0.0, peak_memory_mb=10, processes=1, cause=None,
                  memory_refused=False, process_refused=False, folder_mb=0.0)
    values.update(changes)
    return RunResult(**values)


# --- Without the sandbox ---------------------------------------------------------------


@pytest.mark.parametrize("changes,stderr,expected", [
    ({}, "", "ran"),
    ({"exit_code": 1}, "Traceback ... ValueError", "failed"),
    ({"cause": "timeout", "exit_code": 91}, "", "timeout"),
    ({"cause": "cpu", "exit_code": 91}, "", "timeout"),
    ({"cause": "disk", "exit_code": 91}, "", "blocked"),
    ({"cause": "writes", "exit_code": 91}, "", "blocked"),
    ({"exit_code": 1, "memory_refused": True}, "", "memory"),
    ({"exit_code": 1}, "MemoryError", "memory"),
    ({"exit_code": 1}, "PermissionError: [WinError 10013] An attempt was made", "blocked"),
    ({"exit_code": 1}, "socket.gaierror: [Errno 11001] getaddrinfo failed", "blocked"),
    ({"exit_code": 1}, "PermissionError: [Errno 13] Permission denied: 'C:\\\\Users\\\\x'",
     "blocked"),
    ({"exit_code": 1}, "PermissionError: [Errno 13] Permission denied: '<folder>\\\\app\\\\x'",
     "failed"),
    ({"exit_code": 1, "process_refused": True}, "", "blocked"),
    ({"exit_code": 0, "memory_refused": True}, "", "ran"),
])
def test_classify(changes, stderr, expected):
    assert classify(result(**changes), stderr)[0] == expected


def test_blocked_signs_name_the_boundary():
    assert blocked_signs("OSError: [WinError 10013] An attempt") == ["network"]
    assert blocked_signs("PermissionError: [WinError 5] Access is denied: 'D:\\\\data'") == [
        "files outside the folder"]
    assert blocked_signs("ValueError: no") == []


def survey(*files, available=None, scripts=None):
    return {"files": list(files), "available": available or {}, "scripts": scripts or {}}


def test_entry_prefers_a_usual_name_then_a_main_guard():
    found = survey({"path": "helpers.py", "imports": []},
                   {"path": "tool.py", "main_guard": True, "imports": ["helpers"]},
                   {"path": "main.py", "main_guard": True, "imports": []},
                   {"path": "test_tool.py", "test": True, "main_guard": True})
    entry, candidates = choose_entry(found, ["helpers.py", "tool.py", "main.py"])
    assert entry == ["main.py"]
    assert candidates == ["main.py", "tool.py"]


def test_entry_a_package_main_or_a_console_script():
    package = survey({"path": "logagg/__init__.py"}, {"path": "logagg/__main__.py",
                                                      "runs_code": True},
                     {"path": "logagg/cli.py", "main_guard": False})
    assert choose_entry(package, [])[0] == ["-m", "logagg"]
    scripted = survey({"path": "src/logagg/cli.py", "imports": []},
                      scripts={"logagg": "logagg.cli:main"})
    entry, _ = choose_entry(scripted, [])
    assert entry[0] == "-c" and "from logagg.cli import main" in entry[1]


def test_entry_skips_imported_modules_and_files_with_syntax_errors():
    found = survey({"path": "lib.py", "runs_code": True},
                   {"path": "app2.py", "runs_code": True, "imports": ["lib"]},
                   {"path": "broken.py", "syntax_error": "line 1: invalid syntax"})
    assert choose_entry(found, [])[0] == ["app2.py"]
    assert choose_entry(survey({"path": "lib.py"}), [])[0] is None


def test_a_console_script_target_is_checked_before_use():
    scripted = survey(scripts={"x": "os; import evil:main"})
    assert choose_entry(scripted, [])[0] is None


def test_missing_modules_leave_out_the_runtime_and_the_output_itself():
    found = survey({"path": "app.py", "imports": ["numpy", "statsmodels", "mypkg", "util"]},
                   {"path": "other.py", "imports": ["seaborn"]},
                   available={"numpy": True, "statsmodels": False, "seaborn": False})
    paths = ["app.py", "other.py", "mypkg/__init__.py", "util.py"]
    assert local_modules(paths) >= {"app", "mypkg", "util"}
    assert missing_modules(found, paths) == ["seaborn", "statsmodels"]
    assert missing_modules(found, paths, {"app.py"}) == ["statsmodels"]


def test_text_is_cleaned_and_bounded():
    from sandbox import runtime

    folder = runtime.default_root() / "work" / "abc"
    raw = (f"Failed to find real location of {runtime.python(runtime.default_root())}\n"
           f"error in {folder}\\app\\x.py\r\n").encode() + b"\xff" + b"y" * 9000
    cleaned = text(raw, folder)
    assert "Failed to find" not in cleaned and "<folder>\\app\\x.py\n" in cleaned
    assert len(cleaned) < 4100 and "[...]" in cleaned


def test_other_languages_are_named():
    assert other_languages(["main.go", "a.ts", "README.md", "x.py"]) == ["Go", "TypeScript"]


@pytest.mark.parametrize("detail,expected", [
    ({"result": "ran"}, "ok"),
    ({"result": "ran", "tests": {"ran": True, "failed": 1, "exit_code": 1}}, "failed"),
    ({"result": "ran", "tests": {"ran": True, "failed": 0, "exit_code": 0}}, "ok"),
    ({"result": "ran", "tests": {"ran": True, "exit_code": 5}}, "ok"),
    ({"result": "timeout"}, "failed"),
    ({"result": "blocked"}, "failed"),
    ({"result": "not-runnable"}, "error"),
    ({"result": "error"}, "error"),
])
def test_check_outcome(detail, expected):
    assert check_outcome(detail) == expected


def test_no_python_is_not_runnable_without_a_sandbox(tmp_path):
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    detail = run_folder(tmp_path)
    assert detail["result"] == "not-runnable"
    assert "Go" in detail["reason"] and "only Python" in detail["reason"]


# --- In the sandbox ---------------------------------------------------------------------

SMALL = Limits(seconds=40, cpu_seconds=40, memory_mb=512, processes=8, disk_mb=64,
               free_disk_mb=512)


@pytest.fixture
def output(tmp_path):
    from sandbox_support import require_runtime

    require_runtime()

    def make(files, **settings):
        folder = tmp_path / "output"
        for name, content in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return run_folder(folder, settings=Settings(limits=settings.pop("limits", SMALL),
                                                    **settings))
    return make


@pytest.mark.sandbox
def test_a_program_that_works_ran(output):
    detail = output({"main.py": "print('hello from the sandbox')\n"})
    assert detail["result"] == "ran", detail
    assert detail["entry"]["stdout"] == "hello from the sandbox\n"
    assert detail["entry"]["command"] == ["python", "main.py"]
    assert check_outcome(detail) == "ok"


@pytest.mark.sandbox
def test_a_program_that_raises_failed(output):
    detail = output({"main.py": "raise ValueError('bad input')\n"})
    assert detail["result"] == "failed"
    assert "ValueError: bad input" in detail["entry"]["stderr"]


@pytest.mark.sandbox
def test_a_program_that_never_ends_timed_out(output):
    detail = output({"main.py": "import time\ntime.sleep(100)\n"},
                    limits=replace(SMALL, seconds=3))
    assert detail["result"] == "timeout"
    assert detail["entry"]["ended_by"] == "timeout"


@pytest.mark.sandbox
def test_a_program_that_wants_too_much_memory(output):
    code = "blocks = [bytearray(64 << 20) for _ in range(8)]\n"
    detail = output({"main.py": code}, limits=replace(SMALL, memory_mb=128))
    assert detail["result"] == "memory", detail["entry"]


@pytest.mark.sandbox
def test_a_program_that_needs_the_network_is_blocked(output):
    code = ("import urllib.request\n"
            "urllib.request.urlopen('http://127.0.0.1:9/', timeout=3)\n")
    detail = output({"main.py": code})
    assert detail["result"] == "blocked", detail["entry"]["stderr"]
    assert "network" in detail["reason"]


@pytest.mark.sandbox
def test_a_module_outside_the_package_set_is_not_runnable(output):
    detail = output({"main.py": "import statsmodels.api as sm\nprint(sm)\n"})
    assert detail["result"] == "not-runnable"
    assert "statsmodels" in detail["reason"]
    assert detail["missing_modules"] == ["statsmodels"]


@pytest.mark.sandbox
def test_a_missing_module_in_a_local_module_is_found_after_the_run(output):
    detail = output({"main.py": "import helpers\nhelpers.go()\n",
                     "helpers.py": "import seaborn\ndef go(): pass\n"})
    assert detail["result"] == "not-runnable", detail
    assert "seaborn" in detail["reason"]


@pytest.mark.sandbox
def test_tests_are_run_and_counted(output):
    detail = output({"calc.py": "def add(a, b):\n    return a + b\n",
                     "test_calc.py": ("from calc import add\n"
                                      "def test_add():\n    assert add(1, 2) == 3\n"
                                      "def test_wrong():\n    assert add(1, 1) == 3\n")})
    tests = detail["tests"]
    assert tests["ran"] and tests["passed"] == 1 and tests["failed"] == 1
    assert tests["failures"] == ["test_calc.py::test_wrong"]
    assert detail["result"] == "ran"  # no entry point; the tests ran
    assert check_outcome(detail) == "failed"


@pytest.mark.sandbox
def test_unittest_tests_run_too(output):
    detail = output({"test_unit.py": ("import unittest\n"
                                      "class T(unittest.TestCase):\n"
                                      "    def test_ok(self):\n        self.assertTrue(True)\n")})
    assert detail["tests"]["passed"] == 1
    assert check_outcome(detail) == "ok"


@pytest.mark.sandbox
def test_a_given_command_is_used(output):
    detail = output({"tool.py": "import sys\nprint(sys.argv[1:])\n"},
                    command=("python", "tool.py", "--day", "2027-03-02"))
    assert detail["entry"]["stdout"].strip() == "['--day', '2027-03-02']"


@pytest.mark.sandbox
def test_ordinary_python_works_in_the_sandbox(output):
    code = """
import asyncio, multiprocessing, os, pathlib, sqlite3, subprocess, sys, tempfile
import sqlalchemy

def square(x):
    return x * x

async def later():
    await asyncio.sleep(0.01)
    return await asyncio.get_running_loop().run_in_executor(None, sum, [1, 2])

if __name__ == "__main__":
    with multiprocessing.Pool(2) as pool:
        assert pool.map(square, [1, 2, 3]) == [1, 4, 9]
    assert asyncio.run(later()) == 3
    engine = sqlalchemy.create_engine("sqlite:///orders.db")
    with engine.begin() as connection:
        connection.execute(sqlalchemy.text("create table t (x)"))
    assert subprocess.run([sys.executable, "-c", "print(1)"], capture_output=True,
                          stdin=subprocess.DEVNULL).stdout.strip() == b"1"
    assert pathlib.Path(".").resolve() == pathlib.Path(os.getcwd())
    with tempfile.TemporaryDirectory() as folder:
        pathlib.Path(folder, "x").write_text("x")
    import matplotlib.pyplot as plt
    plt.plot([1, 2]); plt.savefig("plot.png")
    print("all fine")
"""
    detail = output({"main.py": code})
    assert detail["result"] == "ran", detail["entry"]["stderr"]
    assert detail["entry"]["stdout"].strip() == "all fine"


@pytest.mark.sandbox
def test_only_a_workflow_is_parse_checked(output):
    workflow = ("name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
                "    steps:\n      - run: go test ./...\n")
    detail = output({".github/workflows/ci.yml": workflow, "broken.yaml": "a: [b\n"},
                    task=("pipeline", "ci-workflow", "L2"))
    assert detail["result"] == "not-runnable"
    configs = {item["path"]: item for item in detail["task"]["configs"]}
    assert configs[".github/workflows/ci.yml"]["parses"]
    assert configs[".github/workflows/ci.yml"]["commands"] == ["go test ./..."]
    assert not configs["broken.yaml"]["parses"]


def test_setup_and_tool_configuration_files_are_not_entry_points():
    found = survey({"path": "setup.py", "runs_code": True},
                   {"path": "docs/conf.py", "runs_code": True},
                   {"path": "conftest.py", "runs_code": True})
    assert choose_entry(found, [])[0] is None


@pytest.mark.sandbox
def test_the_entry_runs_before_the_tests(output):
    detail = output({"main.py": "open('order.txt', 'a').write('entry ')\n",
                     "test_order.py": ("def test_after():\n"
                                       "    assert open('order.txt').read() == 'entry '\n")})
    assert detail["tests"]["passed"] == 1, detail["tests"]


@pytest.mark.sandbox
def test_a_failed_survey_says_how_it_ended(output, monkeypatch):
    # On a busy machine the sandbox's low-priority processes can be starved
    # until the clock ends them, leaving no error output.
    from sandbox.box import Box

    real = Box.run

    def starved(self, argv, *args, **kwargs):
        if any(str(part).endswith("survey.py") for part in argv):
            return result(exit_code=0x5B, cause="timeout", seconds=60.0)
        return real(self, argv, *args, **kwargs)

    monkeypatch.setattr(Box, "run", starved)
    detail = output({"main.py": "print(1)\n"})
    assert detail["result"] == "error"
    assert "exit code 91, ended by timeout, after 60.0 s" in detail["reason"]
    assert "result file missing" in detail["reason"] and "no error output" in detail["reason"]
