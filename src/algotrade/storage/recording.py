"""``BatchRecorder``: the background batch writer both of the API's recorders are (the live
quotes, ADR 0028; the text-model usage, ADR 0057). Written once here.

The caller answers first and records afterwards: ``submit`` puts an item on a bounded queue and
returns at once (a full queue drops the item, logged; a request never waits on storage). One
daemon thread drains the queue; each batch it takes (up to ``batch`` items) goes to ``_write``,
which a subclass implements (typically one atomic run: ``run_id`` for its id, then the writes
published together, ADR 0022). A batch whose write raises is logged and dropped; the thread
lives on. ``flush`` waits for everything submitted so far, ``close`` writes what is queued and
stops the thread.
"""

import logging
import queue
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from algotrade.storage.runs import start_run

log = logging.getLogger(__name__)
_STOP = None


class BatchRecorder[T]:
    """Subclasses implement ``_write(items, now)``; ``job`` names the run ids (``<job>-<session>-
    <time>``, ``storage.runs``), ``noun`` the items in the log."""

    def __init__(
        self,
        job: str,
        noun: str,
        batch: int,
        maxsize: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._job, self._noun, self._batch, self._clock = job, noun, batch, clock
        self._queue: queue.Queue[T | None] = queue.Queue(maxsize)
        self._last_run = ""
        self.written = 0  # runs committed
        self._thread = threading.Thread(target=self._drain, name=f"{job}-recorder", daemon=True)
        self._thread.start()

    def _put(self, item: T, weight: int = 1) -> bool:
        """Queue ``item`` (``weight``: how many things it holds, for the log); ``False``
        (dropped, logged) when the queue is full. Never raises."""
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            log.warning("%s recorder queue full: %d %s not recorded", self._job, weight, self._noun)
            return False
        except Exception:
            log.exception("%s recorder could not queue an item", self._job)
            return False
        return True

    def flush(self) -> None:
        """Wait until everything submitted so far is written (tests, shutdown)."""
        self._queue.join()

    def close(self, timeout_s: float = 10.0) -> None:
        """Write what is queued, then stop the thread."""
        self._queue.put(_STOP)
        self._thread.join(timeout_s)

    def run_id(self, session: date, now: datetime) -> str:
        """A fresh run id (ids have one-second resolution: a second run in the same second
        takes the next second)."""
        run_id = start_run(self._job, session, now).run_id
        while run_id <= self._last_run:
            now += timedelta(seconds=1)
            run_id = start_run(self._job, session, now).run_id
        self._last_run = run_id
        return run_id

    def _write(self, items: list[T], now: datetime) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ on the thread

    def _drain(self) -> None:
        while True:
            first = self._queue.get()
            batch = [first]
            while first is not None and len(batch) < self._batch:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            items = [b for b in batch if b is not None]
            try:
                if items:
                    self._write(items, self._clock())
                    self.written += 1
            except Exception:
                log.exception("%s not recorded (%d %s)", self._job, len(items), self._noun)
            finally:
                for _ in batch:
                    self._queue.task_done()
            if any(b is None for b in batch):
                return
