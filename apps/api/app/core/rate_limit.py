import time
from collections import deque
from math import ceil

_MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """In-memory sliding-window limiter.

    State is per process: with several workers each one counts on its own, and a restart
    clears it. Move this to Redis if the API ever runs as more than one process.
    """

    def __init__(self, *, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float] | None:
        events = self._events.get(key)
        if events is None:
            return None
        cutoff = time.monotonic() - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            del self._events[key]
            return None
        return events

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may try again, or None when it is under the limit."""
        events = self._recent(key)
        if events is None or len(events) < self.max_attempts:
            return None
        return max(1, ceil(events[0] + self.window_seconds - time.monotonic()))

    def record(self, key: str) -> None:
        self._recent(key)
        self._events.setdefault(key, deque()).append(time.monotonic())
        if len(self._events) > _MAX_TRACKED_KEYS:
            self._evict()

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._events.clear()
        else:
            self._events.pop(key, None)

    def _evict(self) -> None:
        for key in list(self._events):
            self._recent(key)
        while len(self._events) > _MAX_TRACKED_KEYS:
            del self._events[next(iter(self._events))]


# Failed logins only: a successful login clears the per-account counter.
login_account_limiter = RateLimiter(max_attempts=5, window_seconds=15 * 60)
login_ip_limiter = RateLimiter(max_attempts=30, window_seconds=15 * 60)
# Every registration attempt counts, successful or not.
register_limiter = RateLimiter(max_attempts=10, window_seconds=60 * 60)


def reset_all_limiters() -> None:
    for limiter in (login_account_limiter, login_ip_limiter, register_limiter):
        limiter.reset()
