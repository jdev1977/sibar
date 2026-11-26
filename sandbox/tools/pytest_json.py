"""Runs an output's tests inside the sandbox and writes a summary (T2.7).

``python pytest_json.py <result file> <test folder> [pytest arguments]``,
started in the output's folder. The output's own code (its tests and any
conftest.py) runs in this process, so the summary is only as honest as that
code: it is what the output's tests report, not a verified result.
"""

import json
import sys
import time

MAX_LISTED = 20


class Summary:
    def __init__(self):
        self.counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                       "xfailed": 0, "xpassed": 0}
        self.collected = 0
        self.failures = []

    def pytest_collection_finish(self, session):
        self.collected = len(session.items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.counts["errors"] += 1
            if len(self.failures) < MAX_LISTED:
                self.failures.append(str(report.nodeid)[:200] or "(collection)")

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if hasattr(report, "wasxfail"):
                self.counts["xfailed" if report.skipped else "xpassed"] += 1
            elif report.passed:
                self.counts["passed"] += 1
            elif report.failed:
                self.counts["failed"] += 1
                if len(self.failures) < MAX_LISTED:
                    self.failures.append(str(report.nodeid)[:200])
            elif report.skipped:
                self.counts["skipped"] += 1
        elif report.failed:  # setup or teardown
            self.counts["errors"] += 1
            if len(self.failures) < MAX_LISTED:
                self.failures.append(f"{str(report.nodeid)[:180]} ({report.when})")
        elif report.when == "setup" and report.skipped:
            self.counts["skipped"] += 1


def config_file(folder):
    """The output's own pytest configuration, else an empty one. Named
    explicitly so that pytest does not look for one in the folders above,
    which the sandbox may not read."""
    import os

    for name in ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"):
        if os.path.isfile(os.path.join(folder, name)):
            return os.path.join(folder, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "empty-pytest.ini")


def main():
    result, folder, extra = sys.argv[1], sys.argv[2], sys.argv[3:]
    import pytest

    summary = Summary()
    started = time.monotonic()
    code = pytest.main(["-q", "-p", "no:cacheprovider", "-o", "addopts=",
                        "-c", config_file(folder), "--rootdir", folder,
                        "--confcutdir", folder, folder] + extra, plugins=[summary])
    with open(result, "w", encoding="utf-8") as handle:
        json.dump({"exit_code": int(code), "collected": summary.collected,
                   **summary.counts, "failures": summary.failures,
                   "seconds": round(time.monotonic() - started, 3)}, handle)
    sys.exit(int(code))


if __name__ == "__main__":
    main()
