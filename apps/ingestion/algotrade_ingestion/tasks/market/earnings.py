"""Store the earnings calendar as point-in-time events (``events/earnings``).

Each run fetches a window of calendar dates and writes them all into the partition of the
*run's* session date: "on session D we knew these companies would report on these dates".
Dates change (companies confirm or move them), so each night's snapshot is kept and readers
choose by session. Past windows (``start`` in the past) backfill reported results. Symbols
resolve to ids through the reference as of the session (ADR 0018).
"""

from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.framework.base import FetchRequest, Source
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "earnings_calendar"
TABLE = "events/earnings"


def report_days(start: date, days: int) -> list[date]:
    """Exchange sessions in ``[start, start + days)``: the days companies report on."""
    return sessions_between(start, start + timedelta(days - 1))


def _one_day(run: IngestRun, source: Source, day: date, frames: list[pd.DataFrame]) -> str:
    normalized = run.fetch(source, FetchRequest(day.isoformat(), session_date=run.session))
    if normalized is None or normalized.tables[TABLE].empty:
        return "EMPTY"
    frames.append(normalized.tables[TABLE])
    return f"OK: {len(normalized.tables[TABLE])} rows"


def ingest_earnings(
    ctx: TaskContext, source: Source, session: date, start: date | None = None, *, days: int
) -> RunRecord:
    frames: list[pd.DataFrame] = []
    with IngestRun(ctx, TASK, session) as run:
        for day in report_days(start or session, days):
            run.attempt(day.isoformat(), partial(_one_day, run, source, day, frames))
        rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not rows.empty:
            rows = run.resolve(rows).drop_duplicates(subset=["instrument_id", "ts"], keep="last")
            rows = rows.replace({np.nan: None}).sort_values(["ts", "instrument_id"])
            rows = rows.reset_index(drop=True)
            run.write(TABLE, rows, source.name)
        run.stats.update(
            window=[(start or session).isoformat(), days],
            dates_failed=run.failures(),
            rows=len(rows),
            companies=int(rows["symbol"].nunique()) if len(rows) else 0,
            reported=int(rows["reported"].sum()) if len(rows) else 0,
            unresolved=run.unresolved,
        )
    return run.record
