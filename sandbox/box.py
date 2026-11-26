"""One sandbox: a fresh AppContainer, working folder and desktop, in which
untrusted code runs under limits. See docs/sandbox.md for the threat model.

A :class:`Box` is built from these layers, each of which fails closed (if
Windows refuses one, the box is not built and nothing runs):

- **Less privileged AppContainer (LPAC).** A new AppContainer profile per box,
  with no network capability: the process cannot make a socket at all, so no
  TCP, UDP, DNS or loopback. It may open only objects granted to its own
  package SID or its capabilities: the sandbox's runtime capability (granted
  only by the runtime folder) and ``registryRead`` (Windows needs it to start
  Python; it grants read access to system configuration in the registry).
  Its integrity level is low, so it can write nothing labelled higher.
- **Restricted token.** The process runs on a restricted copy of the user's
  token with no privileges, administrators deny-only, and every access
  checked a second time against four SIDs only: Everyone, Users, the logon
  session and the sandbox's restricted SID. This shuts out what
  ``registryRead`` would otherwise open, such as the user's registry hive,
  which holds the user's environment variables.
- **A window station and desktop of its own.** Another clipboard, other
  atoms, no view of the user's windows or screen.
- **A job object per run** (``sandbox.job``): memory, processes at once,
  user-mode CPU time, a CPU rate cap, low priority, UI restrictions, no crash
  dialogs, and every process killed when the run ends.
- **Watching from outside**: wall-clock time, bytes written, the size and
  file count of the working folder and the free space on its drive.
- **A clean environment**: only the variables set here, none copied from
  this process's environment.

The working folder is the only place the process may write. Its DACL grants
modify to the box's package SID and the restricted SID, full control to the
user (for cleanup), and nothing inherited; its low label lets the process
write in it. :meth:`Box.close` deletes the profile, the desktop, the token
and the folder; profiles and folders left by a run that crashed are removed
by the next box.
"""

import os
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

from runner.ledger import LedgerError, lock_file, unlock_file
from sandbox import runtime
from sandbox.files import remove_tree, usage
from sandbox.job import JobLimits, JobObject

PROFILE_PREFIX = "sibar.sb."
EVERYONE, USERS, ADMINISTRATORS = "S-1-1-0", "S-1-5-32-545", "S-1-5-32-544"
MODIFY = "0x1301bf"  # read, write, execute and delete; not WRITE_DAC
CAPABILITIES = (runtime.RUNTIME_CAPABILITY, "registryRead")
MAX_ENTRIES = 20_000  # files and folders in a working folder
DISK_CHECK_SECONDS = 0.1
END_GRACE_SECONDS = 10.0
KILLED = 0x5B  # exit code of processes the sandbox ends
CUT = b"\n[... cut by the sandbox ...]\n"
# Names the caller of Box.run may not set: the sandbox owns them.
OWNED_VARIABLES = frozenset({
    "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "LOCALAPPDATA", "APPDATA",
    "USERPROFILE", "HOME", "TEMP", "TMP", "USERNAME", "USERDOMAIN", "COMPUTERNAME",
    "PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONSAFEPATH",
})

_OPEN = set()  # profile names of boxes open in this process


class SandboxError(Exception):
    """The sandbox could not be built or used; nothing ran, or the run was
    ended. The message says why."""


@dataclass(frozen=True)
class Limits:
    """Limits of one run (one process tree). The defaults suit a machine with
    little free memory and disk."""

    seconds: float = 60.0  # wall clock
    cpu_seconds: float = 60.0  # user-mode CPU, all processes together
    memory_mb: int = 1024  # committed memory, all processes together
    processes: int = 16  # alive at once
    disk_mb: int = 256  # size of the working folder
    files: int = 10_000  # files and folders in the working folder
    write_mb: int = 2048  # bytes written through any handle, files and pipes
    output_bytes: int = 64 << 10  # of stdout and of stderr kept, head and tail
    cpu_percent: int = 50  # hard cap on the CPU rate, of all cores
    free_disk_mb: int = 1024  # the run ends if the drive gets fuller than this

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{item.name}: a number above 0, not {value!r}")
        if self.cpu_percent > 100:
            raise ValueError(f"cpu_percent: at most 100, not {self.cpu_percent}")
        if self.files > MAX_ENTRIES:
            raise ValueError(f"files: at most {MAX_ENTRIES}, not {self.files}")


