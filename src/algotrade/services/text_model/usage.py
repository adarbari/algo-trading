"""Record text-model usage in the background: ``usage/llm_calls``, one atomic run per batch
(ADR 0058), as the live-quote recorder does (``services/live/recorder.py``, ADR 0028).

The chain answers first and records afterwards: ``submit`` puts a row on a bounded queue and
returns at once (a full queue drops the row, logged, and a recorder that raises is caught: a
request never waits on storage and never fails on it). One daemon thread drains the queue;
each batch is one run (``llm_usage-<session>-<time>``, ``storage.runs``; no run record: not a
job), its partitions written pending and committed together (ADR 0022), dropped if a write
fails. Rows are stamped with the point-in-time columns (ADR 0007): ``session_date`` is the
exchange calendar date of the call, ``knowledge_ts`` the time of the call, ``source``
``text_model``. Only ``usage/*`` tables, only through ``UsageWriter``. ``store_seed`` reads what
the store holds back, for the budget ledger's counters at startup.
"""

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any, Protocol, cast

import pandas as pd

from algotrade.core.time.calendar import exchange_date
from algotrade.data import StoreReader
from algotrade.data.usage import spent_by_day
from algotrade.storage.factory import open_backend
from algotrade.storage.recording import BatchRecorder
from algotrade.storage.tables.usage_writer import UsageWriter

TABLE = "usage/llm_calls"
JOB = "llm_usage"
SOURCE = "text_model"
BATCH = 100  # rows per run at most
COLUMNS = (
    "ts", "provider", "model", "use_case", "user", "input_tokens", "output_tokens", "latency_s",
    "cost_usd", "cost_basis", "outcome", "fell_back_from",
)  # fmt: skip


class UsageSink(Protocol):
    def submit(self, row: Mapping[str, Any]) -> bool: ...


Seed = Callable[[date, date], dict[date, float]]


class UsageRecorder(BatchRecorder[Mapping[str, Any]]):
    """Writes submitted rows (a mapping of ``COLUMNS``) to ``usage/llm_calls`` on its thread."""

    def __init__(
        self,
        writer: UsageWriter,
        maxsize: int = 500,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._writer = writer
        super().__init__(JOB, "rows", BATCH, maxsize, clock)

    def submit(self, row: Mapping[str, Any]) -> bool:
        """Queue ``row`` for writing; ``False`` (dropped, logged) when the queue is full. Never
        raises."""
        return self._put(row)

    def _write(self, items: list[Mapping[str, Any]], now: datetime) -> None:
        frame = _frame(items).drop_duplicates(["ts", "provider", "use_case"], keep="last")
        run_id = self.run_id(frame["session_date"].max(), now)
        with self._writer.publishing(run_id, now):
            for session, part in frame.groupby("session_date", sort=True):
                rows = part.assign(run_id=run_id).reset_index(drop=True)
                self._writer.write_usage(TABLE, cast(date, session), run_id, rows)


def _frame(rows: list[Mapping[str, Any]]) -> pd.DataFrame:
    """The stamped frame of ``rows``: tokens as nullable integers (unknown is null, never 0)."""
    frame = pd.DataFrame([{c: r.get(c) for c in COLUMNS} for r in rows], columns=list(COLUMNS))
    ts = pd.to_datetime(frame["ts"], utc=True)
    for column in ("input_tokens", "output_tokens"):
        frame[column] = frame[column].astype("Int64")
    frame["cost_usd"] = frame["cost_usd"].astype("float64")
    return frame.assign(
        ts=ts,
        session_date=[exchange_date(t.to_pydatetime()) for t in ts],
        knowledge_ts=ts,
        source=SOURCE,
    )


def open_recorder(data_url: str) -> UsageRecorder:
    """A recorder writing to the store at ``data_url`` (the API's)."""
    return UsageRecorder(UsageWriter(open_backend(data_url)))


def store_seed(data_url: str) -> Seed:
    """What the store at ``data_url`` holds, for ``UsageLedger``'s counters at startup: USD
    spent per exchange date over a range."""
    reader = StoreReader(open_backend(data_url))
    return lambda start, end: spent_by_day(reader, start, end)
