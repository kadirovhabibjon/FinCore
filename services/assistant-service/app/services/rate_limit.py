import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """At most `limit` requests per key in any `window_seconds`. In memory:
    one assistant-service process, so this is exact for the deployment it
    runs in (and resets on restart, which only ever loosens it)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and hits[0] <= current - self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(current)
        return True
