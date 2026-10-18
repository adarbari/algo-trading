"""Cboe VIX futures by expiry -> ``volatility/vx_futures``: one partition per trade date (EB D3).

One CSV per expiry (``vendors/cboe/vx_futures.py``: the whole life of the contract, one row per
trade date), asked for every expiry of a window by Cboe's rule (the directory cannot be listed);
an expiry that never existed answers 403 and is ``NO_DATA``. The rows are staged per expiry and
published at the end as one partition per trade date (``stage_sessions`` / ``publish_sessions``),
so a window of years is one commit and an interrupted run resumes from its staging
(``resume=True``): the items already done stay done.

**Known from.** Cboe regenerates an expiry's file about 01:05 New York time the morning after
the trade date (measured 2026-10-17), so a row is knowable from the NEXT SESSION after its trade
date: ``known_from`` = ``next_session(trade date)`` for a backfill and the nightly alike (the
ADR 0050 pattern; ``knowledge_ts`` stays the write instant). ``data.volatility.vx_futures`` reads
a session S as the rows with ``known_from <= S``. A ``--force`` refetch writes only rows that are
new or differ from the stored ones; a restated row is known from the later of that and the
session after the fetch's own day, and the table keeps both versions (key includes
``known_from``). The incremental ``> through`` filter never sees a revision of an older row
(Cboe rewrites old files): only ``--force`` does. Contract days use the NYSE calendar, so a
CFE-only contract on an NYSE holiday would show as NO_DATA.

**Incremental and resumable.** Only the rows after the latest trade date an earlier run stored
for the expiry are written (item ``OK: <n> rows through <date>``): a stored row is never
restated by a refetch. An expiry is DONE once an earlier finished run of a session after its
expiry date fetched it (the file then holds the last row) or found it missing (it never
existed): it is not asked for again (``NOT_DUE``). ``force`` asks for every expiry of the window
and writes every row (the merge keeps the latest run's). The nightly window is the expiries from
``LOOKBACK_DAYS`` before the session (the last rows of a contract that just expired) to
``MONTHLY_AHEAD_DAYS`` out, with the weeklies ``WEEKLY_AHEAD_DAYS`` out.

``STOP_AFTER_FAILED`` fetch errors in a row (a block, an outage) end the run: the rest stay
pending for the next one.
"""

import re
from collections.abc import Mapping
from datetime import date, timedelta
from functools import partial
from typing import Any, cast

import pandas as pd

from algotrade.core.time.calendar import (
    exchange_date,
    is_session,
    next_session,
    previous_session,
    session_on_or_before,
    third_friday,
    weekdays_between,
)
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import (
    FETCH_ERROR,
    IngestRun,
    NoResponseError,
    TaskContext,
    finished_runs,
    status_label,
)
from algotrade_sources.framework.base import FetchRequest, Source

TASK = "vx_futures"
TABLE = "volatility/vx_futures"
FIRST_EXPIRY = date(2013, 1, 1)  # Cboe's free history starts with the 2013 contracts
SETTLE_LEAD_DAYS = 30
WEDNESDAY = 2
LOOKBACK_DAYS = 7
MONTHLY_AHEAD_DAYS = 330  # Cboe lists about nine monthly contracts
WEEKLY_AHEAD_DAYS = 56
STOP_AFTER_FAILED = 8
DONE = ("OK", "NO_DATA")  # item statuses of an expiry that was fetched (or never existed)
_THROUGH = re.compile(r"through (\d{4}-\d{2}-\d{2})")


