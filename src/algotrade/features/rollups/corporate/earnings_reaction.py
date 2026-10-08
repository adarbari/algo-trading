"""``earnings_reaction@v1``: the last report's price move and the volume it drew (ED4b).

Input: ``bars/1d`` split-adjusted as of the session, ``LOOKBACK`` sessions back (the reaction
window of the last four reports and the 20 sessions of pre-event volume before the oldest);
``instruments/symbol_ids`` (SPY's id, a lookup only: never built); ``events/earnings`` read as
``earnings@v1`` reads it (``earnings.valid_events``: the calendar rows and their per-date
authority; the 8-K results rows wait for earnings v2's precedence, so a report only an 8-K
dated is missed until then).

A report E counts at session S only when it was known (``known_from <= S``) AND its reaction
window has closed (``E+1 <= S``). The window is the two sessions around the report, from the
close of the last session before E (E-1) to the close of the first session after it (E+1): it
holds the move whether the company reports before the open or after the close (the
Bernard-Thomas / Kothari window of the post-earnings-drift literature). E-1 and E+1 are
exchange sessions (``core.time.calendar``), whether or not E itself is.

    reaction_excess_return    close(E+1) / close(E-1) - 1 minus SPY's return over the same
                              sessions, for the most recent counted report
    reaction_end_date         E+1, that report's last window session (the anchor of a drift)
    sessions_since_reaction   exchange sessions from E+1 up to the session (0: it is E+1)
    pre_event_adv_usd_20d     mean close x volume over the 20 sessions ending at E-1 (before
                              the event's own volume), for that report
    earnings_volume_ratio     the mean over the last four counted reports of the window's mean
                              dollar volume (E-1, E, E+1 sessions) divided by that report's
                              pre-event 20-session dollar volume

One row per instrument traded on the session (dense), with ``reaction_status`` OK, NO_REPORT
(no report known by the session: a name with no event, not a missing row) or INCOMPLETE (a
report is known but its window is open or off the history, or a bar it needs is missing);
``sessions_since_reaction`` is null unless OK. A value is null (UNKNOWN), never zero, when a
session it needs (a window bar, SPY's bar, a bar of the 20 before) has no bar, SPY has none, or
the history reaches back less far than the report needs; the ratio is also null below four
counted reports. The windows (two sessions, 20, four reports,
``LOOKBACK``) are part of the definition: changing one is a new version. EV2's
``event_reaction@v1`` must read this group, not recompute the window.
"""

from bisect import bisect_left, bisect_right
from datetime import date, timedelta
from functools import cache
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending, sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.price.price_stats import (
    ADV_WINDOW,
    BARS,
    CLOSE,
    VOLUME,
    _mean,
    panel,
)

type Matrix = npt.NDArray[np.float64]

NAME = "earnings_reaction"
VERSION = 1
SYMBOLS = "instruments/symbol_ids"
MARKET_SYMBOL = "SPY"
OK, NO_REPORT, INCOMPLETE = "OK", "NO_REPORT", "INCOMPLETE"
REPORTS = 4  # the reports the volume ratio averages
SAME_QUARTER = timedelta(days=40)  # reports closer than this are one quarter's moved date
LOOKBACK = 330  # sessions back: four quarters of reports and the 20 sessions before the oldest

_REPORT = f"{earnings.EVENTS}.ts"
_NONE = "no report known by the session has a closed reaction window (E+1 <= the session)"
_BAR = "a bar of the window (or of SPY, for the return) is missing, or the history is too short"

