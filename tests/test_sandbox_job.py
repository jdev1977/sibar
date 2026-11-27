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

# The interpreter itself: in a virtual environment ``sys.executable`` is a
# launcher that starts it as a second process.
PYTHON = getattr(sys, "_base_executable", sys.executable)


class Child:
    """``python -c code`` made inside ``job`` (so it is never outside it, even
    if this test dies at once), then let run. Its output is read from a
    pipe; with ``feed`` it reads its input from one."""

    def __init__(self, code, job, feed=False):
        import msvcrt

        from sandbox import win32

        self._win32 = win32
        out_read, out_write = win32.pipe()
        in_read = in_write = None
        null = win32.null_input()
        try:
            if feed:
                in_read, in_write = win32.pipe()
                os.set_handle_inheritable(in_read, True)
                os.set_handle_inheritable(in_write, False)
            self._process = win32.start(
                [PYTHON, "-I", "-S", "-c", code], os.getcwd(), dict(os.environ),
                job=job.handle, stdin=in_read or null, stdout=out_write, stderr=null)
        except BaseException:
            for handle in (out_read, in_write):
                win32.close(handle)
            raise
        finally:
            for handle in (out_write, in_read, null):
                win32.close(handle)
        self.stdout = os.fdopen(msvcrt.open_osfhandle(out_read, os.O_RDONLY), "rb")
        self.stdin = (os.fdopen(msvcrt.open_osfhandle(in_write, 0), "wb")
                      if feed else None)
        win32.resume(self._process)

    def wait(self, timeout):
        if not self._win32.wait(self._process.handle, timeout * 1000):
            raise subprocess.TimeoutExpired("child", timeout)
        return self._win32.exit_code(self._process.handle)

    def communicate(self, data=None, timeout=60):
        if self.stdin is not None:
            self.stdin.write(data or b"")
            self.stdin.close()
        out = self.stdout.read()
        self.wait(timeout)
        return out, b""

    def close(self):
        for stream in (self.stdin, self.stdout):
            if stream is not None:
                stream.close()
        self._process.close()

    __del__ = close


def start(code, job):
    """Start ``python -c code`` in ``job`` and let it run."""
    return Child(code, job)


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
    from sandbox import win32

    child = start("import subprocess, sys, time\n"
                  "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                  "print(g.pid, flush=True)\n"
                  "time.sleep(60)", job)
    grandchild = int(child.stdout.readline())
    held = win32.api().OpenProcess(win32.SYNCHRONIZE, False, grandchild)
    try:
        assert held and grandchild in job.process_ids()
        job.close()
        assert child.wait(timeout=10) != 0
        assert win32.wait(held, 10_000)
    finally:
        job.close()
        win32.close(held)


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
        child = Child(ATOM.replace("NAME", repr(name)), job, feed=True)
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
