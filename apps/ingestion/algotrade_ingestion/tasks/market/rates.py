"""Treasury par yield curve -> ``rates/treasury``: one partition per curve date.

The source serves one calendar year per request, so a window costs one request per year
it touches (a 2024-2026 backfill is three requests). Each curve date in the window becomes
its own partition (``session_date`` = the curve date): the source's rows, one per tenor
with the par yield, its tenor in days and the continuous rate (ADR 0021).
Dates already stored are skipped unless forced. The bond market keeps its own holidays
(Columbus Day, Veterans Day), so an exchange session without a curve is normal: the read
API falls back to the latest curve on or before a date (``data.rates.curve``).
"""

from datetime import date
from functools import partial

import pandas as pd

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.framework.base import FetchRequest, Source
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "treasury_rates"
TABLE = "rates/treasury"


def _one_year(
    run: IngestRun, source: Source, year: int, window: tuple[date, date], skip: set[date]
) -> str:
    normalized = run.fetch(source, FetchRequest(str(year), session_date=run.session))
    frame = normalized.tables[TABLE] if normalized else None
    if frame is None or frame.empty:
        return "NO_DATA"
    days = pd.to_datetime(frame["ts"], utc=True).dt.date
    written = 0
    for day, rows in frame.groupby(days, sort=True):
        if not window[0] <= day <= window[1] or day in skip:
            continue
        run.write(TABLE, rows.reset_index(drop=True), source.name, session=day)
        written += 1
    return f"OK: {written} curves"


def ingest_rates(
    ctx: TaskContext, source: Source, start: date, end: date, force: bool = False
) -> RunRecord:
    """Store every curve dated ``start..end`` (inclusive) not already stored."""
    if start > end:
        raise ValueError(f"empty window: {start} > {end}")
    stored = set() if force else set(ctx.reader.dates(TABLE))
    with IngestRun(ctx, TASK, end) as run:
        for year in range(start.year, end.year + 1):
            run.attempt(str(year), partial(_one_year, run, source, year, (start, end), stored))
            run.checkpoint()
        in_window = [d for d in ctx.reader.dates(TABLE) if start <= d <= end]
        run.stats.update(
            window=[start.isoformat(), end.isoformat()],
            curves=len(in_window),
            latest=max(in_window).isoformat() if in_window else None,
            years=run.counts(),
        )
    return run.record
