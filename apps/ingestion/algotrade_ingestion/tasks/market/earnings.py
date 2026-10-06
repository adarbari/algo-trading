"""Store the earnings calendar as point-in-time events (``events/earnings``).

Each run fetches a window of calendar dates and writes them all into the partition of the
*run's* session date: "on session D we knew these companies would report on these dates".
Dates change (companies confirm or move them), so each night's snapshot is kept and readers
choose by session. Symbols resolve to ids through the reference (ADR 0018): as of the session
for the nightly window, as of the report date for a backfill.

Every row carries ``known_from`` (ADR 0050 decision 3) = the earlier of the run's session and
its report date: a forward row was knowable on the session that stored it, a past-dated row
(last week's reported results, a backfill) on its report date, so ``data.events`` serves a
backfilled 2019 report to the 2019 sessions after it.

The backfill (``backfill_earnings``, ``algotrade-ingest earnings --from D1 --to D2``) fetches
one calendar day per exchange session of a past window, staged day by day and published at
the end into the run session's partition: its rows are history rows (known before that
session), facts of record ``earnings@v1`` never cancels. It is resumable within its session:
a rerun for the same session continues an interrupted or partial run (its staged days are
kept, its failed days asked again); a run for a later session fetches the whole window
again, so each backfill partition holds the full window. Before the reference history starts
a ticker resolves through the earliest snapshot (a reused ticker goes to today's holder):
counted as ``pre_snapshot_rows``.
"""

from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import KNOWN_FROM
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "earnings_calendar"
HISTORY_TASK = "earnings_history"
TABLE = "events/earnings"
CHECKPOINT_EVERY = 20  # backfill days between saves of the run record


def report_days(start: date, days: int) -> list[date]:
    """Exchange sessions in ``[start, start + days)``: the days companies report on."""
    return sessions_between(start, start + timedelta(days - 1))


def with_known_from(rows: pd.DataFrame, session: date) -> pd.DataFrame:
    """``rows`` with ``known_from`` = min(``session``, the report date) (module doc)."""
    reports = pd.to_datetime(rows["ts"], utc=True).dt.date
    return rows.assign(**{KNOWN_FROM: [min(session, day) for day in reports]})


def _fetch_day(run: IngestRun, source: Source, day: date) -> pd.DataFrame | None:
    normalized = run.fetch(source, FetchRequest(day.isoformat(), session_date=run.session))
    if normalized is None or normalized.tables[TABLE].empty:
        return None
    return normalized.tables[TABLE]


def _one_day(run: IngestRun, source: Source, day: date, frames: list[pd.DataFrame]) -> str:
    rows = _fetch_day(run, source, day)
    if rows is None:
        return "EMPTY"
    frames.append(rows)
    return f"OK: {len(rows)} rows"


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
            rows = with_known_from(rows.replace({np.nan: None}), session)
            rows = rows.sort_values(["ts", "instrument_id"]).reset_index(drop=True)
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


def _stage_day(run: IngestRun, source: Source, day: date) -> str:
    """One backfill day: fetched, resolved as of the day, staged with ``known_from``."""
    rows = _fetch_day(run, source, day)
    if rows is None:
        return "EMPTY"
    rows = run.resolve(rows, as_of=day).drop_duplicates(["instrument_id", "ts"], keep="last")
    snapshot = run.resolver(day).snapshot
    if snapshot is not None and snapshot > day:  # before the reference history starts
        run.stats["pre_snapshot_rows"] = run.stats.get("pre_snapshot_rows", 0) + len(rows)
    rows = with_known_from(rows.replace({np.nan: None}), run.session)
    run.stage(TABLE, day.isoformat(), rows.reset_index(drop=True), source.name)
    return f"OK: {len(rows)} rows"


def backfill_earnings(
    ctx: TaskContext, source: Source, session: date, start: date, end: date
) -> RunRecord:
    """The calendar of every exchange session in ``start..end``, one request a day, into
    ``session``'s partition; a resumed run asks only the days it has not fetched (module
    doc)."""
    if start > end:
        raise ValueError(f"--from {start} is after --to {end}")
    with IngestRun(ctx, HISTORY_TASK, session, resume=True) as run:
        window = [d.isoformat() for d in sessions_between(start, end)]
        todo = [d for d in window if d not in run.items]  # a resume keeps its fetched days
        for i, day in enumerate(todo, 1):
            run.attempt(day, partial(_stage_day, run, source, date.fromisoformat(day)))
            if i % CHECKPOINT_EVERY == 0:
                run.checkpoint()
        rows = run.publish(TABLE, sort_by="ts")
        run.stats.update(
            window=[start.isoformat(), end.isoformat()],
            sessions=len(window),
            fetched=len(todo),
            already_done=len(window) - len(todo),
            pre_snapshot_rows=run.stats.get("pre_snapshot_rows", 0),
            dates_failed=run.failures(),
            rows=rows,
            unresolved=run.unresolved,
        )
    return run.record
