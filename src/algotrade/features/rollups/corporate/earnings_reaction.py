"""``earnings_reaction@v2``: the last report's price move and the volume it drew, and the name's
past earnings moves (ED4b; F4 of the options-setups design).

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

    abs_move_mean_8           mean over the last eight reports (``MOVE_REPORTS``) with a closed
                              window of |close(E+1) / close(E-1) - 1|, the raw move (not the excess
                              over SPY: it is what an option straddle prices)
    abs_move_median_8         the median of the same moves
    abs_moves_counted         how many of those reports had both window bars (0 to 8)
    abs_move_mean_4           the mean absolute move of the newest four of them (the recent habit)
    abs_move_max_8            the largest absolute move among them
    signed_move_mean_8        the mean signed move (the direction the name has tended to take)
    up_moves_8                how many of them rose

The past moves read every report known by the session whose window has closed, whether or not a
newer report is still ahead: the name reporting tomorrow is the one an earnings setup compares
its implied move with. The history behind them is ``MOVES_LOOKBACK`` sessions (eight quarters and
the sessions around the oldest); a report older than that is not counted, so ``abs_moves_counted``
says how much history stands behind the mean.

One row per instrument traded on the session (dense), with ``reaction_status`` OK, NO_REPORT
(no report known by the session: a name with no event, not a missing row) or INCOMPLETE (a
report is known but its window is open or off the history, or a bar it needs is missing);
``sessions_since_reaction`` is null unless OK. A value is null (UNKNOWN), never zero, when a
session it needs (a window bar, SPY's bar, a bar of the 20 before) has no bar, SPY has none, or
the history reaches back less far than the report needs; the ratio is also null below four
counted reports. The windows (two sessions, 20, four reports, eight moves,
``MOVES_LOOKBACK``) are part of the definition: changing one is a new version. EV2's
``event_reaction@v1`` must read this group, not recompute the window.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
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
    symbol_column,
)

type Matrix = npt.NDArray[np.float64]

NAME = "earnings_reaction"
VERSION = 2
SYMBOLS = "instruments/symbol_ids"
OK, NO_REPORT, INCOMPLETE = "OK", "NO_REPORT", "INCOMPLETE"
REPORTS = 4  # the reports the volume ratio averages
SAME_QUARTER = timedelta(days=40)  # reports closer than this are one quarter's moved date
LOOKBACK = 330  # sessions back: four quarters of reports and the 20 sessions before the oldest
MOVE_REPORTS = 8  # the reports the past moves cover
RECENT_MOVES = 4  # the newest of them the recent mean covers
MOVES_LOOKBACK = (
    540  # sessions back: eight quarters (about 504 sessions) and the window around the oldest
)

_REPORT = f"{earnings.EVENTS}.ts"
_NONE = "no report known by the session has a closed reaction window (E+1 <= the session)"
_NO_MOVES = (
    "no report known by the session has a closed window with both bars (abs_moves_counted is 0)"
)
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
    Feature(
        "abs_move_mean_8", "float32", "decimal",
        "Mean absolute move (close before the report to close after it, E-1 to E+1, the raw "
        f"move, not the excess over SPY) of the last {MOVE_REPORTS} reports with a closed "
        "window; 0.05 is 5%",
        _NO_MOVES, valid_range=(0, None), inputs=(CLOSE, _REPORT),
    ),
    Feature(
        "abs_move_median_8", "float32", "decimal",
        f"Median absolute move (E-1 to E+1, raw) of the last {MOVE_REPORTS} reports with a closed "
        "window: the typical move, one outlier report does not shift it",
        _NO_MOVES, valid_range=(0, None), inputs=(CLOSE, _REPORT),
    ),
    Feature(
        "abs_moves_counted", "int", "count",
        f"How many of the last {MOVE_REPORTS} reports with a closed window had both bars of the "
        "window: the number of moves behind abs_move_mean_8 (0: none)",
        "never (0 when no report has a closed window on the history)",
        valid_range=(0, MOVE_REPORTS), inputs=(CLOSE, _REPORT),
    ),
    Feature(
        "abs_move_mean_4", "float32", "decimal",
        f"Mean absolute move (E-1 to E+1, raw) of the newest {RECENT_MOVES} of the reports "
        "behind abs_move_mean_8: the recent habit, against the two-year one",
        _NO_MOVES, valid_range=(0, None), inputs=(CLOSE, _REPORT),
    ),
    Feature(
        "abs_move_max_8", "float32", "decimal",
        f"Largest absolute move (E-1 to E+1, raw) of the last {MOVE_REPORTS} reports with a "
        "closed window: the worst surprise the name has had",
        _NO_MOVES, valid_range=(0, None), inputs=(CLOSE, _REPORT),
    ),
    Feature(
        "signed_move_mean_8", "float32", "decimal",
        f"Mean signed move (E-1 to E+1, raw, a fall is negative) of the last {MOVE_REPORTS} "
        "reports with a closed window: whether the name has tended to rise or fall on reports",
        _NO_MOVES, valid_range=(-1, None), inputs=(CLOSE, _REPORT),
    ),
    Feature(
        "up_moves_8", "int", "count",
        f"How many of the last {MOVE_REPORTS} reports with a closed window moved the price up "
        "(E+1 close above E-1 close); abs_moves_counted minus this is the falls and flat ones",
        "never (0 when no report has a closed window on the history)",
        valid_range=(0, MOVE_REPORTS), inputs=(CLOSE, _REPORT),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@cache
def _gap_sessions(start: date, end: date) -> int:
    return sessions_to(start, end)


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


def _share(numerator: float, denominator: float) -> float:
    """``numerator / denominator``, NaN (never an error or an infinity) when the denominator is
    zero, negative or missing: a name with no pre-event trading has no volume ratio."""
    if not np.isfinite(denominator) or denominator <= 0.0:
        return np.nan
    return numerator / denominator


def window_share(grid: list[date], dollar: Matrix, column: int, report: date) -> float:
    """``report``'s window mean dollar volume over its pre-event 20-session dollar volume (NaN:
    the window is off the grid, a bar is missing or the history is short)."""
    w = _window(grid, report)
    if w is None:
        return np.nan
    return _share(
        float(_mean(dollar[w[0] : w[1] + 1, [column]])[0]), _pre_adv(dollar, column, w[0])
    )


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
    move = _share(float(px[after, column]), float(px[before, column])) - 1.0
    market = np.nan if spy is None else _share(float(px[after, spy]), float(px[before, spy])) - 1.0
    excess = move - market
    ratios = [window_share(grid, dollar, column, report) for report in reports[:REPORTS]]
    ratio = float(np.mean(ratios)) if len(reports) >= REPORTS else np.nan
    return {
        "reaction_excess_return": excess,
        "reaction_end_date": grid[after],
        "sessions_since_reaction": _gap_sessions(grid[after], grid[-1]),
        "pre_event_adv_usd_20d": _pre_adv(dollar, column, before),
        "earnings_volume_ratio": ratio if np.isfinite(ratio) else np.nan,
    }


@dataclass(frozen=True)
class Reactions:
    """What a reaction read needs at one session: the ``grid`` of sessions, the close and dollar
    volume matrices (``px``, ``dollar``), each instrument's column, SPY's column (None: no
    SPY bar) and each counted instrument's reports, newest first."""

    grid: list[date]
    px: Matrix
    dollar: Matrix
    ids: npt.NDArray[np.str_]
    column_of: dict[str, int]
    spy: int | None
    by_report: dict[str, list[date]]
    all_reports: dict[str, list[date]]  # every report known by the session, newest first


