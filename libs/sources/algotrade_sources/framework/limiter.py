"""Vendor pacing: ONE adaptive limiter per key (``massive``, ``sec``, ``cboe``...), shared by
every thread and every process on this machine (ADR 0019 R3, responsibility ``rate-limiting``).

The state is a small JSON lock file per key under a runtime directory (default
``var/run/limits/``, git-ignored): the time of the last request, a hold (``not_before``), the
current interval, the success streak and the recent error window. ``wait`` takes an exclusive
``flock`` on it, sleeps until both ``last + interval`` and ``not_before`` have passed, writes
the new state and releases, so two CLI runs (or a run's worker threads) never exceed the
vendor's rate together.

Adaptive pacing (``Pacing``; docs/configuration.md "Vendor pacing"):

- the interval starts at ``start_interval_s`` and stays within ``[min_interval_s,
  max_interval_s]`` (the floor is the fastest we ever go);
- ``throttled(seconds)`` (HTTP 429): hold every process for ``seconds`` (the vendor's
  ``Retry-After``), then multiply the interval by ``backoff_factor``;
- ``record(outcome)``: each response is ``ok``, ``missing`` (the vendor answered "no such
  object": not an error) or ``error`` (5xx, a block, a timeout). The last ``error_window``
  responses form a window; once it is full and the share of errors (429s included) exceeds
  ``max_error_rate``, the interval is multiplied by ``backoff_factor`` and the window starts
  again, so a run slows down at most once per window;
- ``speedup_after`` consecutive non-error responses divide the interval by
  ``speedup_factor``, never below the floor.

The adaptive state resets to ``start_interval_s`` when the key has been idle for
``IDLE_RESET_S`` (in practice: at the start of each nightly run). ``hold`` alone pushes the
next slot out (the chain task's cool-down before its retry pass).

``track()`` gives a ``PacingStats`` that this process's limiter updates until ``untrack``:
``IngestRun`` opens one per key for the length of a run and stores it in the run stats.
Sources never pace themselves: the registry (``sources/framework/registry.py``) gives each
source an ``Http`` client (``sources/framework/http.py``) carrying its key's limiter.
Self-contained on purpose: sources never import ``algotrade.storage`` (contract R4), so this
does its own ``flock``.
"""

import fcntl
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

DEFAULT_DIR = Path("var/run/limits")
IDLE_RESET_S = 600.0  # a key unused this long starts again from ``start_interval_s``
type Sleep = Callable[[float], None]
type Clock = Callable[[], float]
type Outcome = Literal["ok", "missing", "error"]


@dataclass(frozen=True)
class Pacing:
    """One key's pacing rules (from ``config/site/sources.toml``, built by the registry).
    ``max_interval_s`` / ``start_interval_s`` ``None``: the floor (a fixed pace)."""

    min_interval_s: float
    max_interval_s: float | None = None
    start_interval_s: float | None = None
    backoff_factor: float = 1.5
    speedup_factor: float = 1.05
    speedup_after: int = 100
    error_window: int = 50
    max_error_rate: float = 0.10

    def __post_init__(self) -> None:
        if self.min_interval_s < 0:
            raise ValueError(f"min_interval_s must be >= 0, got {self.min_interval_s}")
        if self.ceiling < self.min_interval_s:
            raise ValueError(
                f"max_interval_s {self.ceiling} is below min_interval_s {self.min_interval_s}"
            )
        if not self.min_interval_s <= self.start <= self.ceiling:
            raise ValueError(
                f"start_interval_s {self.start} is outside [{self.min_interval_s}, {self.ceiling}]"
            )
        if self.backoff_factor < 1 or self.speedup_factor < 1:
            raise ValueError("backoff_factor and speedup_factor must be >= 1")
        if self.speedup_after < 1 or self.error_window < 1:
            raise ValueError("speedup_after and error_window must be >= 1")
        if not 0 <= self.max_error_rate <= 1:
            raise ValueError(f"max_error_rate must be in [0, 1], got {self.max_error_rate}")

    @property
    def ceiling(self) -> float:
        return self.min_interval_s if self.max_interval_s is None else self.max_interval_s

    @property
    def start(self) -> float:
        return self.min_interval_s if self.start_interval_s is None else self.start_interval_s

    def clamp(self, interval: float) -> float:
        return min(self.ceiling, max(self.min_interval_s, interval))


