"""``dividend_months@v1``: whether the coming calendar month is one the name pays an ex-dividend
date in, from its own history as known on the session (Hartzmark and Solomon's expected
dividend month).

Inputs: ``events/dividend`` by EVENT date up to the session (the ex-dates: a declared future
ex-date never shows, so nothing after the session is read) and ``price_stats@v2`` for the
session (``history_days``). One row per instrument with a ``price_stats@v2`` row, as
``dividends@v2``.

The coming month is the calendar month after the session's month. An ex-date counts when it
falls in that month of one of the ``YEARS`` years before (the same month a year, two and three
years earlier: all on or before the session). Distributions typed ``special`` are left out (a
one-off predicts nothing), as in ``dividends@v2``.

    div_month_hits_3y        how many of the last 3 years had an ex-date in the coming month
                             (0 to 3)
    expected_div_month_flag  div_month_hits_3y >= 1: the name has paid an ex-dividend date in
                             that month before, so one is expected

Like ``dividends@v2``'s zero, a count of 0 is known only for a name with at least
``MIN_HISTORY_DAYS`` bars among the last 252 sessions (``price_stats@v2.history_days``): a
payer needs no more, a name too new, or one whose bars the corporate-actions history may not
cover, is null (UNKNOWN), never "not expected". The history reaches back at most 3 years: a
young payer's hits count the years it has. The windows (the month, 3 years, ``LOOKBACK``) are
part of the definition: changing one is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate.dividends import DIVIDENDS, PRICE_STATS

NAME = "dividend_months"
VERSION = 1
YEARS = 3
MIN_HISTORY_DAYS = 240  # bars among the last 252 sessions for a zero to be known
LOOKBACK = 800  # sessions of ex-dates loaded: more than 3 years and the month ahead of it

_UNKNOWN = (
    "no ex-dividend date in the coming month of the last 3 years and fewer than 240 bars "
    "among the last 252 sessions (too new, or bars do not cover the history, to call it "
    "not expected)"
)

FEATURES = (
    Feature(
        "div_month_hits_3y", "int", "count",
        "How many of the last 3 years had an ex-dividend date in the calendar month after the "
        "session's month (0 to 3; specials excluded)",
        _UNKNOWN, valid_range=(0, YEARS), inputs=("events/dividend.ts",),
    ),
    Feature(
        "expected_div_month_flag", "bool", "flag",
        "The calendar month after the session's month is one the name has paid an ex-dividend "
        "date in during the last 3 years: a dividend is expected in it",
        _UNKNOWN, inputs=("events/dividend.ts",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def coming_month(session: date) -> tuple[int, int]:
    """(year, month) of the calendar month after the session's."""
    return (session.year + 1, 1) if session.month == 12 else (session.year, session.month + 1)


def hits(dividends: pd.DataFrame | None, session: date) -> pd.Series:
    """Per instrument with an ex-date in the coming month of the last ``YEARS`` years: how many
    of those years had one."""
    if dividends is None or dividends.empty:
        return pd.Series(dtype="int64")
    rows = dividends[dividends["event_date"] <= session]
    if "distribution_type" in rows.columns:
        rows = rows[rows["distribution_type"].astype(str) != "special"]
    year, month = coming_month(session)
    days = pd.to_datetime(rows["event_date"])
    wanted = days.dt.month == month
    back = year - days.dt.year
    kept = rows[wanted & (back >= 1) & (back <= YEARS)]
    years = pd.to_datetime(kept["event_date"]).dt.year
    return years.groupby(kept["instrument_id"].astype(str)).nunique().astype("int64")


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id", "history_days"]]
    today = today.astype({"instrument_id": str})
    found = hits(inputs.get(DIVIDENDS), session)
    count = today["instrument_id"].map(found)
    known = today["history_days"].fillna(0).to_numpy() >= MIN_HISTORY_DAYS
    paid = count.notna().to_numpy()
    value = np.where(paid, count.fillna(0), np.where(known, 0, np.nan))
    out = pd.DataFrame({"instrument_id": today["instrument_id"].to_numpy()})
    out["div_month_hits_3y"] = value
    out["expected_div_month_flag"] = pd.Series(value > 0).where(~np.isnan(value), None).to_numpy()
    return out[["instrument_id", *COLUMNS]].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Whether the coming calendar month is one the name pays an ex-dividend date in, from its "
    "last 3 years",
    (Input(PRICE_STATS), Input(DIVIDENDS, lookback=LOOKBACK, required=False)),
    FEATURES,
    compute,
)
