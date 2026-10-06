"""Pure maths over ``macro/series`` rows for the market groups (ADR 0048): each observation as
the session knew it, and the windows the macro group reads (the latest value, a change over a
year or a number of sessions, trailing means, lows and counts).

The feature input ``macro/series`` hands a group each observation as the session knew it (the
latest vintage with ``vintage_date`` on or before the session, ``data.macro.series``'s rule: a
value revised after the session is never seen), dated within the input's lookback, plus each
series' latest. ``as_series`` turns those rows into one series per id. A null value (FRED's
".", a holiday) is no observation.

Every window is complete or null (UNKNOWN), never shorter: a window whose history does not
reach back to its start (within ``tolerance`` calendar days, for holidays and weekly dates)
gives null.
"""

from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd

type Series = pd.Series  # float values by observation date (a DatetimeIndex), ascending
# Sessions of observations a group reads (about 800 calendar days: a year back from a month
# that is itself months old); each series' latest observation comes whatever its age.
HISTORY_SESSIONS = 550
TOLERANCE_DAYS = 7  # a window's history must reach within this many days of its start


def as_series(rows: pd.DataFrame | None) -> dict[str, Series]:
    """``instrument_id`` -> its observations in ``rows`` (the input's known observations: one
    row per id and ``obs_date``), non-null values only; empty when there are none."""
    if rows is None or rows.empty:
        return {}
    known = rows[rows["value"].notna()]
    out: dict[str, Series] = {}
    for iid, part in known.groupby("instrument_id", sort=True):
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
