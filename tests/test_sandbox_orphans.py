"""No sandboxed process outlives the process that started it.

Each kill test starts a creator: a bounded helper process (this repository's
own code) that opens a box, starts a suspended child in it the way the
sandbox does, says the child's id and waits (at most 60 s). The test holds the
child, kills the creator at that moment, as a crash would, and checks that the
child ends with it. Whatever happens, the test ends the child itself and a
new box removes what the creator left (its profile and working folder).
"""

import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from pathlib import Path

import pytest

from sandbox_support import SMALL, require_runtime

pytestmark = pytest.mark.sandbox
ROOT = Path(__file__).resolve().parents[1]
# The interpreter itself: in a virtual environment ``sys.executable`` is a
# launcher, and killing it would leave the real creator running.
PYTHON = getattr(sys, "_base_executable", sys.executable)
SYNCHRONIZE, TERMINATE, QUERY_LIMITED = 0x00100000, 0x0001, 0x1000


@pytest.fixture(autouse=True)
def runtime():
    require_runtime()


CREATOR = r'''
import sys, time
from sandbox import win32
from sandbox.box import Box
from sandbox.job import JobObject
from sandbox_support import SMALL


def say(pid):
    print(pid, flush=True)
    time.sleep(60)  # the test kills this process here
    sys.exit(3)


with Box(limits=SMALL) as box:
    if sys.argv[1] == "start":
        # As the token test starts its children.
        handles = [win32.null_input(), *win32.pipe()]
        job = JobObject()
        process = win32.start([box.python(), "-c", "pass"], box.app, box.environment(),
                              token=box._token, package=box.package,
                              capabilities=box._capabilities, job=job.handle,
                              stdin=handles[0], stdout=handles[2], stderr=handles[2],
                              desktop=box._desktop.path)
        say(process.pid)
    else:
        # Box.run, stopped after the child is made and before it is checked.
        import ctypes
        process_id = ctypes.WinDLL("kernel32").GetProcessId
        process_id.argtypes = [ctypes.c_void_p]
        win32.in_job = lambda process, job: say(process_id(process))
        box.run([box.python(), "-c", "pass"])
'''


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    return kernel


def _image(kernel, handle):
    buffer = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buffer))
    assert kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
    return buffer.value


@pytest.mark.parametrize("way", ["start", "run"])
def test_a_suspended_child_ends_when_its_creator_is_killed(tmp_path, way):
    from sandbox import runtime
    from sandbox.box import Box

    script = tmp_path / "creator.py"
    script.write_text(CREATOR, encoding="utf-8")
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    creator = subprocess.Popen([PYTHON, str(script), way], cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    kernel, child, ended = _kernel(), None, False
    watchdog = threading.Timer(90, creator.kill)
    watchdog.start()
    try:
        line = creator.stdout.readline()
        assert line.strip().isdigit(), (line, creator.stderr.read()[-2000:] if
                                        creator.poll() is not None else b"")
        child = kernel.OpenProcess(SYNCHRONIZE | TERMINATE | QUERY_LIMITED, False,
                                   int(line))
        assert child, ctypes.get_last_error()
        image = Path(_image(kernel, child))
        assert image.parent == runtime.runtime_dir(runtime.default_root())
        creator.kill()  # as a crash would: no cleanup runs in the creator
        creator.wait(30)
        ended = kernel.WaitForSingleObject(child, 5000) == 0
    finally:
        watchdog.cancel()
        if creator.poll() is None:
            creator.kill()
            creator.wait(30)
        creator.stdout.close()
        creator.stderr.close()
        if child:
            if not ended:
                kernel.TerminateProcess(child, 1)
                kernel.WaitForSingleObject(child, 5000)
            kernel.CloseHandle(child)
        with Box(limits=SMALL) as box:  # removes the creator's profile and folder
            pass
    assert ended, "the child outlived its creator"
    assert not box.left


def test_no_process_is_started_outside_a_job(tmp_path):
    from sandbox import win32

    stdin = win32.null_input()
    try:
        with pytest.raises(ValueError, match="job"):
            # A program that does not exist: nothing could start even if the
            # check were missing.
            win32.start([str(tmp_path / "missing.exe")], tmp_path, dict(os.environ),
                        job=None, stdin=stdin, stdout=stdin, stderr=stdin)
    finally:
        win32.close(stdin)


def test_sweep_ends_leftover_processes_of_the_runtime_and_nothing_else(tmp_path):
    from runner.ledger import lock_file, unlock_file
    from sandbox import runtime, win32
    from sandbox.box import Box, _inside, sweep
    from sandbox.job import JobObject

    root = runtime.default_root()
    job = JobObject()  # holds them all, so none can outlive this test
    stdin = win32.null_input()
    made = []
    try:
        # One as a box makes it (AppContainer, restricted token, own desktop),
        # left when its box closed; one of the runtime's python started
        # plainly; and the bystander, the same program from elsewhere.
        with Box(limits=SMALL) as box:
            made.append(win32.start([box.python(), "-c", "pass"], box.app,
                                    box.environment(), token=box._token,
                                    package=box.package, capabilities=box._capabilities,
                                    job=job.handle, stdin=stdin, stdout=stdin,
                                    stderr=stdin, desktop=box._desktop.path))
        for program in (str(runtime.python(root)), PYTHON):
            made.append(win32.start([program, "-I", "-S", "-c", "pass"], tmp_path,
                                    dict(os.environ), job=job.handle, stdin=stdin,
                                    stdout=stdin, stderr=stdin))
        *leftovers, bystander = made
        lock = lock_file(root / "sandbox.lock")
        try:
            removed, problems = sweep(root)
        finally:
            unlock_file(lock)
        assert problems == []
        for leftover in leftovers:
            assert win32.wait(leftover.handle, 5000)
            assert f"process {leftover.pid} (python.exe)" in removed
        assert not win32.wait(bystander.handle, 0)  # not the runtime's: untouched
    finally:
        job.close()
        for process in made:
            process.close()
        win32.close(stdin)
    runtime_folder = Path(r"C:\x\runtime")
    assert _inside(r"C:\x\RUNTIME\python.exe", runtime_folder)
    assert not _inside(r"C:\x\runtime.new\python.exe", runtime_folder)
    assert not _inside(r"C:\x\runtime", runtime_folder)
