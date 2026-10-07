"""``earnings@v1``: the next and last earnings dates as known on the session.

Input: every ``events/earnings`` row known on or before the session (``data.events``' one
read rule, ADR 0050: its ``known_from``, else the session that stored it). Two kinds of row:

- a **forecast** row (known from the session that stored it): a snapshot's calendar, "by
  session S we knew this company would report on this date". Dates move, so for each report
  date X the authority is the LATEST snapshot whose date range covers X (from its own
  session, or its earliest row if earlier, to its latest row); a forecast another snapshot
  listed for X but the authority omits was moved or cancelled, and is ignored;
- a **history** row (known before the session that fetched it: last week's results in a
  nightly window, a backfilled report known from its report date): a fact of record, always
  kept, whatever a later snapshot lists. Its day still counts in its snapshot's range.

A row a snapshot carried forward over a day its fetch failed (``carried_from``: the session
that fetched it) keeps the kind it had there, so the failed day cancels nothing.

Only snapshots stored on or before the session decide (ranges, authorities): a later
partition contributes only its reported history rows (known by the session) for reports the
session's own partitions do not hold, never its forecasts or carried copies and never a field
of a report the session already had, so recomputing a session after later nights changes
nothing it knew.

One row per (instrument, report date): a history row over a forecast, then the latest
snapshot.

    next_earnings_date  the first valid report date on or after the session
    earnings_time       pre / post (after the close) / unknown, for that date (a report
                        stored as ``intraday``, during the session, reads unknown: neither)
    days_to_earnings    sessions after the session up to the report date (0: today;
                        ``core.time.calendar``)
    date_confirmed      whether the source confirmed the date; null (the Nasdaq calendar
                        does not say)
    last_earnings_date  the latest valid report date before the session

One row per instrument with a next or a last date; others have no row (UNKNOWN).
"""

from datetime import date
from functools import cache
from typing import Any

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "earnings"
VERSION = 1
EVENTS = "events/earnings"
TIMES = {"pre_market": "pre", "after_hours": "post"}
# The row's knowable date (``data.events``' one read rule, ADR 0050); before its stored session:
# a history row (a reported result), else a forecast row of that session's calendar.
KNOWN_FROM = "known_from"
# A forecast copied forward over a day the fetch failed: the session that fetched it, which
# decides its kind (a forecast stays a forecast in every snapshot that carries it).
CARRIED_FROM = "carried_from"

_REPORT = f"{EVENTS}.ts"
_NO_NEXT = "no report date on or after the session in the calendars stored by then"
# A row with no next date reads "Not announced" (ADR 0046), from earnings_schedule@v1.
_NOT_ANNOUNCED: dict[str, Any] = {
    "null_status": "earnings_schedule.next_status@v1",
    "explained_statuses": ("NOT_ANNOUNCED",),
}

