"""A per-user rate limit for on-demand model calls (ADR 0041, amended 2026-10-06): at most
``limit`` calls in any ``window_s`` seconds for one user, counted in memory (one API process;
a restart forgets, which is fine for a courtesy limit on a free tier). ``take`` raises
``RateLimitedError`` with the seconds until the oldest call leaves the window."""

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from algotrade.core.model.errors import RateLimitedError


class RateLimiter:
    def __init__(
        self,
        limit: int = 6,
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def take(self, user: str, what: str) -> None:
        """Count one call by ``user`` (``what`` names it in the error)."""
        now = self._clock()
        with self._lock:
            calls = self._calls[user]
            while calls and now - calls[0] >= self.window_s:
                calls.popleft()
            if len(calls) >= self.limit:
                raise RateLimitedError(what, max(1, math.ceil(self.window_s - (now - calls[0]))))
            calls.append(now)
