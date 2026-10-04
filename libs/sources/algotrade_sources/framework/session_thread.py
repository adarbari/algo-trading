"""Serve a session source to a long-running app (the API's live quotes): one thread owns it.

A session (IB Gateway's socket and the asyncio loop it runs on) belongs to the thread that
opened it, so ``SessionThread`` runs every call on one worker thread of its own. The worker
opens the source when a call first needs it (after a cheap ``probe``), keeps it open between
calls and runs calls one at a time, in order. Batch tasks keep using ``base.opened``; this is
the lifecycle for an app that serves requests for hours.

Failing fast when the gateway is away: a failed open, or a call that loses the session
(``SessionUnavailableError``, ``ConnectionError``, ``OSError``), closes the source and marks
it down for ``retry_after_s``; calls in that window raise ``SessionUnavailableError`` at once
with the reason, so a stopped gateway costs a request nothing. A call that takes longer than
its ``timeout_s`` raises ``SessionUnavailableError`` too; the worker finishes it in the
background and calls fail as busy until it has. Any other error is the caller's (the session
stays open).
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from algotrade_sources.framework.base import SessionSource, SessionUnavailableError

log = logging.getLogger(__name__)

LOST = (SessionUnavailableError, ConnectionError, OSError)  # the session is gone: reopen later


class SessionThread[S: SessionSource]:
    """Runs ``work(source)`` calls on one thread that opens ``source`` lazily and keeps it."""

    def __init__(
        self,
        source: S,
        retry_after_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source, self._retry_after_s, self._clock = source, retry_after_s, clock
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"session-{source.name}")
        self._lock = threading.Lock()
        self._open = False
        self._down_until = 0.0
        self._down_reason = ""
        self._running = 0  # calls submitted and not finished (a timed-out one included)
        self._overdue = False  # a call outlived its timeout and is still running

    @property
    def name(self) -> str:
        return self._source.name

    def status(self) -> str | None:
        """``None`` when a call may be tried now, else why not (down, or still busy)."""
        with self._lock:
            if self._overdue and self._running:
                return f"{self.name}: an earlier request is still running"
            if self._clock() < self._down_until:
                return self._down_reason
            return None

    def call[T](self, work: Callable[[S], T], timeout_s: float) -> T:
        """``work(source)`` on the session's thread; ``SessionUnavailableError`` when the
        session is down, busy, lost during the call or slower than ``timeout_s``."""
        reason = self.status()
        if reason is not None:
            raise SessionUnavailableError(reason)
        with self._lock:
            self._running += 1
        future = self._pool.submit(self._run, work)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeout:
            with self._lock:
                self._overdue = True
            raise SessionUnavailableError(
                f"{self.name}: no answer within {timeout_s:g} s"
            ) from None

    def close(self, timeout_s: float = 5.0) -> None:
        """Close the session on its thread and stop the worker (never raises)."""
        future = self._pool.submit(self._close)
        try:
            future.result(timeout=timeout_s)
        except Exception:
            log.warning("%s: the session did not close cleanly", self.name)
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ on the worker thread

    def _run[T](self, work: Callable[[S], T]) -> T:
        try:
            if not self._open:
                self._connect()
            try:
                return work(self._source)
            except LOST as exc:
                self._down(f"{self.name}: session lost ({exc})")
                raise SessionUnavailableError(str(exc)) from exc
        finally:
            with self._lock:
                self._running -= 1
                if not self._running:
                    self._overdue = False

    def _connect(self) -> None:
        reason = self._source.probe()
        if reason is None:
            try:
                self._source.open()
            except LOST as exc:
                reason = str(exc)
        if reason is not None:
            self._down(reason)
            raise SessionUnavailableError(reason)
        self._open = True

    def _down(self, reason: str) -> None:
        self._close()
        with self._lock:
            self._down_until = self._clock() + self._retry_after_s
            self._down_reason = reason
        log.warning("%s down for %gs: %s", self.name, self._retry_after_s, reason)

    def _close(self) -> None:
        self._open = False
        self._source.close()
