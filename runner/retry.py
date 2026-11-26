"""When and how long to wait before retrying a failed request (T0.5).

Which errors are retryable is the adapters' decision (``runner.providers``):
rate limits, server errors, overload, timeouts and dropped connections are;
authentication, validation and billing errors are not.
"""

import datetime
import email.utils
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with jitter, honouring Retry-After.

    The n-th retry waits a random time between half and all of
    ``min(max_delay, base_delay * 2 ** (n - 1))`` seconds, or longer if the
    provider's Retry-After asks for more. A Retry-After above
    ``max_retry_after`` means the request is not retried in this run.
    """

    max_attempts: int = 4  # including the first
    base_delay: float = 2.0
    max_delay: float = 60.0
    max_retry_after: float = 600.0

    def __post_init__(self):
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be a whole number of at least 1")
        for name in ("base_delay", "max_delay", "max_retry_after"):
            value = getattr(self, name)
            if not (isinstance(value, (int, float)) and math.isfinite(value)
                    and value >= 0):
                raise ValueError(f"{name} must be a number of seconds, at least 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be at least base_delay")

    def may_retry(self, attempts_made):
        """True if another attempt is allowed after ``attempts_made``."""
        return attempts_made < self.max_attempts

    def delay(self, attempts_made, retry_after, rng):
        """Seconds to wait before the next attempt, or None not to retry.

        ``rng`` is a ``random.Random`` (injectable for tests).
        """
        if retry_after is not None and retry_after > self.max_retry_after:
            return None
        ceiling = min(self.max_delay, self.base_delay * 2 ** (attempts_made - 1))
        wait = rng.uniform(ceiling / 2, ceiling)
        return max(wait, retry_after or 0.0)


def parse_retry_after(value, now=None):
    """Seconds from a Retry-After header (seconds or an HTTP date), or None.

    A time in the past is 0; an unreadable value is None.
    """
    if value is None or not value.strip():
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            moment = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        now = now or datetime.datetime.now(datetime.timezone.utc)
        seconds = (moment - now).total_seconds()
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)