@dataclass(frozen=True)
class Isolation:
    """Which layers are on. All are, always, except in the tests that prove
    each boundary by showing their probe gets through when it is off. A box
    with any layer off says so (:attr:`Box.complete`), and its results are
    never stored in a record."""

    appcontainer: bool = True
    restricted_token: bool = True
    desktop: bool = True
    job_limits: bool = True
    watch: bool = True

    @property
    def complete(self):
        return all(getattr(self, item.name) for item in fields(self))


@dataclass(frozen=True)
class RunResult:
    exit_code: Optional[int]
    stdout: bytes  # the head and the tail, if it was longer than kept
    stderr: bytes
    stdout_bytes: int  # all that was written
    stderr_bytes: int
    seconds: float
    cpu_seconds: float
    peak_memory_mb: int
    processes: int  # started in all
    cause: Optional[str]  # what ended it, or None: it ended by itself
    memory_refused: bool  # the memory limit refused some memory
    process_refused: bool  # the process limit refused some process
    folder_mb: float  # size of the working folder when it ended


class _Capture:
    """Reads a pipe to its end, keeping the first and last ``keep`` bytes."""

    def __init__(self, handle, keep):
        from sandbox import win32

        self._handle, self._keep, self._win32 = handle, keep, win32
        self.head, self.tail, self.total = bytearray(), bytearray(), 0
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self):
        while True:
            data = self._win32.read(self._handle)
            if not data:
                return
            self.total += len(data)
            room = self._keep - len(self.head)
            if room > 0:
                self.head += data[:room]
                data = data[room:]
            if data:
                self.tail += data
                del self.tail[:-self._keep]

    def finish(self, seconds):
        self._thread.join(seconds)
        if self._thread.is_alive():
            return bytes(self.head) + CUT  # a writer outlived the job: give up
        if self.total > len(self.head) + len(self.tail):
            return bytes(self.head) + CUT + bytes(self.tail)
        return bytes(self.head) + bytes(self.tail)


def _windows_folder():
    import ctypes

    buffer = ctypes.create_unicode_buffer(260)
    if not ctypes.windll.kernel32.GetSystemWindowsDirectoryW(buffer, 260):
        raise SandboxError("cannot find the Windows folder")
    return buffer.value


def _end_all(job):
    """Kill every process in ``job`` and wait until each has fully ended (a
    process the job no longer counts may still hold files open for a moment).
    Returns how many could not be seen to end."""
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    deadline = time.monotonic() + END_GRACE_SECONDS
    waiting = {}
    try:
        while True:
            # Hold each process before killing it, so its id cannot be reused.
            for pid in job.process_ids():
                if pid not in waiting:
                    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                    if handle:
                        waiting[pid] = handle
            job.terminate(KILLED)
            for pid, handle in list(waiting.items()):
                rest = max(0, int((deadline - time.monotonic()) * 1000))
                if kernel.WaitForSingleObject(ctypes.c_void_p(handle), rest) == 0:
                    kernel.CloseHandle(ctypes.c_void_p(handle))
                    del waiting[pid]
            active = job.accounting().active_processes
            if (not active and not waiting) or time.monotonic() >= deadline:
                return max(active, len(waiting))
            time.sleep(0.02)
    finally:
        for handle in waiting.values():
            kernel.CloseHandle(ctypes.c_void_p(handle))


