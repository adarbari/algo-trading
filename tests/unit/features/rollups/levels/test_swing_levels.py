"""``swing_levels@v1``: pivots by hand (5 bars each side, strict before, at-least after, a flat
top counted once), confirmation 5 sessions after the pivot and never earlier, the most recent
pivot beyond the close, gaps and missing levels null; point in time (a session's row computed
on bars up to it equals the backfilled row) and swing_high > close > swing_low."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.levels import swing_levels as sl
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, series, store, write_bars

BASE = 100.0


def bars(
    highs: list[float], lows: list[float] | None = None, close: float = BASE
) -> dict[str, list[float]]:
    """Bars with a flat close (open = close) and the given highs / lows."""
    n = len(highs)
    lows = lows if lows is not None else [close - 1.0] * n
    return {"close": [close] * n, "high": highs, "low": lows}


def write(writer: StoreWriter, data: dict[str, dict[str, list[float]]]) -> list[date]:
    closes = {i: d["close"] for i, d in data.items()}
    return write_bars(
        writer,
        closes,
        opens=closes,
        highs={i: d["high"] for i, d in data.items()},
        lows={i: d["low"] for i, d in data.items()},
    )


def levels(frame: pd.DataFrame | None) -> dict[str, dict[str, object]]:
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def peak(n: int, at: int, value: float, rest: float = 101.0) -> list[float]:
    highs = [rest] * n
    highs[at] = value
    return highs


def test_pivot_rule_by_hand() -> None:
    h = np.array([[101, 102, 103, 104, 105, 110, 105, 104, 103, 102, 101]], dtype=float).T
    assert sl.pivots(h, high=True)[:, 0].tolist() == [True]  # the docs' worked example
    flat_top = np.array([[100, 100, 100, 100, 100, 110, 110, 100, 100, 100, 100, 100]], float).T
    assert sl.pivots(flat_top, high=True)[:, 0].tolist() == [True, False]  # counted once
    higher_after = h.copy()
    higher_after[8] = 111  # a higher high within 5 bars after: not a pivot
    assert not sl.pivots(higher_after, high=True).any()
    missing = h.copy()
    missing[2] = np.nan  # a missing bar in the 11: unknown, never a pivot
    assert not sl.pivots(missing, high=True).any()
    lows = 200 - h
    assert sl.pivots(lows, high=False)[:, 0].tolist() == [True]


def test_a_pivot_is_known_only_five_sessions_later() -> None:
    writer, reader = store()
    n = 40
    days = write(writer, {"EQ:A": bars(peak(n, 30, 110.0))})
    results = {
        r.session: levels(r.frame)["EQ:A"] for r in compute_sessions(reader, sl.GROUP, days[30:])
    }
    for k in range(30, 35):  # bars 31..34 exist, bar 35 not yet: unconfirmed
        assert np.isnan(results[days[k]]["swing_high"]), k
    for k in range(35, n):
        assert results[days[k]]["swing_high"] == 110.0
        assert results[days[k]]["swing_high_date"] == days[30]


def test_pivots_can_be_dated_d_minus_246_to_d_minus_5() -> None:
    """The 252 sessions read are d - 251 .. d and a pivot needs 5 bars each side among them."""
    writer, reader = store()
    n = 300
    oldest, too_old = n - 1 - sl.FIRST_PIVOT, n - 2 - sl.FIRST_PIVOT
    days = write(
        writer,
        {"EQ:IN": bars(peak(n, oldest, 110.0)), "EQ:OUT": bars(peak(n, too_old, 110.0))},
    )
    out = levels(compute_one(reader, sl.GROUP, END).frame)
    assert sl.FIRST_PIVOT == 246
    assert out["EQ:IN"]["swing_high"] == 110.0 and out["EQ:IN"]["swing_high_date"] == days[oldest]
    assert np.isnan(out["EQ:OUT"]["swing_high"])  # d - 247: its 5th bar before is not read


def test_most_recent_pivot_beyond_the_close() -> None:
    writer, reader = store()
    n = 60
    highs = [101.0] * n
    highs[n - 31], highs[n - 11] = 110.0, 104.0  # 30 and 10 sessions before the end
    lows = [99.0] * n
    lows[n - 21], lows[n - 41] = 97.0, 90.0
    days = write(writer, {"EQ:A": bars(highs, lows, close=100.0)})
    out = levels(compute_one(reader, sl.GROUP, END).frame)["EQ:A"]
    assert out["swing_high"] == 104.0  # both are above the close: the recent one wins
    assert out["swing_high_date"] == days[n - 11]
    assert out["swing_low"] == 97.0 and out["swing_low_date"] == days[n - 21]


def test_skips_pivots_on_the_wrong_side_of_the_close() -> None:
    writer, reader = store()
    n = 60
    highs = [101.0] * n
    highs[n - 31], highs[n - 11] = 112.0, 104.0
    lows = [99.0] * n
    days = write(writer, {"EQ:A": bars(highs, lows, close=100.0)})
    # move the last close above the recent pivot (106): resistance becomes the older 112
    writer2, reader2 = store()
    closes = [100.0] * (n - 1) + [106.0]
    write(writer2, {"EQ:A": {"close": closes, "high": [*highs[:-1], 107.0], "low": lows}})
    assert levels(compute_one(reader, sl.GROUP, END).frame)["EQ:A"]["swing_high"] == 104.0
    out = levels(compute_one(reader2, sl.GROUP, END).frame)["EQ:A"]
    assert out["swing_high"] == 112.0 and out["swing_high_date"] == days[n - 31]


def test_no_level_short_history_and_gaps_are_null() -> None:
    writer, reader = store()
    n = 40
    rising = [100.0 + i for i in range(n)]
    gap = bars(peak(n, 20, 110.0))
    write_bars(  # a steady rise: the close is at its high, no pivot above, none below either
        writer,
        {"EQ:UP": rising, "EQ:NEW": [BASE] * 10, "EQ:GAP": gap["close"]},
        opens={"EQ:UP": rising, "EQ:NEW": [BASE] * 10, "EQ:GAP": gap["close"]},
        highs={
            "EQ:UP": [c + 0.5 for c in rising],
            "EQ:NEW": peak(10, 4, 110.0),
            "EQ:GAP": gap["high"],
        },
        lows={"EQ:UP": [c - 0.5 for c in rising], "EQ:NEW": [99.0] * 10, "EQ:GAP": gap["low"]},
        skip={"EQ:GAP": [23]},  # a missing bar 3 sessions after the peak
    )
    out = levels(compute_one(reader, sl.GROUP, END).frame)
    for iid in ("EQ:UP", "EQ:NEW", "EQ:GAP"):
        assert np.isnan(out[iid]["swing_high"]) and out[iid]["swing_high_date"] is None, iid
    assert np.isnan(out["EQ:UP"]["swing_low"])


def _truncated(full: dict[str, np.ndarray], days: list[date], k: int) -> StoreReader:
    writer, reader = store()
    write_bars(writer, {i: c[: k + 1] for i, c in full.items()}, end=days[k])
    return reader


def test_point_in_time_and_levels_bracket_the_close() -> None:
    full = {"EQ:A": series(300, seed=21), "EQ:B": series(300, seed=22, start=40.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (40, 150, 260, 299)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, sl.GROUP, picks)}
    for day in picks:
        alone = compute_one(_truncated(full, days, days.index(day)), sl.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])
        frame = backfilled[day]
        assert frame is not None
        close = {i: full[i][days.index(day)] for i in full}
        for _, row in frame.iterrows():
            c = close[row["instrument_id"]]
            assert np.isnan(row["swing_high"]) or row["swing_high"] > c
            assert np.isnan(row["swing_low"]) or row["swing_low"] < c
            for side in ("high", "low"):
                when = row[f"swing_{side}_date"]
                assert when is None or when <= days[days.index(day) - sl.PIVOT_WIDTH]
    assert sum(f["swing_high"].notna().sum() for f in backfilled.values() if f is not None) > 0


def test_registered_with_the_declared_lookback() -> None:
    assert GROUPS["swing_levels@v1"].table == "rollups/instrument/swing_levels@v1"
    assert sl.GROUP.inputs[0].sessions_back(None) == sl.WINDOW - 1
