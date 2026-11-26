"""The job object shared by the sandbox and the renderer (T2.7).

The child processes here are this test's own, small and bounded: each stops
by itself well before it could hurt the machine, whether or not the limit
under test works.
"""

import os
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="job objects are Windows only")

from sandbox.job import JobLimits, JobObject  # noqa: E402

CHILD_FLAGS = 0x4  # CREATE_SUSPENDED
# The interpreter itself: in a virtual environment ``sys.executable`` is a
# launcher that starts it as a second process.
PYTHON = getattr(sys, "_base_executable", sys.executable)


def start(code, job):
    """Start ``python -c code`` suspended, put it in ``job``, let it run."""
    child = subprocess.Popen([PYTHON, "-I", "-S", "-c", code],
                             creationflags=CHILD_FLAGS, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    job.assign_handle(int(child._handle))
    _resume(child.pid)
    return child


def _resume(pid):
    import ctypes
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x0800, False, pid)  # PROCESS_SUSPEND_RESUME
    assert handle, ctypes.get_last_error()
    try:
        ntdll.NtResumeProcess(wintypes.HANDLE(handle))
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def wait_empty(job, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job.poll(100)
        if job.empty:
            return
    raise AssertionError("the job's processes did not end")


# Allocates 16 MB at a time, at most 384 MB, then says how far it got.
ALLOCATE = """
blocks = []
try:
    for _ in range(24):
        blocks.append(bytearray(16 << 20))
    print("all", len(blocks))
except MemoryError:
    print("refused", len(blocks))
"""


def test_memory_cap_refuses_memory_and_records_the_peak():
    job = JobObject(JobLimits(memory_bytes=96 << 20))
    try:
        child = start(ALLOCATE, job)
        out, _ = child.communicate(timeout=60)
        wait_empty(job)
        assert out.split()[0] == b"refused"
        assert job.memory_refused
        assert 0 < job.accounting().peak_memory_bytes <= (96 + 16) << 20
    finally:
        job.close()


def test_without_a_cap_the_child_gets_all_it_asks_for():
    job = JobObject(JobLimits())
    try:
        child = start(ALLOCATE, job)
        out, _ = child.communicate(timeout=60)
        assert out.split()[0] == b"all"
        assert not job.memory_refused
    finally:
        job.close()


# Starts up to 12 sleeping children at once, then says how many started.
SPAWN = """
import subprocess, sys
children, refused = [], 0
for _ in range(12):
    try:
        children.append(subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", "import time; time.sleep(3)"]))
    except OSError:
        refused += 1
print(len(children), refused)
for child in children:
    child.wait()
"""


def test_process_limit_refuses_processes_past_the_limit():
    job = JobObject(JobLimits(processes=4))
    try:
        child = start(SPAWN, job)
        out, _ = child.communicate(timeout=60)
        started, refused = map(int, out.split())
        job.poll()
        assert started <= 3 and refused >= 9
        assert job.process_refused
        assert job.accounting().total_processes <= 4 + refused
    finally:
        job.close()


def test_closing_the_job_kills_every_process_in_it():
    job = JobObject(JobLimits())
    child = start("import subprocess, sys, time\n"
                  "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                  "time.sleep(60)", job)
    time.sleep(1.0)
    assert job.accounting().active_processes == 2
    job.close()
    assert child.wait(timeout=10) != 0


def test_cpu_time_limit_ends_the_job():
    job = JobObject(JobLimits(cpu_seconds=1.0))
    try:
        started = time.monotonic()
        child = start("import time\nend = time.time() + 20\n"
                      "while time.time() < end: pass", job)
        child.wait(timeout=30)
        wait_empty(job)
        assert time.monotonic() - started < 15
        assert job.cpu_exceeded
    finally:
        job.close()


def test_bytes_written_are_counted(tmp_path):
    target = tmp_path / "big.bin"
    job = JobObject(JobLimits())
    try:
        child = start(f"f = open({str(target)!r}, 'wb')\n"
                      "for _ in range(8):\n"
                      "    f.write(bytes(1 << 20)); f.flush()\n", job)
        child.wait(timeout=30)
        wait_empty(job)
        assert job.accounting().write_bytes >= 8 << 20
    finally:
        job.close()


# Adds a global atom, says whether it worked, waits, then removes it. The
# atom table is the session's: nothing else on the machine is touched.
ATOM = """
import ctypes
k = ctypes.WinDLL("kernel32")
atom = k.GlobalAddAtomW(NAME)
print(atom != 0, flush=True)
input()
k.GlobalDeleteAtom(atom)
"""


@pytest.mark.parametrize("restricted", [True, False])
def test_ui_restrictions_give_the_job_its_own_atoms(restricted):
    import ctypes
    import uuid

    name = f"sibar-test-{uuid.uuid4().hex}"
    job = JobObject(JobLimits(ui_restricted=restricted))
    try:
        child = subprocess.Popen(
            [PYTHON, "-I", "-S", "-c", ATOM.replace("NAME", repr(name))],
            creationflags=CHILD_FLAGS, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        job.assign_handle(int(child._handle))
        _resume(child.pid)
        assert child.stdout.readline().strip() == b"True"
        seen = ctypes.WinDLL("kernel32").GlobalFindAtomW(name) != 0
        child.communicate(b"\n", timeout=30)
        assert seen is not restricted
    finally:
        job.close()


def test_bad_limits_are_refused():
    with pytest.raises(ValueError):
        JobLimits(processes=0)
    with pytest.raises(ValueError):
        JobLimits(cpu_percent=101)
