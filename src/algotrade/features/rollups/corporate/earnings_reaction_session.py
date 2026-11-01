"""``earnings_reaction_session@v1``: the session a report's price reaction happens on, from the
report time of day the calendar gave (F10; the fields the ``on_event:earnings_reaction_session``
schedule reads, ADR 0050, ADR 0053 amendment).

Input: ``events/earnings`` read as ``earnings@v1`` reads it (``earnings.valid_events``: the
calendar rows known by the session and their per-date authority; the 8-K results rows, whose
``intraday`` time is only known after the event, are left out). The newest report E dated on or
before the session (one per quarter: of reports less than 40 days apart the earliest, as
``earnings_reaction@v1`` counts them) gets the session its reaction lands on, by the ``time``
of the calendar row known by the session:

    pre_market     E's own session (the first session on or after E): the company reports
                   before the open, so that day's trading is the reaction
    after_hours    the first session after E: it reports after the close
    anything else  unknown, never guessed (a calendar that gave no time, or ``intraday``)

    reaction_session_status       OK; PENDING (the reaction session is after the session: an
                                  after-hours report made today); UNKNOWN_TIME (no usable time)
    reaction_report_time          ``pre_market`` / ``after_hours`` / ``unknown``, the time used
    reaction_session_date         the reaction session (null unless OK)
    sessions_since_reaction_session  exchange sessions from it up to the session (0: it is that
                                  day; null unless OK)

``earnings_reaction@v1``'s window (E-1 to E+1) and its ``on_event:earnings_reaction`` anchor E+1
are unchanged: this group is the opt-in anchor that is right for a pre-market report too. An
instrument with no report dated on or before the session has no row (UNKNOWN).
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import is_session, next_session, sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.earnings_reaction import SAME_QUARTER

NAME = "earnings_reaction_session"
VERSION = 1
OK, PENDING, UNKNOWN_TIME = "OK", "PENDING", "UNKNOWN_TIME"
PRE, AFTER, UNKNOWN = "pre_market", "after_hours", "unknown"

_REPORT = f"{earnings.EVENTS}.ts"
_TIME = f"{earnings.EVENTS}.time"
_NOT_OK = "the newest report's reaction session is not yet here (PENDING) or its time is unknown"

FEATURES = (
    Feature(
        "reaction_session_status", "str", "category",
        "OK: the newest report's reaction session is known and has come; PENDING: it is after "
        "the session (an after-hours report made today); UNKNOWN_TIME: the calendar gave no "
        "before-open or after-close time for the report",
        "never", "label", categories=(OK, PENDING, UNKNOWN_TIME), inputs=(_REPORT, _TIME),
    ),
    Feature(
        "reaction_report_time", "str", "category",
        "The time of day the newest report was made, as the calendar row known by the session "
        "gave it: pre_market (before the open), after_hours (after the close) or unknown",
        "never", "label", categories=(PRE, AFTER, UNKNOWN), inputs=(_TIME,),
    ),
    Feature(
        "reaction_session_date", "date", "date",
        "The session the newest report's price reaction happens on: the report's own session "
        "for a pre-market report, the next for an after-hours one",
        _NOT_OK, inputs=(_REPORT, _TIME),
    ),
    Feature(
        "sessions_since_reaction_session", "int", "sessions",
        "Exchange sessions from the newest report's reaction session up to the session (0: the "
        "session is that day)",
        _NOT_OK, valid_range=(0, None), inputs=(_REPORT, _TIME),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)

_TIMES = {"pre_market": PRE, "after_hours": AFTER}


def reaction_session(report: date, time: str) -> date | None:
    """The session ``report``'s reaction lands on given its calendar ``time`` (None: unknown)."""
    if time == PRE:
        return report if is_session(report) else next_session(report)
    if time == AFTER:
        return next_session(report)
    return None


def _newest_per_quarter(rows: pd.DataFrame) -> pd.DataFrame:
    """The newest counted report of each instrument, one report per quarter (the earliest of
    reports less than ``SAME_QUARTER`` apart, as ``earnings_reaction@v1`` keeps them)."""
    out = []
    for iid, group in rows.sort_values("report", kind="stable").groupby("instrument_id"):
        kept: pd.Series | None = None
        for _, row in group.iterrows():
            if kept is None or row["report"] - kept["report"] >= SAME_QUARTER:
                kept = row
        assert kept is not None
        out.append({"instrument_id": str(iid), "report": kept["report"], "time": kept["time"]})
    return pd.DataFrame(out, columns=["instrument_id", "report", "time"])


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[earnings.EVENTS]
    assert stored is not None  # required input
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        known = pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date
        stored = stored[known <= session]
    rows = earnings.valid_events(stored, session)
    if "time" not in rows.columns:
        rows = rows.assign(time=None)
    rows = rows[rows["report"] <= session]
    out = []
    for iid, report, time in _newest_per_quarter(rows).itertuples(index=False):
        said = _TIMES.get(str(time), UNKNOWN)
        reaction = reaction_session(report, said)
        if reaction is None:
            row: dict[str, object] = {"reaction_session_status": UNKNOWN_TIME}
        elif reaction > session:
            row = {"reaction_session_status": PENDING}
        else:
            row = {
                "reaction_session_status": OK,
                "reaction_session_date": reaction,
                "sessions_since_reaction_session": sessions_to(reaction, session),
            }
        out.append({"instrument_id": iid, "reaction_report_time": said, **row})
    frame = pd.DataFrame(out, columns=["instrument_id", *COLUMNS])
    frame["sessions_since_reaction_session"] = frame["sessions_since_reaction_session"].astype(
        "Int64"
    )
    return frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The session the newest earnings report's price reaction lands on, from the report's time "
    "of day (before the open or after the close)",
    (Input(earnings.EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