def _alive(pid):
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return ctypes.get_last_error() != 87  # 87: no such process
    try:
        return kernel.WaitForSingleObject(ctypes.c_void_p(handle), 0) != 0
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def sweep(root):
    """Remove what earlier boxes left behind: AppContainer profiles of this
    sandbox whose process is gone, and working folders under ``root`` (call
    only with ``root``'s lock held). Returns what was removed."""
    from sandbox import win32

    removed = []
    for name in win32.profile_names():
        if not name.startswith(PROFILE_PREFIX) or name in _OPEN:
            continue
        pid_text = name[len(PROFILE_PREFIX):].partition("-")[0]
        if pid_text.isdigit() and int(pid_text) != os.getpid() and _alive(int(pid_text)):
            continue
        win32.delete_profile(name)
        removed.append(f"profile {name}")
    work = Path(root) / "work"
    if work.is_dir():
        for child in work.iterdir():
            remove_tree(child)
            removed.append(f"folder {child.name}")
    return removed


class Box:
    """A sandbox for one output. Use as a context manager; :meth:`run`
    commands in it, then read what they wrote under :attr:`folder`."""

    def __init__(self, root=None, limits=Limits(), isolation=Isolation()):
        self.root = Path(root or runtime.default_root()).resolve()
        self.limits, self.isolation = limits, isolation
        self.complete = isolation.complete
        self.name = self.folder = self.package = None
        self._lock = self._token = self._desktop = None
        self._profile = False
        self.removed = []

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exception):
        self.close()

    # --- building -------------------------------------------------------------------

    def open(self):
        if os.name != "nt":
            raise SandboxError("the sandbox runs on Windows only")
        from sandbox import win32

        self.manifest = runtime.check(self.root)
        try:
            self._lock = lock_file(self.root / "sandbox.lock")
        except LedgerError:
            raise SandboxError(f"another sandbox run is using {self.root}") from None
        try:
            self.removed = sweep(self.root)
            free = shutil.disk_usage(self.root).free >> 20
            if free < self.limits.free_disk_mb + self.limits.disk_mb:
                raise SandboxError(f"only {free} MB free on the drive of {self.root}")
            run_id = secrets.token_hex(4)
            self.name = f"{PROFILE_PREFIX}{os.getpid()}-{run_id}"
            _OPEN.add(self.name)
            self.folder = self.root / "work" / run_id
            self.folder.mkdir(parents=True)
            user = win32.user_sid().string
            if self.isolation.appcontainer:
                self.package = win32.create_profile(self.name)
                self._profile = True
                self._strip_profile()
            else:
                self.package = win32.appcontainer_sid(self.name)
            package = self.package.string
            restricted = runtime.RESTRICTED_SID
            win32.set_file_security(
                self.folder, f"D:P(A;OICI;FA;;;{user})(A;OICI;{MODIFY};;;{package})"
                             f"(A;OICI;{MODIFY};;;{restricted})", low_label=True)
            self.app = self.folder / "app"
            self.home = self.folder / "home"
            local = self.folder / "l"
            # Windows sets TEMP for an AppContainer under LOCALAPPDATA.
            self.temp = local / "Packages" / self.name / "AC" / "Temp"
            for folder in (self.app, self.home, self.temp, self.home / "roaming",
                           self.home / ".matplotlib"):
                folder.mkdir(parents=True, exist_ok=True)
            for cached in runtime.font_cache(self.root).glob("fontlist-*.json"):
                shutil.copyfile(cached, self.home / ".matplotlib" / cached.name)
            self._local = local
            if self.isolation.desktop:
                self._desktop = win32.Desktop(
                    f"sibar-{run_id}", f"D:P(A;;GA;;;{user})(A;;GA;;;SY)"
                                       f"(A;;GA;;;{package})(A;;GA;;;{restricted})",
                    {user, "SY", package, restricted})
            if self.isolation.restricted_token:
                self._token = win32.restricted_token(
                    [win32.Sid.parse(restricted), win32.Sid.parse(EVERYONE),
                     win32.Sid.parse(USERS), win32.logon_sid()],
                    [win32.Sid.parse(ADMINISTRATORS)],
                    f"D:(A;;GA;;;{user})(A;;GA;;;SY)(A;;GA;;;{restricted})"
                    f"(A;;GA;;;{package})")
            self._capabilities = [win32.capability_sid(name) for name in CAPABILITIES]
        except BaseException:
            try:
                self.close()
            except SandboxError:
                pass
            raise

    def _strip_profile(self):
        """Delete the folder and registry key Windows made with the profile:
        the container could write to both."""
        from sandbox import win32

        folder = Path(win32.profile_folder(self.package)).parent
        if folder.name.lower() != self.name.lower() or folder.parent.name.lower() != "packages":
            raise SandboxError(f"unexpected AppContainer folder {folder}")
        if folder.exists():
            remove_tree(folder)
        win32.delete_storage_key(self.name)

    def environment(self, extra=None):
        """The whole environment of a sandboxed process: nothing is copied
        from this process's environment."""
        windows = _windows_folder()
        cpus = str(min(4, os.cpu_count() or 1))
        python = runtime.runtime_dir(self.root)
        environment = {
            "SYSTEMROOT": windows, "WINDIR": windows,
            "PATH": f"{python};{windows}\\System32;{windows}",
            "PATHEXT": ".COM;.EXE;.BAT;.CMD", "COMSPEC": f"{windows}\\System32\\cmd.exe",
            "LOCALAPPDATA": str(self._local), "APPDATA": str(self.home / "roaming"),
            "USERPROFILE": str(self.home), "HOME": str(self.home),
            "TEMP": str(self.temp), "TMP": str(self.temp),
            "USERNAME": "sandbox", "USERDOMAIN": "sandbox", "COMPUTERNAME": "sandbox",
            "NUMBER_OF_PROCESSORS": cpus, "PROCESSOR_ARCHITECTURE": "AMD64",
            "OS": "Windows_NT", "TZ": "UTC",
            "PYTHONHASHSEED": "0", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "PYTHON_CPU_COUNT": cpus,
            # Numerical libraries otherwise start a thread, with its own
            # buffers, for every core of the machine.
            "OPENBLAS_NUM_THREADS": cpus, "OMP_NUM_THREADS": cpus,
            "MKL_NUM_THREADS": cpus, "NUMEXPR_MAX_THREADS": cpus,
            "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(self.home / ".matplotlib"),
        }
        for key, value in (extra or {}).items():
            if key.upper() in OWNED_VARIABLES:
                raise ValueError(f"the sandbox sets {key} itself")
            environment[key] = str(value)
        return environment

    # --- running --------------------------------------------------------------------

    def python(self):
        """The runtime's interpreter."""
        return str(runtime.python(self.root))

    def run(self, argv, cwd=None, environment=None, limits=None):
        """Run ``argv`` in the box and return a :class:`RunResult` once it and
        everything it started have ended (or been ended)."""
        from sandbox import win32

        if self._lock is None or self.folder is None:
            raise SandboxError("the box is not open")
        limits = limits or self.limits
        cwd = Path(cwd or self.app).resolve()
        if not cwd.is_relative_to(self.folder):
            raise SandboxError(f"{cwd}: not inside the working folder")
        job_limits = JobLimits(die_on_crash=True)
        if self.isolation.job_limits:
            job_limits = JobLimits(
                memory_bytes=limits.memory_mb << 20, processes=limits.processes,
                cpu_seconds=limits.cpu_seconds, cpu_percent=limits.cpu_percent,
                below_normal=True, ui_restricted=True, die_on_crash=True)
        job = JobObject(job_limits)
        stdin = out_read = out_write = err_read = err_write = None
        process = None
        try:
            stdin = win32.null_input()
            out_read, out_write = win32.pipe()
            err_read, err_write = win32.pipe()
            process = win32.start(
                list(argv), cwd, self.environment(environment), token=self._token,
                package=self.package if self.isolation.appcontainer else None,
                capabilities=self._capabilities, job=job.handle, stdin=stdin,
                stdout=out_write, stderr=err_write,
                desktop=self._desktop.path if self._desktop else None)
        except BaseException:
            for handle in (out_read, err_read):
                win32.close(handle)
            job.close()
            raise
        finally:
            for handle in (stdin, out_write, err_write):
                win32.close(handle)
        output = errors = None
        try:
            if not win32.in_job(process.handle, job.handle):
                win32.terminate(process)
                raise SandboxError("the process is not in its job; it was ended")
            output = _Capture(out_read, limits.output_bytes)
            errors = _Capture(err_read, limits.output_bytes)
            started = time.monotonic()
            win32.resume(process)
            cause = self._watch(process, job, limits, started)
            seconds = time.monotonic() - started
        finally:
            left = _end_all(job)
            stdout = output.finish(END_GRACE_SECONDS) if output else b""
            stderr = errors.finish(END_GRACE_SECONDS) if errors else b""
            job.poll()
            accounting = job.accounting()
            code = win32.exit_code(process.handle)
            process.close()
            job.close()
            for handle in (out_read, err_read):
                win32.close(handle)
        if left:
            raise SandboxError(f"{left} sandboxed processes did not end")
        cause = cause or ("cpu" if job.cpu_exceeded else None)
        size, entries, complete = usage(self.folder, MAX_ENTRIES)
        if self.isolation.watch and cause is None and (
                not complete or entries > limits.files or size > limits.disk_mb << 20):
            cause = "disk"  # filled between two checks, then ended by itself
        return RunResult(
            exit_code=code, stdout=stdout, stderr=stderr, stdout_bytes=output.total,
            stderr_bytes=errors.total, seconds=round(seconds, 3),
            cpu_seconds=round(accounting.user_seconds, 3),
            peak_memory_mb=accounting.peak_memory_bytes >> 20,
            processes=accounting.total_processes, cause=cause,
            memory_refused=job.memory_refused, process_refused=job.process_refused,
            folder_mb=round(size / (1 << 20), 2))

    def _watch(self, process, job, limits, started):
        """Wait for the run to end; end it at a limit and return which."""
        from sandbox import win32

        next_disk = 0.0
        while True:
            job.poll(50)
            if win32.wait(process.handle, 0):
                job.poll()
                return "cpu" if job.cpu_exceeded else None
            if job.cpu_exceeded:
                return "cpu"
            now = time.monotonic()
            if now - started > limits.seconds:
                return "timeout"
            if not self.isolation.watch:
                continue
            if job.accounting().write_bytes > limits.write_mb << 20:
                return "writes"
            if now >= next_disk:
                size, entries, complete = usage(self.folder, limits.files)
                if not complete or size > limits.disk_mb << 20:
                    return "disk"
                if shutil.disk_usage(self.folder).free < limits.free_disk_mb << 20:
                    return "disk"
                next_disk = now + DISK_CHECK_SECONDS

    # --- cleaning up ----------------------------------------------------------------

    def close(self, keep_folder=False):
        """Remove the token, desktop, profile and (unless ``keep_folder``) the
        working folder, and release the root. Raises SandboxError naming
        anything that could not be removed, after trying everything."""
        from sandbox import win32

        problems = []
        if self._token is not None:
            win32.close(self._token)
            self._token = None
        if self._desktop is not None:
            self._desktop.close()
            self._desktop = None
        if self._profile:
            try:
                win32.delete_profile(self.name)
                self._profile = False
            except OSError as error:
                problems.append(f"AppContainer profile {self.name}: {error}")
        _OPEN.discard(self.name)
        if self.folder is not None and self.folder.exists() and not keep_folder:
            # A virus scanner may hold new files for a while (seconds, on a
            # busy machine): try for up to about ten seconds.
            for pause in (0.2, 0.4, 0.8, 1.6, 3.2, 4.0, None):
                try:
                    remove_tree(self.folder)
                    break
                except OSError as error:
                    if pause is None:
                        problems.append(str(error))
                    else:
                        time.sleep(pause)
        if self._lock is not None:
            unlock_file(self._lock)
            self._lock = None
        if problems:
            raise SandboxError("left behind: " + "; ".join(problems))
