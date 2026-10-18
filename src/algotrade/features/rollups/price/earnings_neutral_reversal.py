"""``earnings_neutral_reversal@v1``: the last 20 sessions' return without the days an earnings
report moved the price (the short-term reversal signal cleaned of earnings, Chan 2003 and
Savor 2012).

Inputs: ``bars/1d`` split-adjusted AS OF the session, the session plus ``WINDOW`` earlier
sessions, and ``events/earnings`` read as ``earnings@v1`` reads it (``earnings.valid_events``,
every row known on or before the session: ``known_from <= S``). One row per operating company
traded on the session.

A report E excludes the daily returns of its reaction window, close(E-1) to close(E+1)
(``earnings_reaction``): the return into E and the return out of it. E-1 is the last session
before E and E+1 the first after it, so a report on a non-session day excludes the one return
across it, and a report on the session itself excludes the return into it (E+1 is not yet
there). A report outside the 20 returns excludes nothing.

    ret_ex_earnings_20d    the product of (1 + r) over the 20 daily close-to-close returns r
                           that are not excluded, minus 1; equal to ``price_stats.ret_20d`` when
                           no report fell in the window
    earnings_days_excluded the number of the 20 returns left out (0: none reported)

Null (UNKNOWN), never zero: a session among the last 21 has no close, or the history is
shorter, or the instrument has no earnings report known by the session at all (the calendar
cannot say it did not report). The window (20) is part of the definition: changing it is a new
version.
"""

from bisect import bisect_left, bisect_right
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.price.price_stats import Matrix, panel, traded_rows

NAME = "earnings_neutral_reversal"
VERSION = 1
BARS = "bars/1d"
WINDOW = 20  # daily returns, from WINDOW + 1 closes

_NULL = (
    f"a session among the last {WINDOW + 1} has no close (a gap), the history is shorter, or "
    "no earnings report is known for the instrument by the session"
)

FEATURES = (
    Feature(
        "ret_ex_earnings_20d", "float32", "decimal",
        f"Return over the last {WINDOW} sessions leaving out the daily returns of every "
        "earnings reaction window (the close before a report to the close after it): the "
        "month's move that earnings did not make",
        _NULL, valid_range=(-1, None), inputs=(f"{BARS}.close", f"{earnings.EVENTS}.ts"),
    ),
    Feature(
        "earnings_days_excluded", "int", "count",
        f"How many of the last {WINDOW} daily returns an earnings reaction window left out "
        "(0: no report in the window)",
        _NULL, valid_range=(0, WINDOW), inputs=(f"{earnings.EVENTS}.ts",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def excluded_positions(grid: list[date], reports: list[date]) -> set[int]:
    """The positions on the session grid (each the close of a session; position p's return is
    close[p] / close[p-1], so the first is 1) whose return a report's reaction window covers."""
    out: set[int] = set()
    for report in reports:
        if report > grid[-1]:
            continue  # not yet reported on the session
        before = bisect_left(grid, report) - 1
        after = bisect_right(grid, report)
        out.update(range(max(before + 1, 1), min(after, len(grid) - 1) + 1))
    return out


def neutral_return(closes: Matrix, column: int, skip: set[int]) -> tuple[float, int]:
    """One instrument's product of (1 + r) over the returns not in ``skip``, minus 1, and the
    number of returns in ``skip``; NaN for a gap or a non-positive close."""
    series: npt.NDArray[np.float64] = closes[:, column]
    if np.isnan(series).any() or (series <= 0).any():
        return np.nan, 0
    kept = [p for p in range(1, len(series)) if p not in skip]
    growth = float(np.prod([series[p] / series[p - 1] for p in kept])) if kept else 1.0
    return growth - 1.0, len(skip)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored, bars = inputs[earnings.EVENTS], inputs[BARS]
    assert stored is not None and bars is not None  # required inputs
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        stored = stored[pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date <= session]
    rows = earnings.valid_events(stored, session)
    reports = {str(i): list(g["report"]) for i, g in rows.groupby("instrument_id")}
    grid = sessions_ending(session, WINDOW + 1)
    px = panel(bars, grid)
    value = np.full(len(px.ids), np.nan)
    count = np.full(len(px.ids), np.nan)
    for column, iid in enumerate(px.ids):
        if str(iid) not in reports:
            continue
        skip = excluded_positions(grid, reports[str(iid)])
        value[column], count[column] = neutral_return(px.close, column, skip)
        if np.isnan(value[column]):
            count[column] = np.nan
    return traded_rows(px, {"ret_ex_earnings_20d": value, "earnings_days_excluded": count}, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The last 20 sessions' return without the days an earnings report moved the price",
    (Input(earnings.EVENTS), Input(BARS, lookback=WINDOW)),
    FEATURES,
    compute,
    applies_to="operating_company",
)
