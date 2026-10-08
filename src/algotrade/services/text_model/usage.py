"""Record text-model usage in the background: ``usage/llm_calls``, one atomic run per batch
(ADR 0057), as the live-quote recorder does (``services/live/recorder.py``, ADR 0028).

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

import logging
import queue
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, cast

import pandas as pd

from algotrade.core.time.calendar import exchange_date
from algotrade.data import StoreReader
from algotrade.data.usage import spent_by_day
from algotrade.storage.factory import open_backend
from algotrade.storage.runs import start_run
from algotrade.storage.tables.usage_writer import UsageWriter

log = logging.getLogger(__name__)

TABLE = "usage/llm_calls"
JOB = "llm_usage"
SOURCE = "text_model"
BATCH = 100  # rows per run at most
COLUMNS = (
    "ts", "provider", "model", "use_case", "user", "input_tokens", "output_tokens", "latency_s",
    "cost_usd", "cost_basis", "outcome", "fell_back_from",
)  # fmt: skip
_STOP = None


class UsageSink(Protocol):
    def submit(self, row: Mapping[str, Any]) -> bool: ...


Seed = Callable[[date, date], dict[date, float]]


class UsageRecorder:
    """Writes submitted rows (a mapping of ``COLUMNS``) to ``usage/llm_calls`` on its thread."""

    def __init__(
        self,
        writer: UsageWriter,
        maxsize: int = 500,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._writer, self._clock = writer, clock
        self._queue: queue.Queue[Mapping[str, Any] | None] = queue.Queue(maxsize)
        self._last_run = ""
        self.written = 0  # runs committed
        self._thread = threading.Thread(target=self._drain, name="usage-recorder", daemon=True)
        self._thread.start()

    def submit(self, row: Mapping[str, Any]) -> bool:
        """Queue ``row`` for writing; ``False`` (dropped, logged) when the queue is full. Never
        raises."""
        try:
            self._queue.put_nowait(row)
        except queue.Full:
            log.warning("usage recorder queue full: a text-model call is not recorded")
            return False
        except Exception:
            log.exception("usage recorder could not queue a row")
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
            rows = [b for b in batch if b is not None]
            try:
                if rows:
                    self._write(rows)
            except Exception:
                log.exception("text-model usage not recorded (%d rows)", len(rows))
            finally:
                for _ in batch:
                    self._queue.task_done()
            if any(b is None for b in batch):
                return

    def _write(self, rows: list[Mapping[str, Any]]) -> None:
        now = self._clock()
        frame = _frame(rows).drop_duplicates(["ts", "provider", "use_case"], keep="last")
        run_id = self._run_id(frame["session_date"].max(), now)
        with self._writer.publishing(run_id, now):
            for session, part in frame.groupby("session_date", sort=True):
                self._writer.write_usage(
                    TABLE,
                    cast(date, session),
                    run_id,
                    part.assign(run_id=run_id).reset_index(drop=True),
                )
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
