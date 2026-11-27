"""What the runtime self-test (T2.7) allows and reports. The box is a fake, so
these run without a runtime; the real self-test runs in every setup."""

import pytest

from sandbox import box as boxes
from sandbox import runtime

WARNING = b"Failed to find real location of C:\\sibar\\.sandbox\\runtime\\python.exe\r\n"


def result(**changes):
    values = dict(exit_code=1, stdout=b"", stderr=WARNING, stdout_bytes=0,
                  stderr_bytes=len(WARNING), seconds=2.0, cpu_seconds=0.2,
                  peak_memory_mb=10, processes=1, cause=None, memory_refused=False,
                  process_refused=False, folder_mb=0.0)
    values.update(changes)
    return boxes.RunResult(**values)


@pytest.fixture
def self_test(monkeypatch, tmp_path):
    """``self_test(result)``: the self-test's answer when its run ends with
    ``result``; ``self_test.limits`` is then the limits it asked for."""

    def run(ended):
        class FakeBox:
            def __init__(self, root=None, limits=boxes.Limits(), **_):
                run.limits = limits

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def python(self):
                return "python.exe"

            def run(self, command, **_):
                return ended

        monkeypatch.setattr(boxes, "Box", FakeBox)
        return runtime.self_test(tmp_path)

    return run


def test_the_self_test_waits_longer_than_a_run_does(self_test):
    self_test(result())
    assert self_test.limits.seconds == 600


def test_a_self_test_ended_by_the_time_limit_says_so(self_test):
    problem = self_test(result(exit_code=91, cause="timeout", seconds=600.1,
                               cpu_seconds=0.8))
    assert "time limit" in problem
    assert "600" in problem and "0.8 s of CPU" in problem
    assert "memory" in problem  # what to do about it
    assert "real location" not in problem


def test_a_self_test_ended_by_another_limit_names_it(self_test):
    problem = self_test(result(exit_code=91, cause="writes"))
    assert "ended by the writes limit" in problem


def test_the_startup_warning_is_not_reported_as_the_error(self_test):
    problem = self_test(result(exit_code=3))
    assert problem == "exit code 3"


def test_the_error_of_a_failed_self_test_is_reported(self_test):
    stderr = WARNING + b"Traceback (most recent call last):\r\nImportError: no numpy\r\n"
    assert self_test(result(stderr=stderr)) == "exit code 1: ImportError: no numpy"
