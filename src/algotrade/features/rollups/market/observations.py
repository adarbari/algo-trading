"""Pure maths over ``macro/series`` rows for the market groups (ADR 0048): each observation as
the session knew it, and the windows the macro group reads (the latest value, a change over a
year or a number of sessions, trailing means, lows and counts).

The feature input ``macro/series`` hands a group each observation as the session knew it (the
latest vintage with ``vintage_date`` on or before the session, ``data.macro.series``'s rule: a
value revised after the session is never seen), dated within the input's lookback, plus each
series' latest. ``as_series`` turns those rows into one series per id. A null value (FRED's
".", a holiday) is no observation.

Every window of days or sessions is complete or null (UNKNOWN), never shorter: a window whose
history does not reach back to its start (within ``tolerance`` calendar days, for holidays and
weekly dates) gives null. A monthly window is the observations dated in its calendar months and
tolerates gaps (a month never published, as October 2025's unemployment rate in the
government shutdown): ``trailing_mean`` needs a minimum of its months present, else null.

A daily level read as a price series (an index's closes, ``last_observations``) counts its
observations, not calendar sessions: the last ``n`` non-null values known by the session, and
nothing when the newest is more than ``max_age`` exchange sessions old (a stale series).
"""

from collections.abc import Mapping
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_to

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


type Months = dict[int, float]  # month number (year * 12 + month - 1) -> its observation


def by_month(s: Series | None) -> Months:
    """A monthly series' observations by month number (the last one of a month); empty when
    there are none."""
    if s is None or s.empty:
        return {}
    index = pd.DatetimeIndex(s.index)
    return dict(zip((index.year * 12 + index.month - 1).tolist(), s.to_numpy(float), strict=True))


def trailing_mean(months: Months, last: int, n: int, minimum: int) -> float:
    """The mean of the observations dated in the ``n`` calendar months ending with month
    ``last``, when at least ``minimum`` of them are present (NaN otherwise)."""
    present = [months[m] for m in range(last - n + 1, last + 1) if m in months]
    return float(np.mean(present)) if len(present) >= minimum else np.nan


def fresh(s: Series | None, session: date, max_age: int) -> bool:
    """Whether ``s`` has an observation and its newest is at most ``max_age`` exchange
    sessions before ``session`` (``core.time.calendar.sessions_to``: 1 is the previous
    session's close, what a series lagged one day knows)."""
    if s is None or s.empty:
        return False
    return sessions_to(pd.Timestamp(s.index[-1]).date(), session) <= max_age


def last_observations(
    s: Series | None, session: date, n: int, max_age: int
) -> npt.NDArray[np.float64] | None:
    """The last ``n`` observations of ``s`` (its non-null values: a FRED "." is no observation,
    skipped, never counted), oldest first, padded at the front with NaN to ``n`` when the
    series is shorter; ``None`` unless ``fresh(s, session, max_age)``."""
    known = None if s is None else s.dropna()
    if known is None or not fresh(known, session, max_age):
        return None
    values = known.to_numpy(float)[-n:]
    return np.concatenate([np.full(n - len(values), np.nan), values])
