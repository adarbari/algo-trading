"""The event study's pure maths (ADR 0050 decision 1, docs/event-sensitivity-plan.md 4.1): the
reaction session of an event, a name's move on it in normal days, the big-move flags and the
class an event day belongs to. No store read; the groups call it with the bars matrix they read.

    reaction session   a release at or before 16:00 ET and a rule day (an expiry, a quarter end)
                       react on their own session; a release after 16:00 on the next; a day the
                       exchange is closed on, the next session. An earnings report: ``pre`` its
                       own session, ``post`` the next, an unknown time is left out (never guessed)
    move               the reaction session's close-to-close log return
    normal day         the sample standard deviation of the 20 log returns ending at the close
                       before the reaction session (``hv20 / sqrt(252)``: the same formula as
                       ``price_stats.hv20``, taken as the session before each past event)
    multiple           |move| over the normal day
    big move           beyond 5% (simple return) or beyond 2 normal days; both flags are kept

A statistic as of session S counts only events whose reaction session is on or before S (the grid
ends at S) and whose normal day and bars are complete: a gap is null, never zero. The macro
release keys are listed here because a rollup reads no config; a fitness test checks the list
against ``config/site/events/releases.toml``.
"""

import warnings
from bisect import bisect_left
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import (
    is_session,
    last_session_of_month,
    monthly_expiry,
    next_session,
)

type Matrix = npt.NDArray[np.float64]

# The scheduled releases a column is kept for; FOMC_UNSCHEDULED is a calendared day (it explains
# a move) but has no column of its own.
MACRO_KEYS = (
    "CPI",
    "EMPLOYMENT",
    "PCE",
    "GDP",
    "PPI",
    "RETAIL_SALES",
    "ISM_MFG",
    "ISM_SERVICES",
    "FOMC",
)
EXPLAINING_KEYS = (*MACRO_KEYS, "FOMC_UNSCHEDULED")
EXPIRY, QUARTER_END = "monthly_expiry", "quarter_end"
STRUCTURE = (EXPIRY, QUARTER_END)
NORMAL_WINDOW = 20  # returns of the normal day
MIN_SESSIONS = 250  # bars an instrument needs before any statistic is non-null (plan 4.2)
BIG_PCT = 0.05  # a big move: beyond 5 % ...
BIG_MULTIPLE = 2.0  # ... or beyond 2 normal days
TOP_MOVES = 20  # the largest moves the "what moves it" shares cover
YEAR = 252  # sessions of the big-move counts
CLOSE_ET = "16:00"  # a release at or before it reacts on its own session

# classes in the order that decides which one a day is counted under
EARNINGS, MACRO, STRUCTURE_CLASS, UNSCHEDULED = "earnings", "macro", "structure", "unscheduled"


