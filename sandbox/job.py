"""Windows job objects: limits on a group of processes taken together.

Shared by the sandbox and the renderer (``renderer/limits.py``). A process put
in a job stays in it, and so does every process it starts: the job allows no
breakaway. Closing the job, or the end of this process however it ends, kills
them all.

Limits are on all the processes of the job together: committed memory,
processes alive at once, user-mode CPU time, a hard cap on the CPU rate, and a
priority below normal. Bytes written are counted (:meth:`JobObject.accounting`)
but not limited: Windows did not report a write limit being passed in tests
here, so a caller that wants one polls the count. UI restrictions stop the
processes from using the clipboard, global atoms, other processes' windows
and desktop switching. Windows refusing any limit raises OSError: a job is
never handed out with fewer limits than asked for.
"""

import ctypes
from dataclasses import dataclass
from typing import NamedTuple, Optional

# JOBOBJECT_BASIC_LIMIT_INFORMATION.LimitFlags
_LIMIT_JOB_TIME = 0x4
_LIMIT_ACTIVE_PROCESS = 0x8
_LIMIT_PRIORITY_CLASS = 0x20
_LIMIT_JOB_MEMORY = 0x200
_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400
_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_BELOW_NORMAL_PRIORITY_CLASS = 0x4000
# JOBOBJECTINFOCLASS
_BASIC_ACCOUNTING = 1
_UI_RESTRICTIONS = 4
_PORT = 7
_BASIC_AND_IO_ACCOUNTING = 8
_EXTENDED_LIMITS = 9
_CPU_RATE_CONTROL = 15
_CPU_RATE_ENABLE, _CPU_RATE_HARD_CAP = 0x1, 0x4
# Desktop, display settings, exit windows, global atoms, handles of other
# processes' windows, reading and writing the clipboard, system parameters.
_UI_ALL = 0xFF
# Completion port messages.
MSG_END_OF_JOB_TIME = 1
MSG_ACTIVE_PROCESS_LIMIT = 3
MSG_ACTIVE_PROCESS_ZERO = 4
MSG_NEW_PROCESS = 6
MSG_PROCESS_MEMORY_LIMIT = 9
MSG_JOB_MEMORY_LIMIT = 10
_ASSIGN_ACCESS = 0x0100 | 0x0001  # PROCESS_SET_QUOTA | PROCESS_TERMINATE


