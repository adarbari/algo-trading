"""``earnings_neutral_reversal@v1``: the 20-session return without the E-1..E+1 returns, by
hand; a report on a non-session day, on the session, outside the window, unknown names."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.price import earnings_neutral_reversal as enr
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 2)
GRID = sessions_ending(SESSION, enr.WINDOW + 1)


def _events(rows: list[tuple[str, date, date]]) -> pd.DataFrame:
    frame = [
        {"instrument_id": i, "ts": pd.Timestamp(d, tz="UTC"), "time": "unknown",
         "known_from": k, "reported": True}
        for i, d, k in rows
    ]  # fmt: skip
    return stamped(frame, SESSION, "e")


def _bars(closes: dict[str, list[float]]) -> pd.DataFrame:
    rows = [
        {"instrument_id": iid, "session_date": day, "open": c, "high": c, "low": c,
         "close": c, "volume": 1.0}
        for iid, series in closes.items()
        for day, c in zip(GRID, series, strict=True)
    ]  # fmt: skip
    return pd.DataFrame(rows)


def _flat_with(jumps: dict[int, float]) -> list[float]:
    """100.0 everywhere, multiplied from position p on by 1 + jump."""
    out, level = [], 100.0
    for p in range(len(GRID)):
        level *= 1 + jumps.get(p, 0.0)
        out.append(level)
    return out


def _compute(events: pd.DataFrame, closes: dict[str, list[float]]) -> pd.DataFrame:
    out = enr.compute({earnings.EVENTS: events, "bars/1d": _bars(closes)}, SESSION, None)
    return out.set_index("instrument_id")


def test_the_reaction_window_returns_are_left_out() -> None:
    e = GRID[10]  # a session: the returns into E (10) and out of it (11) are excluded
    closes = _flat_with({10: 0.20, 11: 0.10, 15: 0.05})
    out = _compute(_events([("EQ:A", e, e)]), {"EQ:A": closes})
    assert abs(out.loc["EQ:A", "ret_ex_earnings_20d"] - 0.05) < 1e-6  # only the 5% day stays
    assert out.loc["EQ:A", "earnings_days_excluded"] == 2


def test_a_report_on_a_non_session_day_excludes_the_one_return_across_it() -> None:
    saturday = next(
        GRID[p] + timedelta(days=1) for p in range(5, 15) if (GRID[p + 1] - GRID[p]).days > 1
    )
    closes = _flat_with({})
    pos = GRID.index(next(d for d in GRID if d > saturday))
    closes = _flat_with({pos: 0.30, pos + 1: 0.02})
    out = _compute(_events([("EQ:A", saturday, saturday)]), {"EQ:A": closes})
    assert abs(out.loc["EQ:A", "ret_ex_earnings_20d"] - 0.02) < 1e-6
    assert out.loc["EQ:A", "earnings_days_excluded"] == 1


def test_a_report_on_the_session_excludes_the_return_into_it() -> None:
    closes = _flat_with({20: 0.25, 19: 0.01})
    out = _compute(_events([("EQ:A", SESSION, SESSION)]), {"EQ:A": closes})
    assert abs(out.loc["EQ:A", "ret_ex_earnings_20d"] - 0.01) < 1e-6
    assert out.loc["EQ:A", "earnings_days_excluded"] == 1  # E+1 is not there yet


def test_a_report_outside_the_window_leaves_the_plain_return() -> None:
    old = GRID[0] - timedelta(days=10)
    closes = _flat_with({3: 0.10})
    out = _compute(_events([("EQ:A", old, old)]), {"EQ:A": closes})
    assert abs(out.loc["EQ:A", "ret_ex_earnings_20d"] - 0.10) < 1e-6
    assert out.loc["EQ:A", "earnings_days_excluded"] == 0


def test_a_report_not_known_by_the_session_excludes_nothing() -> None:
    e = GRID[10]
    closes = _flat_with({10: 0.20})
    out = _compute(
        _events([("EQ:A", e, SESSION + timedelta(days=1)), ("EQ:A", GRID[0], GRID[0])]),
        {"EQ:A": closes},
    )
    assert abs(out.loc["EQ:A", "ret_ex_earnings_20d"] - 0.20) < 1e-6  # not known: the 20% stays


def test_unknown_with_no_report_or_a_gap() -> None:
    gap = _flat_with({})
    gap[5] = np.nan
    events = _events([("EQ:A", GRID[10], GRID[10]), ("EQ:GAP", GRID[10], GRID[10])])
    out = _compute(events, {"EQ:A": _flat_with({}), "EQ:NONE": _flat_with({}), "EQ:GAP": gap})
    assert out.loc["EQ:A", "ret_ex_earnings_20d"] == 0
    assert np.isnan(out.loc["EQ:NONE", "ret_ex_earnings_20d"])  # no report known: unknown
    assert np.isnan(out.loc["EQ:GAP", "ret_ex_earnings_20d"])
    assert np.isnan(out.loc["EQ:GAP", "earnings_days_excluded"])
