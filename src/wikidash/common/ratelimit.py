"""Token bucket rate limiter with lazy refill (no timer thread)."""

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Allows `capacity` requests per `refill_seconds`; starts full (burst)."""

    def __init__(
        self,
        capacity: int,
        refill_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._capacity = capacity
        self._seconds_per_token = refill_seconds / capacity
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(capacity)
        self._last_refill = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until one token is available, then take it."""
        wait = self._take_or_wait_time()
        while wait > 0:
            self._sleep(wait)
            wait = self._take_or_wait_time()

    def _take_or_wait_time(self) -> float:
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return 0.0
            return (1 - self._tokens) * self._seconds_per_token

    def _refill(self) -> None:
        now = self._clock()
        gained = (now - self._last_refill) / self._seconds_per_token
        self._tokens = min(self._capacity, self._tokens + gained)
        self._last_refill = now