@dataclass
class PacingStats:
    """What one key's limiter did in this process while tracked (keys: docs/configuration.md
    "Pacing stats")."""

    requests: int = 0
    errors: int = 0
    throttled_429: int = 0
    retry_after_wait_s: float = 0.0
    limiter_wait_s: float = 0.0
    backoffs_429: int = 0
    error_rate_slowdowns: int = 0
    speedups: int = 0
    interval_start_s: float | None = None
    interval_final_s: float | None = None
    interval_min_s: float | None = None
    interval_max_s: float | None = None

    def saw(self, interval: float) -> None:
        if self.interval_start_s is None:
            self.interval_start_s = interval
        self.interval_final_s = interval
        low, high = self.interval_min_s, self.interval_max_s
        self.interval_min_s = interval if low is None else min(low, interval)
        self.interval_max_s = interval if high is None else max(high, interval)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            out[key] = round(value, 3) if isinstance(value, float) else value
        return out


@dataclass
class _State:
    last: float = 0.0  # wall-clock time of the last request
    not_before: float = 0.0  # a hold: no request before this time
    interval: float | None = None  # None: not started (``Pacing.start``)
    streak: int = 0  # consecutive non-error responses
    window: str = ""  # the last responses, "1" = error, newest last

    def dump(self) -> bytes:
        return json.dumps(self.__dict__).encode()


