"""A hold on a render's processes: cap their memory and end them for good.

The caller puts the render process in the hold before it starts anything, so
the Playwright driver and every browser process (the graphics process too) are
in it from their first moment.

On Windows the hold is a job object with a memory cap for all its processes
together, which kills them when it is closed, also if this process dies.
Elsewhere there is no memory cap, and ending the hold kills the process group.
"""

import os
import signal

_JOB_MEMORY = 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY
_KILL_ON_CLOSE = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
_PORT_INFORMATION = 7
_EXTENDED_INFORMATION = 9
_MEMORY_MESSAGES = (9, 10)  # a process or the job was refused memory
_ASSIGN_ACCESS = 0x0100 | 0x0001  # PROCESS_SET_QUOTA | PROCESS_TERMINATE


class _WindowsJob:
    """A job object holding process ``pid``; OSError if Windows refuses."""

    def __init__(self, pid, memory_bytes):
        import ctypes
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
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        class Port(ctypes.Structure):
            _fields_ = [("key", ctypes.c_void_p), ("port", wintypes.HANDLE)]

        self._ctypes, self._wintypes, self._extended = ctypes, wintypes, Extended
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel = kernel
        handle = wintypes.HANDLE
        for name, result, arguments in (
            ("CreateJobObjectW", handle, [ctypes.c_void_p, wintypes.LPCWSTR]),
            ("CreateIoCompletionPort", handle,
             [handle, handle, ctypes.c_size_t, wintypes.DWORD]),
            ("OpenProcess", handle, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ("SetInformationJobObject", wintypes.BOOL,
             [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]),
            ("QueryInformationJobObject", wintypes.BOOL,
             [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
              ctypes.c_void_p]),
            ("AssignProcessToJobObject", wintypes.BOOL, [handle, handle]),
            ("GetQueuedCompletionStatus", wintypes.BOOL,
             [handle, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
              wintypes.DWORD]),
            ("TerminateJobObject", wintypes.BOOL, [handle, wintypes.UINT]),
            ("CloseHandle", wintypes.BOOL, [handle]),
        ):
            function = getattr(kernel, name)
            function.restype, function.argtypes = result, arguments

        self._job = kernel.CreateJobObjectW(None, None)
        self._port = kernel.CreateIoCompletionPort(handle(-1), None, 0, 1)
        process = kernel.OpenProcess(_ASSIGN_ACCESS, False, pid)
        limits = Extended()
        limits.basic.flags = _JOB_MEMORY | _KILL_ON_CLOSE
        limits.job_memory = memory_bytes
        port = Port(None, self._port)
        held = bool(
            self._job and self._port and process
            and kernel.SetInformationJobObject(
                self._job, _EXTENDED_INFORMATION, ctypes.byref(limits),
                ctypes.sizeof(limits))
            and kernel.SetInformationJobObject(
                self._job, _PORT_INFORMATION, ctypes.byref(port),
                ctypes.sizeof(port))
            and kernel.AssignProcessToJobObject(self._job, process))
        error = ctypes.get_last_error()
        if process:
            kernel.CloseHandle(process)
        if not held:
            self.end()
            raise OSError(f"no job object for the process (Windows error {error})")
        self._refused = False

    def peak_bytes(self):
        """The most memory the job's processes have held together."""
        limits = self._extended()
        if not self._kernel.QueryInformationJobObject(
                self._job, _EXTENDED_INFORMATION, self._ctypes.byref(limits),
                self._ctypes.sizeof(limits), None):
            return 0
        return limits.peak_job

    def refused_memory(self):
        """Whether the cap has refused any process memory."""
        message = self._wintypes.DWORD()
        key, detail = self._ctypes.c_size_t(), self._ctypes.c_void_p()
        byref = self._ctypes.byref
        while self._kernel.GetQueuedCompletionStatus(
                self._port, byref(message), byref(key), byref(detail), 0):
            self._refused |= message.value in _MEMORY_MESSAGES
        return self._refused

    def end(self):
        if self._job:
            self._kernel.TerminateJobObject(self._job, 1)
            self._kernel.CloseHandle(self._job)
            self._job = None
        if self._port:
            self._kernel.CloseHandle(self._port)
            self._port = None


class ProcessLimit:
    """Holds process ``pid`` and all it starts from now on. Elsewhere than on
    Windows, ``pid`` must lead its own process group.

    Raises OSError if Windows will not apply the cap."""

    def __init__(self, pid, memory_mb):
        self._pid = pid
        self._job = _WindowsJob(pid, memory_mb << 20) if os.name == "nt" else None
        self.memory_limited = self._job is not None
        self.peak_mb = 0
        self.refused_memory = False
        self._ended = False

    def end(self):
        """Kill whatever is still running; afterwards ``peak_mb`` and
        ``refused_memory`` tell how the cap was used."""
        if self._ended:
            return
        self._ended = True
        if self._job is not None:
            self.peak_mb = self._job.peak_bytes() >> 20
            self.refused_memory = self._job.refused_memory()
            self._job.end()
        else:
            try:
                os.killpg(self._pid, signal.SIGKILL)
            except (AttributeError, OSError):
                pass
