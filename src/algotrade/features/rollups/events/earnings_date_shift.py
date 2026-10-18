"""``earnings_date_shift@v1``: the next report date, how far it moved from last year's, and when
that became known (the fields the ``on_event:earnings_date_shift`` schedule reads, ADR 0050,
ADR 0053 amendment, EB H4).

Input: every ``events/earnings`` row known on or before the session, read as ``earnings@v1``
reads it (``earnings.valid_events``: the calendar rows and their per-date authority; the 8-K
results rows are left out). For an instrument whose NEXT report date X (the first valid date on
or after the session) is a stored one:

    expected = the year-ago report (the valid report before the session whose distance to X is
               nearest 364 days, within 45) + 364 days: the same weekday a year earlier, the
               rule ``earnings_expected@v1`` falls back on
    earnings_date_shift_days     X - expected, in calendar days (positive: later than a year ago)
    earnings_shift_direction     ``later`` or ``earlier`` when the shift is at least
                                 ``MIN_SHIFT_DAYS`` calendar days either way; null below it
    earnings_shift_known_date    the session the date X was FIRST stored in a calendar known by
                                 the session (``known_from``, else the stored session: the
                                 earliest of the rows that carry X, so a date that moved is
                                 known from the session its new value first appeared)
    sessions_since_earnings_shift  exchange sessions from that session up to the session (0:
                                 the session it became known); null unless a direction

The history starts with the first stored calendar snapshot: a date first stored AT or before
that snapshot says nothing about when it became known (vendor backfills carry no time), so it
is never an event (the history begins the session after). Dates are the calendar's
SCHEDULED ones; the Nasdaq calendar does not confirm a date, so the "confirmed date" of the
literature is a scheduled one here. A name with no year-ago report, or with no next date, has
nulls; an instrument with no report row known by the session has no row (UNKNOWN).
"""

from datetime import date, timedelta
from typing import cast

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_date_shift"
VERSION = 1
YEAR = timedelta(days=364)  # 52 weeks: the same weekday a year earlier
TOLERANCE = 45  # calendar days: the year-ago report is this near 364 days before X, else none
MIN_SHIFT_DAYS = 7  # a shift smaller than a week is a calendar's noise, not an event
LATER, EARLIER = "later", "earlier"

_REPORT = f"{earnings.EVENTS}.ts"
_NONE = (
    "no report date on or after the session, or no report of a year ago to compare it with, "
    "known by the session"
)
_UNSHIFTED = f"{_NONE}, or the date is within {MIN_SHIFT_DAYS} days of last year's"

FEATURES = (
    Feature(
        "earnings_date_shift_days", "int", "days",
        "Calendar days the next report date lies after the year-ago report plus 364 days "
        "(negative: earlier than a year ago)",
        _NONE, inputs=(_REPORT,),
    ),
    Feature(
        "earnings_shift_direction", "str", "category",
        "later or earlier when the next report date moved a week or more from last year's",
        _UNSHIFTED, "label", categories=(LATER, EARLIER), inputs=(_REPORT,),
    ),
    Feature(
        "earnings_shift_known_date", "date", "date",
        "The session the next report date was first stored in a calendar known by the session",
        _UNSHIFTED, inputs=(_REPORT,),
    ),
    Feature(
        "sessions_since_earnings_shift", "int", "sessions",
        "Exchange sessions from the session the shifted date became known up to the session "
        "(0: it became known today)",
        _UNSHIFTED, valid_range=(0, None), inputs=(_REPORT,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _year_ago(past: list[date], date_x: date) -> date | None:
    """The report in ``past`` nearest 364 days before ``date_x`` (within ``TOLERANCE``)."""
    best = min(past, key=lambda d: abs((date_x - d).days - YEAR.days), default=None)
    ok = best is not None and abs((date_x - best).days - YEAR.days) <= TOLERANCE
    return best if ok else None


def _first_known(stored: pd.DataFrame, first_snapshot: date | None) -> dict[tuple[str, date], date]:
    """(instrument, report date) -> the earliest effective ``known_from`` of the rows carrying
    that date; a date known at or before ``first_snapshot`` is left out (module doc)."""
    stamp = pd.to_datetime(stored["session_date"])
    if earnings.KNOWN_FROM in stored.columns:
        stamp = pd.to_datetime(stored[earnings.KNOWN_FROM]).fillna(stamp)
    if earnings.CARRIED_FROM in stored.columns:  # a copy carried over a failed day: its origin's
        origin = pd.to_datetime(stored[earnings.CARRIED_FROM])
        stamp = pd.concat([stamp, origin], axis=1).min(axis=1)
    frame = pd.DataFrame(
        {
            "instrument_id": stored["instrument_id"].astype(str).to_numpy(),
            "report": earnings.report_days(stored).dt.date.to_numpy(),
            "known": stamp.dt.date.to_numpy(),
        }
    )
    first = frame.groupby(["instrument_id", "report"])["known"].min()
    if first_snapshot is not None:
        first = first[first > first_snapshot]
    out: dict[tuple[str, date], date] = {}
    for key, known in first.items():
        iid, report = cast(tuple[str, date], key)
        out[str(iid), report] = known
    return out


def _first_snapshot(stored: pd.DataFrame) -> date | None:
    """The earliest session a calendar snapshot (a forecast row: not known before the session
    that stored it) was stored in."""
    snap = pd.to_datetime(stored["session_date"])
    if earnings.KNOWN_FROM in stored.columns:
        known = pd.to_datetime(stored[earnings.KNOWN_FROM])
        snap = snap[known.isna() | (known >= snap)]
    return None if snap.empty else snap.min().date()


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs[earnings.EVENTS]
    assert stored is not None  # required input
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        known = pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date
        stored = stored[known.isna() | (known <= session)]
    if "source" in stored.columns:
        stored = stored[stored["source"] != earnings.SEC_8K_SOURCE]
    rows = earnings.valid_events(stored, session)
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str))
    first = _first_known(stored, _first_snapshot(stored))
    upcoming = rows[rows["report"] >= session].sort_values(["instrument_id", "report"])
    next_date = dict(
        zip(
            upcoming.drop_duplicates("instrument_id")["instrument_id"],
            upcoming.drop_duplicates("instrument_id")["report"],
            strict=True,
        )
    )
    past: dict[str, list[date]] = {}
    for iid, day in zip(rows["instrument_id"], rows["report"], strict=True):
        if day < session:
            past.setdefault(iid, []).append(day)
    out = []
    for iid in sorted(set(rows["instrument_id"])):
        x = next_date.get(iid)
        ago = _year_ago(past.get(iid, []), x) if x is not None else None
        shift = None if ago is None or x is None else (x - (ago + YEAR)).days
        direction = None
        if shift is not None and abs(shift) >= MIN_SHIFT_DAYS:
            direction = LATER if shift > 0 else EARLIER
        seen = first.get((iid, x)) if direction and x is not None else None
        if seen is None or seen > session:
            direction, seen = None, None
        out.append((iid, shift, direction, seen))
    frame = pd.DataFrame(
        out,
        columns=[
            "instrument_id", "earnings_date_shift_days", "earnings_shift_direction",
            "earnings_shift_known_date",
        ],
    )  # fmt: skip
    frame["earnings_date_shift_days"] = frame["earnings_date_shift_days"].astype("Int64")
    frame["sessions_since_earnings_shift"] = pd.array(
        [
            None if d is None else sessions_to(d, session)
            for d in frame["earnings_shift_known_date"]
        ],
        dtype="Int64",
    )
    return frame[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The next earnings date, its shift from a year ago and the session the shift became known",
    (Input(earnings.EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
