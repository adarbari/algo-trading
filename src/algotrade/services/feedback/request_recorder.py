"""Record the missing-feature requests of Describe it in the background:
``feedback/feature_requests``, one atomic run per batch (ADR 0066 amendment 2026-10-11), the same
writer and the same ``BatchRecorder`` pattern as the drafting events (``recorder.py``).

``submit`` puts a row on a bounded queue and returns at once (a full queue drops the row, logged;
a request never waits on storage and never fails on it). A row is stamped with the point-in-time
columns (ADR 0007): ``session_date`` is the exchange calendar date of the request, ``knowledge_ts``
its time, ``source`` ``drafting_feedback``. A row is keyed by user, ref and exchange day, so a
trader asking for one thing twice on a day is one row. Only ``feedback/*`` tables, only through
``FeedbackWriter``.
"""

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any, cast

import pandas as pd

from algotrade.core.time.calendar import exchange_date
from algotrade.services.feedback.events import FeedbackSink
from algotrade.storage.factory import open_backend
from algotrade.storage.recording import BatchRecorder
from algotrade.storage.tables.feedback_writer import FeedbackWriter

TABLE = "feedback/feature_requests"
JOB = "feature_requests"
SOURCE = "drafting_feedback"
BATCH = 100  # rows per run at most
KEY = ["user", "ref", "session_date"]  # as the table's key (schemas.py)
COLUMNS = (
    "ts", "user", "ref", "key", "new_slug", "feasibility", "span", "closest", "call_id",
    "draft_session_id",
)  # fmt: skip

__all__ = ["FeatureRequestRecorder", "FeedbackSink", "open_request_recorder"]


class FeatureRequestRecorder(BatchRecorder[Mapping[str, Any]]):
    """Writes submitted rows (a mapping of ``COLUMNS``) to ``feedback/feature_requests`` on its
    thread."""

    def __init__(
        self,
        writer: FeedbackWriter,
        maxsize: int = 500,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._writer = writer
        super().__init__(JOB, "requests", BATCH, maxsize, clock)

    def submit(self, row: Mapping[str, Any]) -> bool:
        """Queue ``row`` for writing; ``False`` (dropped, logged) when the queue is full. Never
        raises."""
        return self._put(row)

    def _write(self, items: list[Mapping[str, Any]], now: datetime) -> None:
        frame = _frame(items).drop_duplicates(KEY, keep="last")
        run_id = self.run_id(frame["session_date"].max(), now)
        with self._writer.publishing(run_id, now):
            for session, part in frame.groupby("session_date", sort=True):
                rows = part.assign(run_id=run_id).reset_index(drop=True)
                self._writer.write_feedback(TABLE, cast(date, session), run_id, rows)


def _frame(rows: list[Mapping[str, Any]]) -> pd.DataFrame:
    """The stamped frame of ``rows``: a column a row lacks is null."""
    frame = pd.DataFrame([{c: r.get(c) for c in COLUMNS} for r in rows], columns=list(COLUMNS))
    ts = pd.to_datetime(frame["ts"], utc=True)
    return frame.assign(
        ts=ts,
        session_date=[exchange_date(t.to_pydatetime()) for t in ts],
        knowledge_ts=ts,
        source=SOURCE,
    )


def open_request_recorder(data_url: str) -> FeatureRequestRecorder:
    """A recorder writing to the store at ``data_url`` (the API's)."""
    return FeatureRequestRecorder(FeedbackWriter(open_backend(data_url)))
