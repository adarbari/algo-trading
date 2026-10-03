"""Vendor pacing: ONE limiter per key (``massive``, ``sec``, ``nasdaq``...), shared by every
thread and every process on this machine (ADR 0019 R3, responsibility ``rate-limiting``).

The state is a lock file per key under a runtime directory (default ``var/run/limits/``,
git-ignored) holding the wall-clock time of the last request. ``wait`` takes an exclusive
``flock`` on it, sleeps until ``min_interval_s`` has passed since that time, writes the new
time and releases, so two CLI runs (or a run's worker threads) never exceed the vendor's
rate together. ``hold`` pushes the next slot out (a cool-down after the vendor pushed back).

Sources never pace themselves: the registry (``sources/registry.py``) gives each source an
``Http`` client (``sources/http.py``) carrying its key's limiter. Self-contained on purpose:
sources never import ``algotrade.storage`` (contract R4), so this does its own ``flock``.
"""

import fcntl
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

DEFAULT_DIR = Path("var/run/limits")
type Sleep = Callable[[float], None]
type Clock = Callable[[], float]


class Limiter:
    """Space requests for one key at least ``min_interval_s`` apart, across processes."""

    def __init__(
        self,
        key: str,
        min_interval_s: float,
        directory: Path = DEFAULT_DIR,
        sleep: Sleep = time.sleep,
        clock: Clock = time.time,
    ) -> None:
        if not key or "/" in key or key.startswith("."):
            raise ValueError(f"invalid limiter key {key!r}")
        self.key, self.min_interval_s = key, min_interval_s
        self.path = directory / f"{key}.lock"
        self._sleep, self._clock = sleep, clock
        self._thread = threading.Lock()

    def wait(self) -> float:
        """Block until this key may send a request, then claim the slot; -> seconds waited."""

        def claim(last: float) -> float:
            pause = max(0.0, last + self.min_interval_s - self._clock())
            if pause > 0:
                self._sleep(pause)
            return max(self._clock(), last)

        before = self._clock()
        self._update(claim)
        return max(0.0, self._clock() - before)

    def hold(self, seconds: float) -> None:
        """Make the next request for this key (any process) wait ``seconds`` from now."""
        self._update(lambda last: max(last, self._clock() + seconds - self.min_interval_s))

    def _update(self, step: Callable[[float], float]) -> None:
        """Run ``step(last request time) -> new time`` under the key's thread + file lock."""
        with self._thread:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                stamp = step(_parse(os.read(fd, 64)))
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, repr(stamp).encode())
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)


def _parse(raw: bytes) -> float:
    try:
        return float(raw.decode().strip() or 0.0)
    except ValueError:  # a torn or foreign file: start afresh
        return 0.0
