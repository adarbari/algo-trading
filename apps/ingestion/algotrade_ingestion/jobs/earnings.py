"""Store the earnings calendar as point-in-time events (``events/earnings``).

Each run fetches a window of calendar dates and writes them all into the partition of the
*run's* session date: "on session D we knew these companies would report on these dates".
Dates change (companies confirm or move them), so each night's snapshot is kept and readers
choose by session. Past windows (``start`` in the past) backfill reported results. Symbols
resolve to ids through the reference as of the session (ADR 0018).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.common import stamp, with_ids
from algotrade_ingestion.sources.base import FetchRequest, Source
from algotrade_ingestion.sources.nasdaq_earnings import TABLE

JOB = "earnings_calendar"


def weekdays(start: date, days: int) -> list[date]:
    """Weekdays in ``[start, start + days)``. Holidays are fetched too (they return no rows)."""
    return [start + timedelta(i) for i in range(days) if (start + timedelta(i)).weekday() < 5]


def ingest_earnings(
    writer: StoreWriter,
    reader: StoreReader,
    source: Source,
    session: date,
    start: date | None = None,
    days: int = 60,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    run_id = new_run_id(JOB, session, now)
    frames, failed = [], []
    for day in weekdays(start or session, days):
        request = FetchRequest(day.isoformat(), session_date=session)
        try:
            payload = source.fetch(request)
            if payload is None:
                raise ValueError("no response")
            writer.raw.put(source.name, source.dataset, session, run_id, day.isoformat(), payload)
            normalized = source.normalize(request, payload)
            if normalized is not None and not normalized.tables[TABLE].empty:
                frames.append(normalized.tables[TABLE])
        except Exception as exc:
            failed.append(f"{day.isoformat()}: {exc}")
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    unresolved = 0
    if not rows.empty:
        rows, unresolved = with_ids(rows, reader.resolver(session))
        rows = rows.drop_duplicates(subset=["instrument_id", "ts"], keep="last")
        rows = (
            rows.replace({np.nan: None}).sort_values(["ts", "instrument_id"]).reset_index(drop=True)
        )
        writer.write_table(TABLE, session, run_id, stamp(rows, session, now, source.name, run_id))
    stats = {
        "window": [(start or session).isoformat(), days],
        "dates_failed": failed,
        "rows": len(rows),
        "companies": int(rows["symbol"].nunique()) if len(rows) else 0,
        "reported": int(rows["reported"].sum()) if len(rows) else 0,
        "unresolved": unresolved,
    }
    record = RunRecord(
        run_id,
        JOB,
        session,
        now,
        RunStatus.PARTIAL if failed else RunStatus.COMPLETE,
        now,
        stats=stats,
    )
    writer.save_run(record)
    return record