FEATURES = (
    Feature(
        "reaction_status", "str", "category",
        "OK: the last report's window closed with its bars; NO_REPORT: no report known by the "
        "session; INCOMPLETE: the last report's window lacks a stock or SPY bar (the "
        "other columns may be null)",
        "never", "label", categories=(OK, NO_REPORT, INCOMPLETE), inputs=(_REPORT,),
    ),
    Feature(
        "reaction_excess_return", "float32", "decimal",
        "Return of the close before the last report to the close after it (E-1 to E+1), "
        "minus SPY's over the same sessions",
        f"{_NONE}, or {_BAR}", valid_range=(-2, None), inputs=(CLOSE, _REPORT, f"{SYMBOLS}.symbol"),
    ),
    Feature(
        "reaction_end_date", "date", "date",
        "The last session of the last report's reaction window (the first after the report)",
        _NONE, inputs=(_REPORT,),
    ),
    Feature(
        "sessions_since_reaction", "int", "sessions",
        "Exchange sessions from the end of the last report's reaction window up to the "
        "session (0: the session is that day)",
        _NONE, valid_range=(0, None), inputs=(_REPORT,),
    ),
    Feature(
        "pre_event_adv_usd_20d", "float32", "usd",
        f"Mean close x volume over the {ADV_WINDOW} sessions ending before the last report "
        "(the volume of the event itself excluded)",
        f"{_NONE}, or a session among those {ADV_WINDOW} has no bar, or the history is shorter",
        valid_range=(0, None), inputs=(CLOSE, VOLUME, _REPORT),
    ),
    Feature(
        "earnings_volume_ratio", "float32", "ratio",
        f"Mean over the last {REPORTS} reports of the reaction window's mean dollar volume "
        "divided by that report's pre-event 20-session dollar volume",
        f"fewer than {REPORTS} reports with a closed window known by the session, or a bar "
        "of any of them is missing, or the history is shorter",
        valid_range=(0, None), inputs=(CLOSE, VOLUME, _REPORT),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@cache
def _gap_sessions(start: date, end: date) -> int:
    return sessions_to(start, end)


def _spy_column(symbols: pd.DataFrame | None, ids: npt.NDArray[np.str_]) -> int | None:
    """SPY's column in the bars panel, or ``None`` (no reference, or SPY has no bars)."""
    if symbols is None:
        return None
    found = symbols.loc[symbols["symbol"] == MARKET_SYMBOL, "instrument_id"]
    if found.empty:
        return None
    where = np.flatnonzero(ids == str(found.iloc[0]))
    return int(where[0]) if len(where) else None


def _window(grid: list[date], report: date) -> tuple[int, int] | None:
    """(E-1, E+1) as positions on the session grid: the last session before the report and
    the first after it; ``None`` when E+1 is not on the grid yet (the window is open) or E-1
    is before it."""
    after = bisect_right(grid, report)
    before = bisect_left(grid, report) - 1
    if after >= len(grid) or before < 0:
        return None
    return before, after


def _pre_adv(dollar: Matrix, column: int, before: int) -> float:
    """Mean dollar volume of the ``ADV_WINDOW`` sessions ending at ``before`` (NaN: a gap or a
    history too short)."""
    if before + 1 < ADV_WINDOW:
        return np.nan
    return float(_mean(dollar[before + 1 - ADV_WINDOW : before + 1, [column]])[0])


def _one_per_quarter(reports: list[date]) -> list[date]:
    """Newest first, keeping the earliest of reports less than ``SAME_QUARTER`` apart (the
    calendar listed one quarter twice: a moved date)."""
    kept: list[date] = []
    for day in sorted(reports):
        if not kept or day - kept[-1] >= SAME_QUARTER:
            kept.append(day)
    return kept[::-1]


def _row(
    reports: list[date], grid: list[date], column: int, px: Matrix, dollar: Matrix, spy: int | None
) -> dict[str, Any]:
    """The columns of one instrument from its counted reports, newest first."""
    last = _window(grid, reports[0])
    assert last is not None  # counted reports have a closed window on the grid
    before, after = last
    with np.errstate(invalid="ignore", divide="ignore"):
        excess = (px[after, column] / px[before, column] - 1.0) - (
            np.nan if spy is None else px[after, spy] / px[before, spy] - 1.0
        )
    ratios = []
    for report in reports[:REPORTS]:
        w = _window(grid, report)
        if w is None:
            ratios.append(np.nan)
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            ratios.append(
                float(_mean(dollar[w[0] : w[1] + 1, [column]])[0]) / _pre_adv(dollar, column, w[0])
            )
    ratio = float(np.mean(ratios)) if len(reports) >= REPORTS else np.nan
    return {
        "reaction_excess_return": excess,
        "reaction_end_date": grid[after],
        "sessions_since_reaction": _gap_sessions(grid[after], grid[-1]),
        "pre_event_adv_usd_20d": _pre_adv(dollar, column, before),
        "earnings_volume_ratio": ratio if np.isfinite(ratio) else np.nan,
    }


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stored, bars = inputs[earnings.EVENTS], inputs[BARS]
    assert stored is not None and bars is not None  # required inputs
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        known = pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date
        stored = stored[known <= session]
    rows = earnings.valid_events(stored, session)
    grid = sessions_ending(session, LOOKBACK + 1)
    px = panel(bars, grid)
    column_of = {iid: i for i, iid in enumerate(px.ids)}
    spy = _spy_column(inputs[SYMBOLS], px.ids)
    dollar = px.close * px.volume
    # the newest report (one per quarter) counts once its reaction window (E-1 .. E+1) is on
    # the grid: E+1 on or before the session, E-1 inside the lookback
    by_report = {
        str(iid): _one_per_quarter(list(g["report"])) for iid, g in rows.groupby("instrument_id")
    }
    by_report = {i: r for i, r in by_report.items() if _window(grid, r[0]) is not None}
    out = []
    for traded in px.ids[~np.isnan(px.close[-1])]:  # every instrument traded on the session
        iid = str(traded)
        if iid in by_report:
            values = _row(by_report[iid], grid, column_of[iid], px.close, dollar, spy)
            if pd.notna(values["reaction_excess_return"]):  # the ADV may be null: a filter's call
                out.append({"instrument_id": iid, "reaction_status": OK, **values})
                continue
            values = {**values, "sessions_since_reaction": pd.NA}
            out.append({"instrument_id": iid, "reaction_status": INCOMPLETE, **values})
        else:  # no report with a closed window on the grid (none, future only, or too old)
            out.append({"instrument_id": iid, "reaction_status": NO_REPORT})
    frame = pd.DataFrame(out, columns=["instrument_id", *COLUMNS])
    frame["sessions_since_reaction"] = frame["sessions_since_reaction"].astype("Int64")
    return frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How the last earnings report moved the price against SPY, and the volume it drew",
    (
        Input(earnings.EVENTS),
        Input(BARS, lookback=LOOKBACK),
        Input(SYMBOLS, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
