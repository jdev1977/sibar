"""A hold on a render's processes: cap their memory and end them for good.

The caller puts the render process in the hold before it starts anything, so
the Playwright driver and every browser process (the graphics process too) are
in it from their first moment.

On Windows the hold is a job object (``sandbox.job``, shared with the sandbox)
with a memory cap for all its processes together, which kills them when it is
closed, also if this process dies. Elsewhere there is no memory cap, and
ending the hold kills the process group.
"""

import os
import signal


class ProcessLimit:
    """Holds process ``pid`` and all it starts from now on. Elsewhere than on
    Windows, ``pid`` must lead its own process group.

    Raises OSError if Windows will not apply the cap."""

    def __init__(self, pid, memory_mb):
        self._pid = pid
        self._job = None
        if os.name == "nt":
            from sandbox.job import JobLimits, JobObject

            self._job = JobObject(JobLimits(memory_bytes=memory_mb << 20))
            try:
                self._job.assign_pid(pid)
            except OSError:
                self._job.close()
                raise
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
            self.peak_mb = self._job.accounting().peak_memory_bytes >> 20
            self._job.poll()
            self.refused_memory = self._job.memory_refused
            self._job.close()
        else:
            try:
                os.killpg(self._pid, signal.SIGKILL)
            except (AttributeError, OSError):
                pass
