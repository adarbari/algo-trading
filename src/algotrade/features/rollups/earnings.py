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

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import Input, Inputs, Rollup

NAME = "earnings"
VERSION = 1
EVENTS = "events/earnings"
TIMES = {"pre_market": "pre", "after_hours": "post"}

COLUMNS: dict[str, str] = {
    "next_earnings_date": "date",
    "earnings_time": "str",
    "days_to_earnings": "int",
    "date_confirmed": "bool",
    "last_earnings_date": "date",
}


def valid_events(stored: pd.DataFrame) -> pd.DataFrame:
    """The rows of the authoritative snapshot for each report date (see the module doc)."""
    rows = stored.assign(
        report=pd.to_datetime(stored["ts"], utc=True).dt.date,
        snapshot=pd.to_datetime(stored["session_date"]).dt.date,
    )
    ranges = rows.groupby("snapshot")["report"].agg(["min", "max"])
    snaps = ranges.index.to_numpy()
    # A snapshot covers from its own session (the calendar it fetched starts there) or its
    # earliest row (a backfill of past dates), to its latest row.
    ranges["min"] = np.minimum(ranges["min"].to_numpy(), snaps)
    reports = np.array(sorted(rows["report"].unique()))
    covers = (ranges["min"].to_numpy()[None, :] <= reports[:, None]) & (
        reports[:, None] <= ranges["max"].to_numpy()[None, :]
    )
    # Snapshots are sorted ascending: the last covering one is the authority.
    last = covers.shape[1] - 1 - np.argmax(covers[:, ::-1], axis=1)
    authority = dict(zip(reports, snaps[last], strict=True))
    return rows[rows["snapshot"] == rows["report"].map(authority)]


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


ROLLUP = Rollup(
    NAME,
    VERSION,
    "Next and last earnings dates, report time and sessions to the next report",
    (Input(EVENTS),),
    COLUMNS,
    compute,
)