def monthly_expiry(year: int, month: int) -> date:
    """The standard VX expiry of ``year``-``month``: 30 days before the third Friday of the
    next month (before the business day preceding it when that Friday is a holiday); a
    Wednesday that is a holiday moves to the session before (checked against the files:
    2024-06-18, 2014-03-18)."""
    after = date(year + month // 12, month % 12 + 1, 1)
    friday = third_friday(after.year, after.month)
    base = friday if is_session(friday) else previous_session(friday)
    return session_on_or_before(base - timedelta(SETTLE_LEAD_DAYS))


def monthly_expiries(start: date, end: date) -> list[date]:
    """The monthly VX expiries in ``start..end`` (a monthly expiry falls in its own month)."""
    out, month = [], date(start.year, start.month, 1)
    while month <= end:
        day = monthly_expiry(month.year, month.month)
        if start <= day <= end:
            out.append(day)
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    return out


def expiry_dates(start: date, end: date, weeklies_until: date | None = None) -> list[date]:
    """Every VX expiry in ``start..end`` by Cboe's rule, ascending: the monthly ones, and the
    Wednesday weeklies up to ``weeklies_until`` (default ``end``: the weeklies are listed only
    a few weeks ahead). Some never existed (weeklies before they were listed): the file answers
    403."""
    last = min(end, weeklies_until or end)
    weekly = {session_on_or_before(w) for w in weekdays_between(start, last, WEDNESDAY)}
    return sorted({d for d in weekly if start <= d <= last} | set(monthly_expiries(start, end)))


def nightly_window(session: date) -> tuple[date, date]:
    """The expiries a nightly run asks for: ``(start, end)`` around ``session``."""
    return session - timedelta(LOOKBACK_DAYS), session + timedelta(MONTHLY_AHEAD_DAYS)


def _history(runs: list[RunRecord]) -> tuple[dict[date, date], set[date]]:
    """From the finished runs: expiry -> the latest trade date stored, and the expiries that
    are done (fetched after their expiry date, or found never to have existed)."""
    through: dict[date, date] = {}
    done: set[date] = set()
    for record in runs:
        for key, status in record.items.items():
            try:
                expiry = date.fromisoformat(key)
            except ValueError:
                continue
            label = status_label(status)
            if label == "OK":
                match = _THROUGH.search(status)
                if match:
                    last = date.fromisoformat(match.group(1))
                    through[expiry] = max(last, through.get(expiry, last))
            if label in DONE and record.session_date > expiry:
                done.add(expiry)
    return through, done


VALUES = ("open", "high", "low", "close", "settle", "change", "volume", "efp", "open_interest")


def _equal(new: Any, old: Any) -> bool:
    """NA-safe equality of two stored values (an Int64 count may be NA on either side)."""
    if pd.isna(new) or pd.isna(old):
        return bool(pd.isna(new) and pd.isna(old))
    return bool(new == old)


def _restated(run: IngestRun, rows: pd.DataFrame) -> pd.DataFrame:
    """``--force``: only the rows that are new or differ from the stored ones. A restated row is
    known from the session AFTER the fetch's own day (``next_session(exchange_date(clock))``) when
    that is later than its trade date's next session, so a past session never sees a value Cboe
    changed afterwards; the reader keeps, per contract and trade date, the latest version known."""
    learned = next_session(exchange_date(run.clock()))
    stored = run.reader.table_range(
        TABLE,
        rows["session_date"].min(),
        rows["session_date"].max(),
        None,
        [rows["instrument_id"].iloc[0]],
    )
    if stored is None or stored.empty:
        return rows
    stored = stored.assign(session_date=pd.to_datetime(stored["session_date"]).dt.date)
    stored = stored.sort_values("known_from", kind="stable").drop_duplicates(
        "session_date", keep="last"
    )
    old = stored.set_index("session_date")
    keep, known = [], []
    for row in rows.itertuples(index=False):
        before = old.loc[row.session_date] if row.session_date in old.index else None
        if before is None:
            keep.append(True)
            known.append(row.known_from)
            continue
        same = all(_equal(getattr(row, c), before[c]) for c in VALUES)
        keep.append(not same)
        known.append(max(cast(date, row.known_from), learned))
    out = rows.assign(known_from=known)
    return out[keep].reset_index(drop=True)


def _fetch_expiry(
    run: IngestRun, source: Source, expiry: date, through: Mapping[date, date], force: bool
) -> str:
    try:
        normalized = run.fetch(source, FetchRequest(expiry.isoformat(), session_date=run.session))
    except NoResponseError:
        return "NO_DATA"
    frame = normalized.tables[TABLE] if normalized else None
    if frame is None or frame.empty:
        return "NO_DATA"
    seen = through.get(expiry)
    new = frame if force or seen is None else frame[frame["session_date"] > seen]
    new = new.assign(known_from=[next_session(d) for d in new["session_date"]])
    if force:
        new = _restated(run, new)
    if not new.empty:
        run.stage_sessions(TABLE, expiry.isoformat(), new.reset_index(drop=True), source.name)
    last = max(frame["session_date"])
    return f"OK: {len(new)} rows through {last.isoformat()}"


def ingest_vx_futures(
    ctx: TaskContext,
    source: Source,
    session: date,
    start: date | None = None,
    end: date | None = None,
    force: bool = False,
) -> RunRecord:
    """Store the new rows of every VX expiry in ``start..end`` (default: the nightly window of
    ``session``; an explicit window is the backfill, ``--from 2013-01-01``)."""
    default = nightly_window(session)
    first, last = max(start or default[0], FIRST_EXPIRY), end or default[1]
    if first > last:
        raise ValueError(f"empty window: {first} > {last}")
    through, done = ({}, set()) if force else _history(finished_runs(ctx.writer, TASK))
    weeklies_until = session + timedelta(WEEKLY_AHEAD_DAYS) if end is None else None
    failed_in_a_row = 0
    with IngestRun(ctx, TASK, session, resume=True) as run:
        for expiry in expiry_dates(first, last, weeklies_until):
            key = expiry.isoformat()
            if key in run.items:
                continue  # done by the run this one resumes
            if expiry in done:
                run.record_item(key, "NOT_DUE")
                continue
            status = run.attempt(key, partial(_fetch_expiry, run, source, expiry, through, force))
            failed_in_a_row = failed_in_a_row + 1 if status_label(status) == FETCH_ERROR else 0
            run.checkpoint()
            if failed_in_a_row >= STOP_AFTER_FAILED:
                run.partial(f"{STOP_AFTER_FAILED} fetch errors in a row: the rest is pending")
                break
        written = run.publish_sessions(TABLE)
        stored = [d for d in run.reader.dates(TABLE) if d <= session]
        asked = {k: v for k, v in run.items.items() if status_label(v) != "NOT_DUE"}
        run.stats.update(
            window=[first.isoformat(), last.isoformat()],
            expiries=len(asked),
            listed=sum(status_label(v) == "OK" for v in asked.values()),
            rows=sum(written.values()),
            sessions_written=len(written),
            latest=max(stored).isoformat() if stored else None,
            items=run.counts(),
        )
    return run.record
