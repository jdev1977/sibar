"""A hold on a browser's processes: cap their memory and end them for good.

On Windows the browser process is put in a job object, which the processes it
starts afterwards (the renderer among them) join too. Elsewhere there is no
memory cap and only the browser process is killed (its children exit with it).
"""

import os
import signal

_JOB_MEMORY = 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY
_KILL_ON_CLOSE = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
_EXTENDED_INFORMATION = 9
_ASSIGN_ACCESS = 0x0100 | 0x0001  # PROCESS_SET_QUOTA | PROCESS_TERMINATE


def _windows_job(pid, memory_bytes):
    """A job holding process ``pid``, or None if Windows refuses."""
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
            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = Extended()
    limits.basic.flags = _JOB_MEMORY | _KILL_ON_CLOSE
    limits.job_memory = memory_bytes
    process = kernel.OpenProcess(_ASSIGN_ACCESS, False, pid)
    held = bool(
        process
        and kernel.SetInformationJobObject(
            job, _EXTENDED_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits))
        and kernel.AssignProcessToJobObject(job, process))
    if process:
        kernel.CloseHandle(process)
    if not held:
        kernel.CloseHandle(job)
        return None

    def end():
        kernel.TerminateJobObject(job, 1)
        kernel.CloseHandle(job)

    return end


class ProcessLimit:
    """Holds the browser process ``pid``. ``memory_limited`` says whether the
    memory cap is in force. :meth:`end` kills whatever is still running."""

    def __init__(self, pid, memory_mb):
        self.pid = pid
        self._end = _windows_job(pid, memory_mb << 20) if os.name == "nt" else None
        self.memory_limited = self._end is not None

    def end(self, closed):
        """``closed`` says the browser already shut down cleanly, so its
        process number must not be killed (it may have been reused)."""
        if self._end is not None:
            self._end()
            self._end = None
        elif not closed:
            try:
                os.kill(self.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except OSError:
                pass
