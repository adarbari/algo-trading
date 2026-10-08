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

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol, cast

import pandas as pd

from algotrade.core.time.calendar import exchange_date, is_session, previous_session
from algotrade.storage.factory import open_backend
from algotrade.storage.recording import BatchRecorder
from algotrade.storage.tables.live_writer import LiveWriter

TABLE = "live/option_quotes"
JOB = "live_quotes"
SOURCE = "ibkr"
BATCH = 50  # snapshots per run at most


class Recorder(Protocol):
    def submit(self, rows: pd.DataFrame) -> bool: ...

    def close(self) -> None: ...


def quote_session(at: datetime) -> date:
    """The exchange session a quote taken at ``at`` belongs to (the last one, outside one)."""
    day = exchange_date(at)
    return day if is_session(day) else previous_session(day)


class LiveRecorder(BatchRecorder[pd.DataFrame]):
    """Writes submitted snapshots (rows with ``ts``) to ``live/option_quotes`` on its thread."""

    def __init__(
        self,
        writer: LiveWriter,
        maxsize: int = 200,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._writer = writer
        super().__init__(JOB, "quotes", BATCH, maxsize, clock)

    def submit(self, rows: pd.DataFrame) -> bool:
        """Queue ``rows`` for writing; ``False`` (dropped) when empty or the queue is full."""
        return not rows.empty and self._put(rows, len(rows))

    def _write(self, items: list[pd.DataFrame], now: datetime) -> None:
        rows = pd.concat(items, ignore_index=True)
        ts = pd.to_datetime(rows["ts"], utc=True)
        rows = rows.assign(
            ts=ts,
            session_date=[quote_session(t.to_pydatetime()) for t in ts],
            knowledge_ts=ts,
            source=SOURCE,
        ).drop_duplicates(["instrument_id", "ts"], keep="last")
        run_id = self.run_id(rows["session_date"].max(), now)
        with self._writer.publishing(run_id, now):
            for session, part in rows.groupby("session_date", sort=True):
                frame = part.assign(run_id=run_id).reset_index(drop=True)
                self._writer.write_live(TABLE, cast(date, session), run_id, frame)


def open_recorder(data_url: str) -> LiveRecorder:
    """A recorder writing to the store at ``data_url`` (the API's)."""
    return LiveRecorder(LiveWriter(open_backend(data_url)))
