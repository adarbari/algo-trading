"""Pure maths over ``macro/series`` rows for the market groups (ADR 0048): each observation as
the session knew it, and the windows the macro group reads (the latest value, a change over a
year or a number of sessions, trailing means, lows and counts).

The feature input ``macro/series`` hands a group every vintage with ``vintage_date`` on or
before the session, sorted by ``vintage_date``. ``known_series`` keeps the latest of them per
(series, observation), which is ``data.macro.series.series_as_of``'s rule: a value revised
after the session is never seen. A null value (FRED's ".", a holiday) is no observation.

Every window is complete or null (UNKNOWN), never shorter: a window whose history does not
reach back to its start (within ``tolerance`` calendar days, for holidays and weekly dates)
gives null.
"""

from collections.abc import Mapping
from datetime import date, timedelta

import numpy as np
import pandas as pd

type Series = pd.Series  # float values by observation date (a DatetimeIndex), ascending
HISTORY_DAYS = 800  # observations older than this are never read (a year back from a stale month)
TOLERANCE_DAYS = 7  # a window's history must reach within this many days of its start


def known_series(
    rows: pd.DataFrame | None, session: date, history_days: int = HISTORY_DAYS
) -> dict[str, Series]:
    """``instrument_id`` -> its observations as ``session`` knew them (the latest vintage with
    ``vintage_date <= session`` per observation, non-null values only), dated within
    ``history_days`` of the session; empty when there are none."""
    if rows is None or rows.empty:
        return {}
    first = session - timedelta(days=history_days)
    seen = rows[(rows["vintage_date"] <= session) & (rows["obs_date"] >= first)]
    newest = seen.sort_values("vintage_date", kind="stable")
    newest = newest.drop_duplicates(["instrument_id", "obs_date"], keep="last")
    newest = newest[newest["value"].notna()]
    out: dict[str, Series] = {}
    for iid, part in newest.groupby("instrument_id", sort=True):
        index = pd.DatetimeIndex(pd.to_datetime(part["obs_date"]))
        out[str(iid)] = pd.Series(part["value"].to_numpy(float), index=index).sort_index()
    return out


def latest(series: Mapping[str, Series], iid: str) -> float:
    """The latest known value of ``iid`` (NaN: none)."""
    s = series.get(iid)
    return float(s.iloc[-1]) if s is not None and len(s) else np.nan


def value_near(s: Series, day: pd.Timestamp, tolerance: int = TOLERANCE_DAYS) -> float:
    """The value of the last observation on or before ``day``, if it is at most ``tolerance``
    days older (NaN otherwise)."""
    before = s[s.index <= day]
    if before.empty or (day - before.index[-1]).days > tolerance:
        return np.nan
    return float(before.iloc[-1])


def change_12m(series: Mapping[str, Series], iid: str, ratio: bool) -> float:
    """The latest value against the value a year before the latest observation: ``latest /
    then - 1`` (``ratio``, a year-over-year change) or ``latest - then`` (a difference)."""
    s = series.get(iid)
    if s is None or s.empty:
        return np.nan
    then = value_near(s, s.index[-1] - pd.DateOffset(years=1))
    if np.isnan(then) or (ratio and then == 0):
        return np.nan
    now = float(s.iloc[-1])
    return now / then - 1.0 if ratio else now - then


def since(s: Series | None, start: date) -> Series | None:
    """The observations dated after ``start``, if the history reaches back to it (an
    observation within ``TOLERANCE_DAYS`` on or before it); ``None`` otherwise."""
    if s is None or s.empty:
        return None
    day = pd.Timestamp(start)
    if np.isnan(value_near(s, day)):
        return None
    window = s[s.index > day]
    return window if len(window) else None


def last_months(s: Series | None, n: int) -> Series | None:
    """The last ``n`` monthly observations, when they are ``n`` consecutive months (``None``
    otherwise)."""
    if s is None or len(s) < n:
        return None
    window = s.iloc[-n:]
    index = pd.DatetimeIndex(window.index)
    months = index.year * 12 + index.month
    return window if int(months[-1] - months[0]) == n - 1 else None