@dataclass(frozen=True)
class JobLimits:
    """What a job allows. None: no limit of that kind."""

    memory_bytes: Optional[int] = None  # committed memory, all processes
    processes: Optional[int] = None  # alive at the same time
    cpu_seconds: Optional[float] = None  # user-mode CPU time, all processes
    cpu_percent: Optional[int] = None  # hard cap on the rate, of all cores
    below_normal: bool = False
    ui_restricted: bool = False
    die_on_crash: bool = False  # no crash dialog: a crashing process just ends

    def __post_init__(self):
        for name in ("memory_bytes", "processes"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ValueError(f"{name}: a whole number of at least 1, not {value!r}")
        if self.cpu_seconds is not None and not self.cpu_seconds > 0:
            raise ValueError(f"cpu_seconds: more than 0, not {self.cpu_seconds!r}")
        if self.cpu_percent is not None and not (
                isinstance(self.cpu_percent, int) and 1 <= self.cpu_percent <= 100):
            raise ValueError(f"cpu_percent: from 1 to 100, not {self.cpu_percent!r}")


class Accounting(NamedTuple):
    active_processes: int
    total_processes: int
    peak_memory_bytes: int
    write_bytes: int
    user_seconds: float


def _api():
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD), ("minimum_set", ctypes.c_size_t),
            ("maximum_set", ctypes.c_size_t), ("processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic), ("io", ctypes.c_uint64 * 6),
            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    class Port(ctypes.Structure):
        _fields_ = [("key", ctypes.c_void_p), ("port", wintypes.HANDLE)]

    class CpuRate(ctypes.Structure):
        _fields_ = [("flags", wintypes.DWORD), ("rate", wintypes.DWORD)]

    class Accounts(ctypes.Structure):
        _fields_ = [
            ("user_time", ctypes.c_int64), ("kernel_time", ctypes.c_int64),
            ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
            ("page_faults", wintypes.DWORD), ("total", wintypes.DWORD),
            ("active", wintypes.DWORD), ("terminated", wintypes.DWORD),
            ("io", ctypes.c_uint64 * 6)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = wintypes.HANDLE
    for name, result, arguments in (
        ("CreateJobObjectW", handle, [ctypes.c_void_p, wintypes.LPCWSTR]),
        ("CreateIoCompletionPort", handle,
         [handle, handle, ctypes.c_size_t, wintypes.DWORD]),
        ("OpenProcess", handle, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        ("SetInformationJobObject", wintypes.BOOL,
         [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]),
        ("QueryInformationJobObject", wintypes.BOOL,
         [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]),
        ("AssignProcessToJobObject", wintypes.BOOL, [handle, handle]),
        ("GetQueuedCompletionStatus", wintypes.BOOL,
         [handle, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]),
        ("TerminateJobObject", wintypes.BOOL, [handle, wintypes.UINT]),
        ("CloseHandle", wintypes.BOOL, [handle]),
    ):
        function = getattr(kernel, name)
        function.restype, function.argtypes = result, arguments
    return kernel, wintypes, Basic, Extended, Port, CpuRate, Accounts


class JobObject:
    """A job with ``limits``. Raises OSError if Windows refuses any of them."""

    def __init__(self, limits=JobLimits()):
        (self._kernel, self._wintypes, _, self._Extended, Port, CpuRate,
         self._Accounts) = _api()
        self.limits = limits
        self.memory_refused = self.process_refused = False
        self.cpu_exceeded = False
        self.empty = False  # set once the job has had processes and has none
        kernel = self._kernel
        self._job = kernel.CreateJobObjectW(None, None)
        self._port = kernel.CreateIoCompletionPort(
            self._wintypes.HANDLE(-1), None, 0, 1)
        if not (self._job and self._port):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(f"no job object (Windows error {error})")
        extended = self._Extended()
        flags = _LIMIT_KILL_ON_JOB_CLOSE
        if limits.die_on_crash:
            flags |= _LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        if limits.memory_bytes is not None:
            flags |= _LIMIT_JOB_MEMORY
            extended.job_memory = limits.memory_bytes
        if limits.processes is not None:
            flags |= _LIMIT_ACTIVE_PROCESS
            extended.basic.processes = limits.processes
        if limits.cpu_seconds is not None:
            flags |= _LIMIT_JOB_TIME
            extended.basic.job_time = int(limits.cpu_seconds * 10_000_000)
        if limits.below_normal:
            flags |= _LIMIT_PRIORITY_CLASS
            extended.basic.priority = _BELOW_NORMAL_PRIORITY_CLASS
        extended.basic.flags = flags
        settings = [(_EXTENDED_LIMITS, extended),
                    (_PORT, Port(None, self._port))]
        if limits.cpu_percent is not None:
            settings.append((_CPU_RATE_CONTROL, CpuRate(
                _CPU_RATE_ENABLE | _CPU_RATE_HARD_CAP, limits.cpu_percent * 100)))
        if limits.ui_restricted:
            settings.append((_UI_RESTRICTIONS, self._wintypes.DWORD(_UI_ALL)))
        for kind, value in settings:
            if not kernel.SetInformationJobObject(
                    self._job, kind, ctypes.byref(value), ctypes.sizeof(value)):
                error = ctypes.get_last_error()
                self.close()
                raise OSError(f"the job refused a limit (class {kind}, "
                              f"Windows error {error})")

    @property
    def handle(self):
        """The job's handle, for ``PROC_THREAD_ATTRIBUTE_JOB_LIST``."""
        return self._job

    def assign_handle(self, process):
        """Put the process with handle ``process`` in the job; OSError if not."""
        if not self._kernel.AssignProcessToJobObject(
                self._job, self._wintypes.HANDLE(process)):
            raise OSError(f"the process could not be put in the job "
                          f"(Windows error {ctypes.get_last_error()})")

    def assign_pid(self, pid):
        """Put process ``pid`` in the job; OSError if Windows refuses."""
        process = self._kernel.OpenProcess(_ASSIGN_ACCESS, False, pid)
        if not process:
            raise OSError(f"the process could not be opened "
                          f"(Windows error {ctypes.get_last_error()})")
        try:
            self.assign_handle(process)
        finally:
            self._kernel.CloseHandle(process)

    def poll(self, timeout_ms=0):
        """Read the job's messages, waiting up to ``timeout_ms`` for the first;
        update the flags and return the message numbers read."""
        if not self._port:
            return []
        message = self._wintypes.DWORD()
        key, detail = ctypes.c_size_t(), ctypes.c_void_p()
        byref, seen, wait = ctypes.byref, [], timeout_ms
        while self._kernel.GetQueuedCompletionStatus(
                self._port, byref(message), byref(key), byref(detail), wait):
            wait = 0
            number = message.value
            seen.append(number)
            if number in (MSG_JOB_MEMORY_LIMIT, MSG_PROCESS_MEMORY_LIMIT):
                self.memory_refused = True
            elif number == MSG_ACTIVE_PROCESS_LIMIT:
                self.process_refused = True
            elif number == MSG_END_OF_JOB_TIME:
                self.cpu_exceeded = True
            elif number == MSG_ACTIVE_PROCESS_ZERO:
                self.empty = True
            elif number == MSG_NEW_PROCESS:
                self.empty = False
        return seen

    def accounting(self):
        """Counts so far, as an :class:`Accounting`."""
        accounts, extended = self._Accounts(), self._Extended()
        query = self._kernel.QueryInformationJobObject
        if not (self._job
                and query(self._job, _BASIC_AND_IO_ACCOUNTING, ctypes.byref(accounts),
                          ctypes.sizeof(accounts), None)
                and query(self._job, _EXTENDED_LIMITS, ctypes.byref(extended),
                          ctypes.sizeof(extended), None)):
            return Accounting(0, 0, 0, 0, 0.0)
        return Accounting(accounts.active, accounts.total, extended.peak_job,
                          accounts.io[4], accounts.user_time / 10_000_000)

    def terminate(self, exit_code=1):
        """Kill every process in the job; the job stays open."""
        if self._job:
            self._kernel.TerminateJobObject(self._job, exit_code)

    def close(self):
        """Kill every process in the job and release it."""
        if getattr(self, "_job", None):
            self._kernel.TerminateJobObject(self._job, 1)
            self._kernel.CloseHandle(self._job)
            self._job = None
        if getattr(self, "_port", None):
            self._kernel.CloseHandle(self._port)
            self._port = None
