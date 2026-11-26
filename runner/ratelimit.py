"""Requests-per-minute limit, one per provider (T0.5).

Request starts are spaced evenly, ``60 / per_minute`` seconds apart, across
all threads that share the limiter. Providers also limit tokens per minute and
concurrency; their 429 responses are retried (see ``runner.retry``).
"""

import math
import threading
import time


class RateLimiter:
    def __init__(self, per_minute, *, clock=time.monotonic, sleep=time.sleep):
        if (isinstance(per_minute, bool) or not isinstance(per_minute, (int, float))
                or not math.isfinite(per_minute) or per_minute <= 0):
            raise ValueError(f"requests per minute must be above 0, not {per_minute!r}")
        self.per_minute = per_minute
        self._interval = 60.0 / per_minute
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = None

    def acquire(self):
        """Wait for this request's turn; return the seconds waited."""
        with self._lock:
            now = self._clock()
            slot = now if self._next is None else max(now, self._next)
            self._next = slot + self._interval
        wait = slot - now
        if wait > 0:
            self._sleep(wait)
        return wait