class Limiter:
    """Space requests for one key ``interval`` apart (adaptive, see the module docstring),
    across threads and processes."""

    def __init__(
        self,
        key: str,
        pacing: Pacing | float,
        directory: Path = DEFAULT_DIR,
        sleep: Sleep = time.sleep,
        clock: Clock = time.time,
    ) -> None:
        if not key or "/" in key or key.startswith("."):
            raise ValueError(f"invalid limiter key {key!r}")
        self.key = key
        self.pacing = pacing if isinstance(pacing, Pacing) else Pacing(pacing)
        self.path = directory / f"{key}.lock"
        self._sleep, self._clock = sleep, clock
        self._thread = threading.Lock()
        self._tracked: list[PacingStats] = []

    @property
    def min_interval_s(self) -> float:
        return self.pacing.min_interval_s

    @property
    def interval(self) -> float:
        """The current interval (shared state; the start value when idle)."""
        out: list[float] = []
        self._update(lambda s: out.append(self._current(s)))
        return out[0]

    # ------------------------------------------------------------------ pacing

    def wait(self) -> float:
        """Block until this key may send a request, then claim the slot; -> seconds waited."""
        waited: list[float] = []

        def claim(s: _State) -> None:
            interval = self._current(s)
            pause = max(0.0, s.last + interval - self._clock(), s.not_before - self._clock())
            if pause > 0:
                self._sleep(pause)
            s.last = max(self._clock(), s.last)
            waited.append(pause)
            self._each(lambda st: _requested(st, pause, interval))

        self._update(claim)
        return waited[0]

    def hold(self, seconds: float) -> None:
        """Make the next request for this key (any process) wait ``seconds`` from now."""
        self._update(lambda s: _hold(s, self._clock() + seconds))

    def throttled(self, seconds: float) -> None:
        """The vendor answered 429: hold every process for ``seconds`` (its Retry-After),
        then back off (interval x ``backoff_factor``) unless a hold was already running (the
        other workers' 429s from the same burst back off once). Counts as an error."""

        def step(s: _State) -> None:
            now = self._clock()
            fresh = s.not_before <= now
            held = max(0.0, now + seconds - max(s.not_before, now))
            _hold(s, now + seconds)
            if fresh:
                s.interval = self.pacing.clamp(self._current(s) * self.pacing.backoff_factor)
            self._each(lambda st: _throttled(st, held, fresh))
            self._observe(s, error=True)

        self._update(step)

    def record(self, outcome: Outcome) -> None:
        """One response that was not a 429: ``ok``, ``missing`` (not an error) or ``error``."""
        self._update(lambda s: self._observe(s, error=outcome == "error"))

    def _observe(self, s: _State, error: bool) -> None:
        p = self.pacing
        interval = self._current(s)
        s.window = (s.window + ("1" if error else "0"))[-p.error_window :]
        if error:
            s.streak = 0
            self._each(_errored)
        else:
            s.streak += 1
        if len(s.window) >= p.error_window and s.window.count("1") / len(s.window) > (
            p.max_error_rate
        ):
            s.interval, s.window = p.clamp(interval * p.backoff_factor), ""
            self._each(_slowed)
        elif s.streak >= p.speedup_after:
            s.interval, s.streak = p.clamp(interval / p.speedup_factor), 0
            self._each(_sped_up)
        self._each(lambda st: st.saw(self._current(s)))

    def _current(self, s: _State) -> float:
        idle = bool(s.last) and self._clock() - s.last > IDLE_RESET_S
        if (s.interval is None or idle) and s.not_before <= self._clock():
            s.interval, s.streak, s.window = self.pacing.start, 0, ""
        return self.pacing.clamp(self.pacing.start if s.interval is None else s.interval)

    # ------------------------------------------------------------------ stats

    def track(self) -> PacingStats:
        """Start collecting what this process's limiter does (until ``untrack``)."""
        stats = PacingStats()
        with self._thread:
            self._tracked.append(stats)
        return stats

    def untrack(self, stats: object) -> None:
        with self._thread:
            if stats in self._tracked:
                self._tracked.remove(stats)

    def _each(self, fn: Callable[[PacingStats], None]) -> None:
        for stats in self._tracked:  # called under self._thread
            fn(stats)

    # ------------------------------------------------------------------ the shared file

    def _update(self, step: Callable[[_State], object]) -> None:
        """Run ``step(state)`` (mutating it) under the key's thread + file lock."""
        with self._thread:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                state = _parse(os.read(fd, 4096))
                step(state)
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, state.dump())
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)


def _hold(s: _State, until: float) -> None:
    s.not_before = max(s.not_before, until)


def _requested(st: PacingStats, pause: float, interval: float) -> None:
    st.requests += 1
    st.limiter_wait_s += pause
    st.saw(interval)


def _throttled(st: PacingStats, held: float, backed_off: bool) -> None:
    st.throttled_429 += 1
    st.backoffs_429 += int(backed_off)
    st.retry_after_wait_s += held


def _errored(st: PacingStats) -> None:
    st.errors += 1


def _slowed(st: PacingStats) -> None:
    st.error_rate_slowdowns += 1


def _sped_up(st: PacingStats) -> None:
    st.speedups += 1


def _parse(raw: bytes) -> _State:
    """The shared state; a bare number is the previous format (the last request time); a
    torn or foreign file starts afresh."""
    text = raw.decode(errors="replace").strip()
    try:
        value = json.loads(text) if text else {}
    except ValueError:
        return _State()
    if isinstance(value, int | float):
        return _State(last=float(value))
    if not isinstance(value, dict):
        return _State()
    try:
        return _State(
            last=float(value.get("last", 0.0)),
            not_before=float(value.get("not_before", 0.0)),
            interval=None if value.get("interval") is None else float(value["interval"]),
            streak=int(value.get("streak", 0)),
            window=str(value.get("window", "")),
        )
    except (TypeError, ValueError):
        return _State()
