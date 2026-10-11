"""Record the feedback events of a drafting session in the background:
``feedback/drafting_events``, one atomic run per batch (ADR 0066), as the text-model usage
recorder does (``services/text_model/usage.py``, ADR 0058).

``submit`` puts a row on a bounded queue and returns at once (a full queue drops the row,
logged, and a recorder that raises is caught: a request never waits on storage and never fails
on it). One daemon thread drains the queue; each batch is one run
(``drafting_feedback-<session>-<time>``, ``storage.runs``; no run record: not a job), its
partitions written pending and committed together (ADR 0022), dropped if a write fails. Rows are
stamped with the point-in-time columns (ADR 0007): ``session_date`` is the exchange calendar date
of the event, ``knowledge_ts`` the time of the event, ``source`` ``drafting_feedback``. A row is
keyed by its session, its id and its event, so a repeated submit of one event is one row. Only
``feedback/*`` tables, only through ``FeedbackWriter``.
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

TABLE = "feedback/drafting_events"
JOB = "drafting_feedback"
SOURCE = "drafting_feedback"
BATCH = 100  # rows per run at most
KEY = ["draft_session_id", "event_id", "event"]  # as the table's key (schemas.py)
COLUMNS = (
    "event_id", "draft_session_id", "ts", "user", "doc_kind", "doc_id", "event", "call_ids",
    "catalogue_version", "prompt_version", "draft_hash", "saved_hash", "sentence", "payload",
)  # fmt: skip

__all__ = ["FeedbackRecorder", "FeedbackSink", "open_recorder"]


class FeedbackRecorder(BatchRecorder[Mapping[str, Any]]):
    """Writes submitted rows (a mapping of ``COLUMNS``) to ``feedback/drafting_events`` on its
    thread."""

    def __init__(
        self,
        writer: FeedbackWriter,
        maxsize: int = 500,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._writer = writer
        super().__init__(JOB, "events", BATCH, maxsize, clock)

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


def open_recorder(data_url: str) -> FeedbackRecorder:
    """A recorder writing to the store at ``data_url`` (the API's)."""
    return FeedbackRecorder(FeedbackWriter(open_backend(data_url)))
