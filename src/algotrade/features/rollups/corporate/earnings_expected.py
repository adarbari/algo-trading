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
before the session (its anniversary is the next one due) and only when that anniversary is on
or after the session. Every row read is one ``earnings@v1`` reads (``earnings.valid_events``:
its 8-K / calendar handling and per-date authority) and is known by the session
(``known_from <= session``), so a report stored later, or a date nobody knew yet, never
makes a session SCHEDULED and the actual future dates are never read. One row per
instrument with a report row known by the session; an instrument with none has no row
(UNKNOWN).
"""

from datetime import date, timedelta
from functools import cache

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings

NAME = "earnings_expected"
VERSION = 1
SCHEDULED, PRIOR_YEAR, UNKNOWN = "SCHEDULED", "PRIOR_YEAR", "UNKNOWN"
YEAR = timedelta(days=364)  # 52 weeks: the anniversary falls on the same weekday

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
    within_year = rows[(rows["report"] < session) & (rows["report"] >= session - YEAR)]
    anchor = within_year.drop_duplicates(
        "instrument_id", keep="first"
    )  # earliest: soonest anniversary
    scheduled = dict(zip(upcoming["instrument_id"], upcoming["report"], strict=True))
    prior = {i: d + YEAR for i, d in zip(anchor["instrument_id"], anchor["report"], strict=True)}
    out = []
    for iid in sorted(set(rows["instrument_id"])):
        if iid in scheduled:
            out.append((iid, scheduled[iid], SCHEDULED))
        elif iid in prior and prior[iid] >= session:
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
