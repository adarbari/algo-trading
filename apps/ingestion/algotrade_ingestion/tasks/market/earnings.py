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

A calendar day the run failed to fetch carries the previous snapshot's forecasts forward
(``carried_from``), so a failed fetch never cancels knowledge (ADR 0050 decision 3): the
rows the latest earlier snapshot holds for that report day are copied unchanged into this
one (their ``known_from`` kept) with ``carried_from`` = the session of the snapshot that
fetched them (null on fetched rows). So are a fetched day's rows of a ticker that does not
resolve today (it would otherwise lose its id). A day no earlier snapshot holds stays
uncovered. Counted as ``carried_rows``, with the days in ``carried_days``.
"""

from datetime import date, timedelta
from functools import partial

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import CARRIED_FROM, COMMON, KNOWN_FROM
from algotrade_ingestion.tasks.framework.run import FAILURES, IngestRun, TaskContext, status_label
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


class _Previous:
    """The latest snapshot stored before the run's session, read once: what was known then."""

    def __init__(self, run: IngestRun) -> None:
        earlier = [d for d in run.reader.dates(TABLE) if d < run.session]
        frame = run.reader.table(TABLE, max(earlier)) if earlier else None
        self.rows = frame if frame is not None else pd.DataFrame(columns=["instrument_id", "ts"])
        self.days = pd.to_datetime(self.rows["ts"], utc=True).dt.date

    def carried(
        self, day: date, have: pd.DataFrame | None, symbols: set[str] | None = None
    ) -> pd.DataFrame:
        """Its rows for report ``day`` (of ``symbols`` only, when given) that ``have`` lacks,
        ready to store again: stamps dropped, ``carried_from`` set (module doc)."""
        rows = self.rows[self.days == day]
        if symbols is not None:
            rows = rows[rows["symbol"].isin(symbols)] if "symbol" in rows.columns else rows[:0]
        if have is not None and len(have):
            rows = rows[~rows["instrument_id"].isin(set(have["instrument_id"]))]
        if rows.empty:
            return pd.DataFrame()
        stored = pd.to_datetime(rows["session_date"]).dt.date
        origin = stored
        if CARRIED_FROM in rows.columns:  # a row carried before keeps the session that fetched it
            origin = rows[CARRIED_FROM].where(rows[CARRIED_FROM].notna(), stored)
        # A row stored before known_from existed: known from min(its session, its report date).
        report = pd.to_datetime(rows["ts"], utc=True).dt.date
        fallback = [min(s, r) for s, r in zip(stored, report, strict=True)]
        known = (
            rows[KNOWN_FROM] if KNOWN_FROM in rows.columns else pd.Series(None, index=rows.index)
        )
        known = known.where(known.notna(), pd.Series(fallback, index=rows.index))
        out = rows.drop(columns=list(COMMON)).assign(**{CARRIED_FROM: list(origin)})
        return out.assign(**{KNOWN_FROM: list(known)})


def _carry_forward(
    run: IngestRun, previous: _Previous, days: list[date], fetched: pd.DataFrame
) -> pd.DataFrame:
    """The previous snapshot's rows for the window's failed days and for today's unresolved
    tickers, counted in the run stats (module doc)."""
    report = pd.to_datetime(fetched["ts"], utc=True).dt.date if len(fetched) else None
    resolver = run.resolver()
    parts = []
    for day in days:
        mine = fetched[report == day] if report is not None else None
        if status_label(run.items.get(day.isoformat(), "")) in FAILURES:
            parts.append(previous.carried(day, mine))
        elif mine is not None and len(mine) and "symbol" in mine.columns:
            lost = {str(s) for s in mine["symbol"] if not resolver.knows(str(s))}
            if lost:
                parts.append(previous.carried(day, mine, lost))
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    carried = pd.concat(parts, ignore_index=True)
    run.stats["carried_rows"] = len(carried)
    run.stats["carried_days"] = sorted(
        {d.isoformat() for d in pd.to_datetime(carried["ts"], utc=True).dt.date}
    )
    return carried


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
        window = report_days(start or session, days)
        carried = _carry_forward(run, _Previous(run), window, rows)
        rows = pd.concat([rows, carried], ignore_index=True) if len(carried) else rows
        if not rows.empty:
            rows = rows.sort_values(["ts", "instrument_id"]).reset_index(drop=True)
            run.write(TABLE, rows, source.name)
        run.stats.update(
            window=[(start or session).isoformat(), days],
            dates_failed=run.failures(),
            rows=len(rows),
            companies=int(rows["symbol"].nunique()) if "symbol" in rows.columns else 0,
            reported=int(rows["reported"].fillna(False).astype(bool).sum())
            if "reported" in rows.columns
            else 0,
            unresolved=run.unresolved,
            carried_rows=run.stats.get("carried_rows", 0),
        )
    return run.record


def _stage_day(run: IngestRun, source: Source, day: date) -> str:
    """One backfill day: fetched, resolved as of the day, staged with ``known_from`` (an
    empty day stages nothing, replacing what an earlier attempt carried for it)."""
    rows = _fetch_day(run, source, day)
    if rows is None:
        run.stage(TABLE, day.isoformat(), pd.DataFrame(), source.name)
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
        previous, failed = _Previous(run), [date.fromisoformat(d) for d in run.retryable()]
        carried = _carry_forward(run, previous, failed, pd.DataFrame())
        report = pd.to_datetime(carried["ts"], utc=True).dt.date if len(carried) else None
        for failed_day in failed:
            part = carried[report == failed_day] if report is not None else carried
            if len(part):
                run.stage(TABLE, failed_day.isoformat(), part.reset_index(drop=True), source.name)
        rows = run.publish(TABLE, sort_by="ts")
        run.stats.update(
            window=[start.isoformat(), end.isoformat()],
            sessions=len(window),
            fetched=len(todo),
            already_done=len(window) - len(todo),
            pre_snapshot_rows=run.stats.get("pre_snapshot_rows", 0),
            carried_rows=run.stats.get("carried_rows", 0),
            dates_failed=run.failures(),
            rows=rows,
            unresolved=run.unresolved,
        )
    return run.record