def read_reactions(inputs: Inputs, session: date, lookback: int = LOOKBACK) -> Reactions:
    """The counted reports (known by the session, one per quarter, window on the grid) with the
    price and volume matrices around them: the one rule ``earnings_reaction@v2`` and the groups
    that read the same window (``earnings_gap_volume@v1``) share."""
    stored, bars = inputs[earnings.EVENTS], inputs[BARS]
    assert stored is not None and bars is not None  # required inputs
    if earnings.KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        known = pd.to_datetime(stored[earnings.KNOWN_FROM]).dt.date
        stored = stored[known <= session]
    rows = earnings.valid_events(stored, session)
    grid = sessions_ending(session, lookback + 1)
    px = panel(bars, grid)
    column_of = {iid: i for i, iid in enumerate(px.ids)}
    spy = symbol_column(inputs[SYMBOLS], px.ids)
    # the newest report (one per quarter) counts once its reaction window (E-1 .. E+1) is on
    # the grid: E+1 on or before the session, E-1 inside the lookback
    all_reports = {
        str(iid): _one_per_quarter(list(g["report"])) for iid, g in rows.groupby("instrument_id")
    }
    by_report = {i: r for i, r in all_reports.items() if _window(grid, r[0]) is not None}
    return Reactions(
        grid, px.close, px.close * px.volume, px.ids, column_of, spy, by_report, all_reports
    )


