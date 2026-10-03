"""Daily bars from Massive: one ``bars/1d`` partition per session date, unadjusted.

Dates already stored are skipped unless forced, so a 2-year backfill (~500 requests at
5/minute, ~1h45m) can be interrupted and resumed. Sessions come from the exchange calendar
(``core/calendar.py``); a session the vendor has no rows for is recorded, not an error.
Vendor tickers become ids through the reference as of each session (ADR 0018); the loop
itself (raw save, ids, stamping, run record) is ``IngestRun``'s.
"""

from collections.abc import Sequence
from datetime import date
from functools import partial

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.sources.base import FetchRequest, Source
from algotrade_ingestion.tasks.framework import IngestRun, TaskContext

TASK = "daily_bars"
BARS = "bars/1d"
CHECKPOINT_EVERY = 5


def _one_session(run: IngestRun, source: Source, day: date) -> str:
    request = FetchRequest(day.isoformat(), session_date=day)
    normalized = run.fetch(source, request)
    bars = normalized.tables[BARS] if normalized else None
    if bars is None or bars.empty:
        return "NO_SESSION"
    before = run.unresolved
    bars = run.resolve(bars, as_of=day, keep_symbol=False)
    bars = bars.drop_duplicates("instrument_id", keep="last").sort_values("instrument_id")
    run.write(BARS, bars, source.name, session=day)
    invalid = normalized.notes.get("invalid_rows", 0) if normalized else 0
    unknown = run.unresolved - before
    notes = (f", {invalid} invalid dropped" if invalid else "") + (
        f", {unknown} unresolved" if unknown else ""
    )
    return f"OK: {len(bars)} bars{notes}"


def ingest_daily_bars(
    ctx: TaskContext, source: Source, sessions: Sequence[date], force: bool = False
) -> RunRecord:
    stored = set(ctx.reader.dates(BARS))
    with IngestRun(ctx, TASK, max(sessions)) as run:
        for i, day in enumerate(sorted(sessions), start=1):
            if day in stored and not force:
                run.record_item(day.isoformat(), "STORED")
                continue
            run.attempt(day.isoformat(), partial(_one_session, run, source, day))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        run.stats["sessions"] = run.counts()
    return run.record
