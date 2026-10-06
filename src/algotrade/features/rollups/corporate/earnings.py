"""``earnings@v1``: the next and last earnings dates as known on the session.

Input: every ``events/earnings`` calendar snapshot stored on or before the session (the
earnings task stores, on each session, the calendar for the days ahead). Knowledge is as
stored: a snapshot says "on session S we knew these companies would report on these dates",
and dates move, so for each report date X the authority is the LATEST snapshot on or before
the session whose date range covers X (from its own session, or its earliest row if
earlier, to its latest row). A row an earlier snapshot listed for X but that
snapshot omits was moved or cancelled, and is ignored.

    next_earnings_date  the first valid report date on or after the session
    earnings_time       pre / post (after the close) / unknown, for that date
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
        "no earlier report date in the calendars stored by then (they start with the first "
        "stored snapshot; a backfill does not invent history)", inputs=(_REPORT,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def valid_events(stored: pd.DataFrame, since: date | None = None) -> pd.DataFrame:
    """The rows of the authoritative snapshot for each report date (see the module doc).

    ``since``: only report dates on or after it (``anchored_vwap@v1`` needs none older). The
    snapshots' ranges still come from all their rows, so the rows kept are exactly those the
    full reading keeps for those dates; only the per-date work is limited to them. The work
    over every stored row is a vectorised group-by of two day columns."""
    report_day = (
        pd.to_datetime(stored["ts"], utc=True).dt.tz_localize(None).to_numpy(dtype="datetime64[D]")
    )
    snap_day = pd.to_datetime(stored["session_date"]).to_numpy(dtype="datetime64[D]")
    ranges = pd.DataFrame({"snapshot": snap_day, "report": report_day}).groupby("snapshot")
    lo, hi = ranges["report"].min(), ranges["report"].max()
    snaps = lo.index.to_numpy(dtype="datetime64[D]")
    # A snapshot covers from its own session (the calendar it fetched starts there) or its
    # earliest row (a backfill of past dates), to its latest row.
    first = np.minimum(lo.to_numpy(dtype="datetime64[D]"), snaps)
    last_day = hi.to_numpy(dtype="datetime64[D]")
    keep = np.ones(len(stored), dtype=bool)
    if since is not None:
        keep = report_day >= np.datetime64(since, "D")
    reports = np.unique(report_day[keep])
    covers = (first[None, :] <= reports[:, None]) & (reports[:, None] <= last_day[None, :])
    # Snapshots are sorted ascending: the last covering one is the authority.
    authority = snaps[covers.shape[1] - 1 - np.argmax(covers[:, ::-1], axis=1)]
    kept = np.flatnonzero(keep)
    valid = kept[snap_day[kept] == authority[np.searchsorted(reports, report_day[kept])]]
    rows: pd.DataFrame = stored.iloc[valid]
    return rows.assign(
        report=pd.to_datetime(rows["ts"], utc=True).dt.date,
        snapshot=pd.to_datetime(rows["session_date"]).dt.date,
    )


def _column(frame: pd.DataFrame, name: str) -> list[object]:
    """A column's values, or nulls when the source does not provide it."""
    return frame[name].tolist() if name in frame.columns else [None] * len(frame)


@cache
def _sessions_to(start: date, end: date) -> int:
    return sessions_to(start, end)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[EVENTS]
    assert stored is not None  # required input
    rows = valid_events(stored)
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