def past_moves(read: Reactions, iid: str) -> list[float]:
    """The signed E-1 to E+1 moves of ``iid``'s last ``MOVE_REPORTS`` reports with a closed
    window on the grid (newest first); a report whose window lacks a bar is not counted. A report
    with an open window (ahead of the session, or E+1 not yet closed) is skipped, not the name."""
    column = read.column_of.get(iid)
    if column is None:
        return []
    closed = [r for r in read.all_reports.get(iid, []) if _window(read.grid, r) is not None]
    moves = []
    for report in closed[:MOVE_REPORTS]:
        window = _window(read.grid, report)
        assert window is not None
        before, after = window
        move = _share(float(read.px[after, column]), float(read.px[before, column])) - 1.0
        if np.isfinite(move):
            moves.append(move)
    return moves


def window_ratio(read: Reactions, iid: str, report: date) -> float:
    """The window's mean dollar volume (E-1, E, E+1) over the pre-event 20-session dollar volume
    of ``report`` for ``iid``; NaN when a bar is missing or the history is short."""
    return window_share(read.grid, read.dollar, read.column_of[iid], report)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    read = read_reactions(inputs, session, MOVES_LOOKBACK)
    grid, px, dollar, spy = read.grid, read.px, read.dollar, read.spy
    column_of, by_report = read.column_of, read.by_report
    out = []
    for traded in read.ids[~np.isnan(px[-1])]:  # every instrument traded on the session
        iid = str(traded)
        signed = past_moves(read, iid)
        moves = [abs(m) for m in signed]
        past = {
            "abs_move_mean_8": float(np.mean(moves)) if moves else np.nan,
            "abs_move_median_8": float(np.median(moves)) if moves else np.nan,
            "abs_moves_counted": len(moves),
            "abs_move_mean_4": float(np.mean(moves[:RECENT_MOVES])) if moves else np.nan,
            "abs_move_max_8": float(np.max(moves)) if moves else np.nan,
            "signed_move_mean_8": float(np.mean(signed)) if signed else np.nan,
            "up_moves_8": sum(m > 0 for m in signed),
        }
        if iid in by_report:
            values = _row(by_report[iid], grid, column_of[iid], px, dollar, spy)
            if pd.notna(values["reaction_excess_return"]):  # the ADV may be null: a filter's call
                out.append({"instrument_id": iid, "reaction_status": OK, **values, **past})
                continue
            values = {**values, "sessions_since_reaction": pd.NA}
            out.append({"instrument_id": iid, "reaction_status": INCOMPLETE, **values, **past})
        else:  # no report with a closed window on the grid (none, future only, or too old)
            out.append({"instrument_id": iid, "reaction_status": NO_REPORT, **past})
    frame = pd.DataFrame(out, columns=["instrument_id", *COLUMNS])
    frame["sessions_since_reaction"] = frame["sessions_since_reaction"].astype("Int64")
    for count in ("abs_moves_counted", "up_moves_8"):
        frame[count] = frame[count].astype("int64")
    return frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How the last earnings report moved the price against SPY and the volume it drew, and how far "
    "the name moved on its last eight reports",
    (
        Input(earnings.EVENTS),
        Input(BARS, lookback=MOVES_LOOKBACK),
        Input(SYMBOLS, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