FEATURES = (
    Feature(
        "next_earnings_date", "date", "date",
        "The first report date on or after the session, as known on the session",
        f"{_NO_NEXT} (the row exists for a last date)", inputs=(_REPORT,), **_NOT_ANNOUNCED,
    ),
    Feature(
        "earnings_time", "str", "category",
        "When the next report is due: pre (before the open), post (after the close), unknown",
        _NO_NEXT, "label", categories=("pre", "post", "unknown"), inputs=(f"{EVENTS}.time",),
        **_NOT_ANNOUNCED,
    ),
    Feature(
        "days_to_earnings", "int", "sessions",
        "Exchange sessions after the session up to the next report date (0: reports today)",
        _NO_NEXT, valid_range=(0, None), inputs=(_REPORT,), **_NOT_ANNOUNCED,
    ),
    Feature(
        "date_confirmed", "bool", "flag", "Whether the source confirmed the next report date",
        f"the source does not say (the Nasdaq calendar never does), or {_NO_NEXT}",
        inputs=(f"{EVENTS}.date_confirmed",),
    ),
    Feature(
        "last_earnings_date", "date", "date", "The latest report date before the session",
        "no earlier report date known by the session (the calendars start with the first "
        "stored snapshot, the earnings backfill from its first day)", inputs=(_REPORT,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


# The ``source`` of the SEC 8-K Item 2.02 results rows the ``filings`` task stores in
# ``events/earnings`` (``EARNINGS_8K_SOURCE`` in storage.tables.schemas; rollups import no storage).
# ``earnings@v1`` reads the calendar rows only: the 8-K rows join in a later version with the
# per-quarter precedence between the two sources (ADR 0050 decision 3), so v1 keeps its values.
SEC_8K_SOURCE = "sec_8k"


def _report_days(stored: pd.DataFrame) -> pd.Series:
    """The report day of each row, naive: ``earnings_date`` where the writer gave one (an 8-K
    accepted after 20:00 New York time has a ``ts`` on the next UTC day; the Nasdaq calendar's
    ``ts`` is midnight UTC of the day), else the UTC date of ``ts``."""
    from_ts = pd.to_datetime(stored["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    if "earnings_date" not in stored.columns:
        return from_ts
    given = pd.to_datetime(stored["earnings_date"], errors="coerce")
    return given.where(given.notna(), from_ts)


def valid_events(stored: pd.DataFrame, session: date, since: date | None = None) -> pd.DataFrame:
    """The valid rows for each report date as of ``session`` (see the module doc): every
    history row, and the forecast rows of the authority snapshot; one row per (instrument,
    report date), a history row over a forecast, then the latest snapshot.

    Only snapshots stored on or before ``session`` form ranges and act as authorities. A row
    of a later partition (visible through its ``known_from``) stays only as a reported
    history row: its forecasts are not known yet and its carried rows are copies of rows
    their origin snapshot holds.

    ``since``: only report dates on or after it (``anchored_vwap@v1`` needs none older). The
    snapshots' ranges still come from all their rows, so the rows kept are exactly those the
    full reading keeps for those dates; only the per-date work is limited to them. The work
    over every stored row is a vectorised group-by of two day columns."""
    if "source" in stored.columns:  # the 8-K results rows wait for the v2 precedence (above)
        stored = stored[stored["source"] != SEC_8K_SOURCE]
    report_day = _report_days(stored).to_numpy(dtype="datetime64[D]")
    snap_day = pd.to_datetime(stored["session_date"]).to_numpy(dtype="datetime64[D]")
    n = len(stored)
    history, carried, fetched_on = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool), snap_day
    if CARRIED_FROM in stored.columns:
        origin = pd.to_datetime(stored[CARRIED_FROM]).to_numpy(dtype="datetime64[D]")
        carried = ~np.isnat(origin)
        fetched_on = np.where(carried, origin, snap_day)
    if KNOWN_FROM in stored.columns:
        known = pd.to_datetime(stored[KNOWN_FROM]).to_numpy(dtype="datetime64[D]")
        history = ~np.isnat(known) & (known < fetched_on)
    reported = np.zeros(n, dtype=bool)
    if "reported" in stored.columns:
        reported = stored["reported"].fillna(False).astype(bool).to_numpy()
    stored_by = snap_day <= np.datetime64(session, "D")
    keep = np.ones(n, dtype=bool)
    if since is not None:
        keep = report_day >= np.datetime64(since, "D")
    from_authority = np.zeros(n, dtype=bool)
    if stored_by.any():
        frame = pd.DataFrame({"snapshot": snap_day[stored_by], "report": report_day[stored_by]})
        ranges = frame.groupby("snapshot")
        lo, hi = ranges["report"].min(), ranges["report"].max()
        snaps = lo.index.to_numpy(dtype="datetime64[D]")
        # A snapshot covers from its own session (the calendar it fetched starts there) or its
        # earliest row (the past days its window fetched), to its latest row.
        first = np.minimum(lo.to_numpy(dtype="datetime64[D]"), snaps)
        last_day = hi.to_numpy(dtype="datetime64[D]")
        target = np.flatnonzero(stored_by & keep)
        reports = np.unique(report_day[target])
        if len(reports):
            covers = (first[None, :] <= reports[:, None]) & (reports[:, None] <= last_day[None, :])
            # Snapshots are sorted ascending: the last covering one is the authority.
            authority = snaps[covers.shape[1] - 1 - np.argmax(covers[:, ::-1], axis=1)]
            at = np.searchsorted(reports, report_day[target])
            from_authority[target] = snap_day[target] == authority[at]
    later_fact = ~stored_by & history & reported & ~carried
    valid = np.flatnonzero(keep & ((stored_by & (from_authority | history)) | later_fact))
    rows: pd.DataFrame = stored.iloc[valid].assign(
        _stored_by=stored_by[valid], _history=history[valid]
    )
    rows = rows.assign(
        report=_report_days(rows).dt.date,
        snapshot=pd.to_datetime(rows["session_date"]).dt.date,
    )
    if rows["_history"].any():
        # A report kept twice: a row stored by the session wins (a later partition only adds
        # reports the session's own did not have, never changes a field of one), then the
        # history row, then the latest snapshot.
        ranked = rows.sort_values(["_stored_by", "_history", "snapshot"], kind="stable")
        last = ranked.drop_duplicates(["instrument_id", "report"], keep="last").index
        rows = rows[rows.index.isin(last)]
    return rows.drop(columns=["_stored_by", "_history"])


def _column(frame: pd.DataFrame, name: str) -> list[object]:
    """A column's values, or nulls when the source does not provide it."""
    return frame[name].tolist() if name in frame.columns else [None] * len(frame)


@cache
def _sessions_to(start: date, end: date) -> int:
    return sessions_to(start, end)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[EVENTS]
    assert stored is not None  # required input
    rows = valid_events(stored, session)
    rows = rows.sort_values(["instrument_id", "report"], kind="stable")
    upcoming = rows[rows["report"] >= session].drop_duplicates("instrument_id", keep="first")
    past = rows[rows["report"] < session].drop_duplicates("instrument_id", keep="last")
    nxt = pd.DataFrame(
        {
            "instrument_id": upcoming["instrument_id"].astype(str).to_numpy(),
            "next_earnings_date": upcoming["report"].to_numpy(),
            "earnings_time": [TIMES.get(str(t), "unknown") for t in _column(upcoming, "time")],
            "days_to_earnings": [_sessions_to(session, d) for d in upcoming["report"]],
            "date_confirmed": _column(upcoming, "date_confirmed"),
        }
    )
    last = pd.DataFrame(
        {
            "instrument_id": past["instrument_id"].astype(str).to_numpy(),
            "last_earnings_date": past["report"].to_numpy(),
        }
    )
    out = nxt.merge(last, on="instrument_id", how="outer")
    return out.sort_values("instrument_id", kind="stable").reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Next and last earnings dates, report time and sessions to the next report",
    (Input(EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
