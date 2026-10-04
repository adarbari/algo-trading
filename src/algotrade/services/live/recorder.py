"""Record live quotes in the background: ``live/option_quotes``, one atomic run per batch.

The API answers first and records afterwards: ``submit`` puts a snapshot on a bounded queue
and returns at once (a full queue drops the snapshot, logged; a page never waits on storage).
One daemon thread drains the queue; each batch it takes is one run (``live_quotes-<session>-
<time>``, from ``storage.runs``; no run record: these are not jobs), its partitions written
pending and committed together (ADR 0022), dropped if a write fails. Rows are stamped with
the point-in-time columns (ADR 0007): ``session_date`` is the exchange session the quote was
taken in (the last session before it, outside one), ``knowledge_ts`` the time it was taken,
``source`` ``ibkr``. Only ``live/*`` tables, only through ``LiveWriter`` (ADR 0028).
"""

import logging
import queue
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, cast

import pandas as pd

from algotrade.core.time.calendar import exchange_date, is_session, previous_session
from algotrade.storage.factory import open_backend
from algotrade.storage.runs import start_run
from algotrade.storage.tables.live_writer import LiveWriter

log = logging.getLogger(__name__)

TABLE = "live/option_quotes"
JOB = "live_quotes"
SOURCE = "ibkr"
BATCH = 50  # snapshots per run at most
_STOP = None


class Recorder(Protocol):
    def submit(self, rows: pd.DataFrame) -> bool: ...

    def close(self) -> None: ...


def quote_session(at: datetime) -> date:
    """The exchange session a quote taken at ``at`` belongs to (the last one, outside one)."""
    day = exchange_date(at)
    return day if is_session(day) else previous_session(day)


class LiveRecorder:
    """Writes submitted snapshots (rows with ``ts``) to ``live/option_quotes`` on its thread."""

    def __init__(
        self,
        writer: LiveWriter,
        maxsize: int = 200,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._writer, self._clock = writer, clock
        self._queue: queue.Queue[pd.DataFrame | None] = queue.Queue(maxsize)
        self._last_run = ""
        self.written = 0  # runs committed
        self._thread = threading.Thread(target=self._drain, name="live-recorder", daemon=True)
        self._thread.start()

    def submit(self, rows: pd.DataFrame) -> bool:
        """Queue ``rows`` for writing; ``False`` (dropped) when empty or the queue is full."""
        if rows.empty:
            return False
        try:
            self._queue.put_nowait(rows)
        except queue.Full:
            log.warning("live recorder queue full: %d quotes not recorded", len(rows))
            return False
        return True

    def flush(self) -> None:
        """Wait until everything submitted so far is written (tests, shutdown)."""
        self._queue.join()

    def close(self, timeout_s: float = 10.0) -> None:
        """Write what is queued, then stop the thread."""
        self._queue.put(_STOP)
        self._thread.join(timeout_s)

    # ------------------------------------------------------------------ on the thread

    def _drain(self) -> None:
        while True:
            first = self._queue.get()
            batch = [first]
            while first is not None and len(batch) < BATCH:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            frames = [b for b in batch if b is not None]
            try:
                if frames:
                    self._write(pd.concat(frames, ignore_index=True))
            except Exception:
                log.exception("live quotes not recorded (%d snapshots)", len(frames))
            finally:
                for _ in batch:
                    self._queue.task_done()
            if any(b is None for b in batch):
                return

    def _write(self, rows: pd.DataFrame) -> None:
        now = self._clock()
        ts = pd.to_datetime(rows["ts"], utc=True)
        rows = rows.assign(
            ts=ts,
            session_date=[quote_session(t.to_pydatetime()) for t in ts],
            knowledge_ts=ts,
            source=SOURCE,
        ).drop_duplicates(["instrument_id", "ts"], keep="last")
        run_id = self._run_id(rows["session_date"].max(), now)
        with self._writer.publishing(run_id, now):
            for session, part in rows.groupby("session_date", sort=True):
                frame = part.assign(run_id=run_id).reset_index(drop=True)
                self._writer.write_live(TABLE, cast(date, session), run_id, frame)
        self.written += 1

    def _run_id(self, session: date, now: datetime) -> str:
        """A fresh run id (ids have one-second resolution: a second run in the same second
        takes the next second)."""
        run_id = start_run(JOB, session, now).run_id
        while run_id <= self._last_run:
            now += timedelta(seconds=1)
            run_id = start_run(JOB, session, now).run_id
        self._last_run = run_id
        return run_id


def open_recorder(data_url: str) -> LiveRecorder:
    """A recorder writing to the store at ``data_url`` (the API's)."""
    return LiveRecorder(LiveWriter(open_backend(data_url)))
