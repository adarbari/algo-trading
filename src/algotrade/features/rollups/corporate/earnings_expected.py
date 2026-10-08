"""``earnings_expected@v1``: the report date a session can expect, and how it knows (ED4e).

``earnings@v1`` is null before a report date is announced, which on the history is almost
always (the Nasdaq calendar stores each report from its own day). Sessions in an edge's
evaluation window need an expectation that uses only what the session knew, so this group
states one, with the basis:

    expected_report_date       SCHEDULED: the first report date on or after the session in a
                               row known by it; PRIOR_YEAR: the year-ago report of the
                               instrument plus 364 days (52 weeks, the same weekday; the
                               Frazzini-Lamont timing rule); null when UNKNOWN
    expected_basis             SCHEDULED, PRIOR_YEAR or UNKNOWN: UNKNOWN is "no basis for a
                               date", never "no earnings"
    sessions_to_expected_report  sessions after the session up to the expected date (0:
                               today; ``core.time.calendar``); null when UNKNOWN

PRIOR_YEAR is used only when no row is SCHEDULED, from the earliest report in the 364 days
before the session whose quarter is not yet reported (a later report within 45 days of its
anniversary means it is), rolled to the next session when the anniversary is a holiday, and
only when that date is on or after the session and within 100 days (further out a quarter's
row is missing or the company reports yearly: UNKNOWN).

Known caveat until ``earnings`` v2: the 8-K results rows are not read (``earnings@v1`` reads
the calendar rows only), so a report the calendar lacks is not seen.

Every row read is one ``earnings@v1`` reads (``earnings.valid_events``: its per-date
authority) and is known by the session
(``known_from <= session``), so a report stored later, or a date nobody knew yet, never
makes a session SCHEDULED and the actual future dates are never read. One row per
instrument with a report row known by the session; an instrument with none has no row
(UNKNOWN).
"""

from datetime import date, timedelta
from functools import cache

import pandas as pd

from algotrade.core.time.calendar import is_session, next_session, sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_expected"
VERSION = 1
SCHEDULED, PRIOR_YEAR, UNKNOWN = "SCHEDULED", "PRIOR_YEAR", "UNKNOWN"
YEAR = timedelta(days=364)  # 52 weeks: the anniversary falls on the same weekday
EARLY = timedelta(days=45)  # a report this much before the anniversary is the same quarter's
MAX_AHEAD = 100  # calendar days: further out, a quarter's row is missing (or it reports yearly)

_REPORT = f"{earnings.EVENTS}.ts"
_UNKNOWN = (
    "UNKNOWN: no report date on or after the session is known, and no report in the "
    "364 days before it"
)

FEATURES = (
    Feature(
        "expected_report_date", "date", "date",
        "The report date the session can expect: the next known one (SCHEDULED) or the "
        "year-ago report plus 364 days (PRIOR_YEAR)",
        _UNKNOWN, inputs=(_REPORT,),
    ),
    Feature(
        "expected_basis", "str", "category",
        "How the date is known: SCHEDULED (a report date known by the session), PRIOR_YEAR "
        "(the year-ago report plus 364 days), UNKNOWN (neither: not 'no earnings')",
        "never", "label", categories=(SCHEDULED, PRIOR_YEAR, UNKNOWN), inputs=(_REPORT,),
    ),
    Feature(
        "sessions_to_expected_report", "int", "sessions",
        "Exchange sessions after the session up to the expected report date (0: today)",
        _UNKNOWN, valid_range=(0, None), inputs=(_REPORT,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@cache
def _sessions_to(start: date, end: date) -> int:
    return sessions_to(start, end)


def _prior_year(past: list[date], session: date) -> date | None:
    """The next anniversary of a report in the 364 days before ``session`` (``past``: the
    report dates before it, ascending), rolled to a session; None when there is none, or it
    is more than ``MAX_AHEAD`` days out. A quarter already reported this year (the latest
    report is within ``EARLY`` days of the anchor's anniversary or later) is skipped for the
    next anchor, so an early report is not expected again."""
    latest = past[-1]
    for anchor in (d for d in past if d >= session - YEAR):
        anniversary = anchor + YEAR
        if latest >= anniversary - EARLY:
            continue  # this quarter's report is out
        expected = anniversary if is_session(anniversary) else next_session(anniversary)
        return expected if (expected - session).days <= MAX_AHEAD else None
    return None


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored = inputs[earnings.EVENTS]
    assert stored is not None  # required input
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        known = pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date
        stored = stored[known <= session]
    rows = earnings.valid_events(stored, session)
    rows = rows.sort_values(["instrument_id", "report"], kind="stable")
    rows = rows.assign(instrument_id=rows["instrument_id"].astype(str))
    upcoming = rows[rows["report"] >= session].drop_duplicates("instrument_id", keep="first")
    past: dict[str, list[date]] = {}
    for iid, day in zip(rows["instrument_id"], rows["report"], strict=True):
        if day < session:
            past.setdefault(iid, []).append(day)  # ascending: rows are sorted
    scheduled = dict(zip(upcoming["instrument_id"], upcoming["report"], strict=True))
    prior = {i: d for i, days in past.items() if (d := _prior_year(days, session)) is not None}
    out = []
    for iid in sorted(set(rows["instrument_id"])):
        if iid in scheduled:
            out.append((iid, scheduled[iid], SCHEDULED))
        elif iid in prior:
            out.append((iid, prior[iid], PRIOR_YEAR))
        else:
            out.append((iid, None, UNKNOWN))
    frame = pd.DataFrame(out, columns=["instrument_id", "expected_report_date", "expected_basis"])
    frame["sessions_to_expected_report"] = pd.array(
        [None if d is None else _sessions_to(session, d) for d in frame["expected_report_date"]],
        dtype="Int64",
    )
    return frame


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The earnings date a session can expect: the next known date, else last year's plus 364 days",
    (Input(earnings.EVENTS),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