def log_returns(close: Matrix) -> Matrix:
    """Close-to-close log returns of a (sessions x names) matrix; row 0 and any session whose
    close or previous close is missing or not positive are NaN."""
    out = np.full(close.shape, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = close[1:] / close[:-1]
    ok = np.isfinite(ratio) & (ratio > 0)
    out[1:][ok] = np.log(ratio[ok])
    return out


def multiples(returns: Matrix) -> Matrix:
    """|return| over the normal day as of the session before, per cell: NaN while fewer than
    ``NORMAL_WINDOW`` complete returns precede it, or the normal day is zero."""
    normal = (
        pd.DataFrame(returns).rolling(NORMAL_WINDOW, min_periods=NORMAL_WINDOW).std().to_numpy()
    )
    before = np.full(returns.shape, np.nan)
    before[1:] = normal[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.abs(returns) / before
    out[~np.isfinite(out)] = np.nan
    return np.asarray(out, dtype=np.float64)


def normal_day(returns: Matrix) -> Matrix:
    """The normal day of the last row: the standard deviation of the final ``NORMAL_WINDOW``
    returns of each column (NaN when one of them is missing)."""
    window = returns[-NORMAL_WINDOW:]
    out = pd.DataFrame(window).std().to_numpy(dtype=np.float64, copy=True)
    out[np.isnan(window).any(axis=0)] = np.nan
    return out


def big(returns: Matrix, mult: Matrix) -> npt.NDArray[np.bool_]:
    """Cells that are a big move: beyond 5 % or beyond 2 normal days (False where unknown)."""
    with np.errstate(invalid="ignore"):
        return (np.abs(np.expm1(returns)) > BIG_PCT) | (mult > BIG_MULTIPLE)


def release_days(releases: pd.DataFrame | None, session: date) -> list[tuple[str, date, str]]:
    """``(key, release date, time_et)`` of each release known by ``session``: per (key, date)
    the latest version known (by ``known_from``, then the stored session), a ``moved`` one
    dropped (its new date is another row), ascending by date."""
    if releases is None or releases.empty:
        return []
    rows = releases[pd.to_datetime(releases["known_from"]).dt.date <= session]
    rows = rows[rows["release_key"].isin(EXPLAINING_KEYS)]
    if rows.empty:
        return []
    rows = rows.sort_values(["known_from", "session_date"], kind="stable")
    latest = rows.drop_duplicates(["release_key", "release_date"], keep="last")
    live = latest[latest["status"] != "moved"]
    days = pd.to_datetime(live["release_date"]).dt.date
    return sorted(
        zip(live["release_key"].astype(str), days, live["time_et"].astype(str), strict=True),
        key=lambda r: (r[1], r[0]),
    )


def calendar_cover(grid: list[date], releases: list[tuple[str, date, str]]) -> int | None:
    """The first position on ``grid`` the release calendar covers: its earliest known release
    (the calendar is stored from a start date, so earlier sessions are unknown, not event-free);
    None when no release is known."""
    if not releases:
        return None
    return bisect_left(grid, min(day for _, day, _ in releases))


def reaction_session(day: date, time_et: str | None = CLOSE_ET) -> date:
    """The session an event on ``day`` reacts on, with no grid (the maths of ``reaction_position``
    for a date ahead of the session): a release after the close, or on a day the exchange is
    closed, reacts on the next session."""
    if is_session(day) and (time_et is None or time_et <= CLOSE_ET):
        return day
    return next_session(day)


def reaction_position(grid: list[date], day: date, time_et: str | None = CLOSE_ET) -> int | None:
    """The position on ``grid`` (sessions ending at S, oldest first) of the session an event on
    ``day`` reacts on, or None when it is not on the grid (before the first session, after S, or
    with no session before it to take the previous close from)."""
    pos = bisect_left(grid, day)
    if pos < len(grid) and grid[pos] == day and time_et is not None and time_et > CLOSE_ET:
        pos += 1  # after the close: the next session
    if pos >= len(grid) or pos < 1 or day < grid[0]:
        return None
    return pos


def macro_positions(
    grid: list[date], releases: list[tuple[str, date, str]]
) -> dict[str, list[int]]:
    """Reaction positions on ``grid`` of each release key (``EXPLAINING_KEYS``)."""
    out: dict[str, list[int]] = {k: [] for k in EXPLAINING_KEYS}
    for key, day, time_et in releases:
        pos = reaction_position(grid, day, time_et)
        if pos is not None:
            out[key].append(pos)
    return out


def structure_positions(grid: list[date]) -> dict[str, list[int]]:
    """Positions on ``grid`` of the rule days: each month's monthly option expiry (the third
    Friday, the session before when closed) and each quarter's last session."""
    first, last = grid[0], grid[-1]
    months = [
        (m // 12, m % 12 + 1)
        for m in range(first.year * 12 + first.month - 1, last.year * 12 + last.month)
    ]
    days: dict[str, list[date]] = {EXPIRY: [], QUARTER_END: []}
    for year, month in months:
        days[EXPIRY].append(monthly_expiry(year, month))
        if month % 3 == 0:
            days[QUARTER_END].append(last_session_of_month(year, month))
    found = {cls: [reaction_position(grid, d) for d in ds] for cls, ds in days.items()}
    return {cls: [p for p in ps if p is not None] for cls, ps in found.items()}


def nullable_ints(frame: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    """``frame`` with each ``int`` column (by the group's ``column_types``) as a nullable Int64."""
    for name, dtype in columns.items():
        if dtype == "int":
            frame[name] = frame[name].astype("Int64")
    return frame


def class_stats(
    mult: Matrix, returns: Matrix, positions: list[int]
) -> tuple[npt.NDArray[np.int64], Matrix, Matrix]:
    """Per column, over the events at ``positions``: how many have a multiple, their median
    multiple and the worst (lowest) simple return when one fell (NaN: none counted, or none fell:
    UNKNOWN, never zero)."""
    width = mult.shape[1]
    if not positions:
        return np.zeros(width, dtype=np.int64), np.full(width, np.nan), np.full(width, np.nan)
    m = mult[positions]
    known = np.isfinite(m)
    simple = np.where(known, np.expm1(returns[positions]), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN column is NaN, not an error
        median, worst = np.nanmedian(m, axis=0), np.nanmin(simple, axis=0)
    worst[~(worst < 0)] = np.nan
    return known.sum(axis=0), median, worst
