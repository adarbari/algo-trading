"""``momentum@v1``: Wilder ATR and RSI with hand-computed values, the fixed warm-up, the
return, relative volume and channels by hand; gaps and short history are null (never a shorter
window or zero); split-adjusted as of each session; point in time (a session's row computed on
bars up to it equals the backfilled row, and later bars never change it)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.price import momentum as mo
from algotrade.features.rollups.price.price_stats import Panel
from tests.helpers.rollup_store import END, series, store, write_bars, write_split

F32 = 2e-7


def rows(frame: pd.DataFrame | None) -> dict[str, dict[str, float]]:
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def one_panel(close: list[float], high: list[float], low: list[float]) -> Panel:
    col = lambda v: np.asarray(v, dtype=float)[:, None]  # noqa: E731
    vol = np.ones((len(close), 1))
    return Panel(np.array(["EQ:A"]), col(close), col(high), col(low), col(close), vol)


def reference_wilder(values: list[float], period: int = 14) -> float:
    """Wilder's average written out the long way (seed mean, then the recursion)."""
    avg = sum(values[:period]) / period
    for x in values[period:]:
        avg = (avg * (period - 1) + x) / period
    return avg


def test_atr_by_hand() -> None:
    # 15 bars with a true range of 1.00 (close 100, high 100.5, low 99.5), so 14 TRs of 1.00
    close, high, low = [100.0] * 15, [100.5] * 15, [99.5] * 15
    shock = one_panel([*close, 100.0], [*high, 107.5], [*low, 92.5])  # TR 15.00
    assert mo.wilder_atr_rsi(shock)[0][0] == pytest.approx((13 * 1 + 15) / 14)  # 2.00
    gap_up = one_panel([*close, 104.5], [*high, 105.0], [*low, 104.0])  # TR |105 - 100| = 5
    assert mo.wilder_atr_rsi(gap_up)[0][0] == pytest.approx((13 + 5) / 14)
    seed_only = one_panel(close, high, low)  # exactly 14 TRs: the seed mean
    assert mo.wilder_atr_rsi(seed_only)[0][0] == pytest.approx(1.0)
    short = one_panel(close[:14], high[:14], low[:14])  # 13 TRs: unknown
    assert np.isnan(mo.wilder_atr_rsi(short)[0][0])


def test_rsi_by_hand() -> None:
    changes = [2.0, -1.0] * 7  # 14 changes: average gain 1.0, average loss 0.5
    close = list(np.cumsum([100.0, *changes]))
    rsi = lambda c: mo.wilder_atr_rsi(one_panel(c, c, c))[1][0]  # noqa: E731
    assert rsi(close) == pytest.approx(100 - 100 / (1 + 2))  # 66.67
    after = [*close, close[-1] + 3]  # gain (13 + 3) / 14, loss 6.5 / 14
    assert rsi(after) == pytest.approx(100 - 100 / (1 + 16 / 6.5))  # 71.11
    assert rsi(list(np.arange(100.0, 116.0))) == 100.0  # no loss
    assert rsi(list(np.arange(116.0, 100.0, -1))) == pytest.approx(0.0)  # no gain
    assert np.isnan(rsi([100.0] * 16))  # never moved: 0/0 is unknown, not 50


def test_long_history_uses_the_last_150_sessions_and_matches_a_reference() -> None:
    writer, reader = store()
    c = series(400, seed=4)
    write_bars(writer, {"EQ:A": c})
    out = rows(compute_one(reader, mo.GROUP, END).frame)["EQ:A"]
    last = c[-mo.WARMUP :]  # write_bars: open = previous close, high / low 1% around
    hi = np.maximum(np.r_[c[-mo.WARMUP - 1], last[:-1]], last) * 1.01
    lo = np.minimum(np.r_[c[-mo.WARMUP - 1], last[:-1]], last) * 0.99
    prev = last[:-1]
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(abs(hi[1:] - prev), abs(lo[1:] - prev)))
    assert out["atr_14"] == pytest.approx(reference_wilder(list(tr)), rel=F32)
    diff = np.diff(last)
    gain = reference_wilder(list(np.clip(diff, 0, None)))
    loss = reference_wilder(list(np.clip(-diff, 0, None)))
    assert out["rsi_14"] == pytest.approx(100 - 100 / (1 + gain / loss), rel=1e-6)
    # the warm-up is long enough: the full 400-bar recursion differs by less than 0.01%
    full_prev = c[:-1]
    full_hi = np.maximum(full_prev, c[1:]) * 1.01
    full_lo = np.minimum(full_prev, c[1:]) * 0.99
    full_tr = np.maximum(
        full_hi - full_lo, np.maximum(abs(full_hi - full_prev), abs(full_lo - full_prev))
    )
    assert out["atr_14"] == pytest.approx(reference_wilder(list(full_tr)), rel=1e-4)


def test_return_relative_volume_and_channels_by_hand() -> None:
    writer, reader = store()
    n = 60
    close = np.full(n, 100.0)
    close[-6], close[-1] = 100.0, 103.0  # ret_5d = 0.03
    high, low = close + 1.0, close - 1.0
    high[-30], low[-45] = 120.0, 80.0  # inside the 50-session channel, outside the 20
    high[-10], low[-15] = 110.0, 95.0  # inside the 20-session channel
    high[-1] = 115.0  # today's high: in high_20d, not in prior_high_20d
    volume = np.full(n, 1_000_000.0)
    volume[-1] = 1_800_000.0
    write_bars(
        writer,
        {"EQ:A": close},
        opens={"EQ:A": close},
        volume={"EQ:A": volume},
        highs={"EQ:A": high},
        lows={"EQ:A": low},
    )
    out = rows(compute_one(reader, mo.GROUP, END).frame)["EQ:A"]
    assert out["ret_5d"] == pytest.approx(0.03, rel=F32)
    assert out["rel_volume"] == pytest.approx(1.8, rel=F32)
    assert out["high_20d"] == 115.0 and out["prior_high_20d"] == 110.0
    assert out["low_20d"] == 95.0
    assert out["high_50d"] == 120.0 and out["low_50d"] == 80.0


def test_gaps_short_history_and_zero_volume_are_null_not_zero() -> None:
    writer, reader = store()
    write_bars(
        writer,
        {
            "EQ:NEW": series(14, seed=2),  # 13 true ranges
            "EQ:GAP10": series(80, seed=3),
            "EQ:GAP30": series(80, seed=5),
            "EQ:QUIET": series(40, seed=6),
            "EQ:IDLE": series(40, seed=7),
        },
        skip={"EQ:GAP10": [69], "EQ:GAP30": [49]},  # no bar 10 / 30 sessions before the end
        volume={"EQ:QUIET": [0.0] * 39 + [500.0], "EQ:IDLE": [1000.0] * 39 + [0.0]},
    )
    out = rows(compute_one(reader, mo.GROUP, END).frame)
    assert all(np.isnan(out["EQ:NEW"][c]) for c in ("atr_14", "rsi_14", "high_20d"))
    assert not np.isnan(out["EQ:NEW"]["ret_5d"])  # 6 bars are enough for the return
    gap10, gap30 = out["EQ:GAP10"], out["EQ:GAP30"]
    assert np.isnan(gap10["atr_14"]) and np.isnan(gap10["high_20d"])  # run of 10 bars
    assert np.isnan(gap10["rel_volume"]) and not np.isnan(gap10["ret_5d"])
    assert gap30["atr_14"] > 0 and gap30["high_20d"] > 0  # run of 30 bars: enough
    assert np.isnan(gap30["high_50d"]) and np.isnan(gap30["low_50d"])
    assert np.isnan(out["EQ:QUIET"]["rel_volume"])  # no volume in the 20 sessions before
    assert out["EQ:IDLE"]["rel_volume"] == 0.0  # no trades today: known, zero


def test_split_adjusted_as_of_each_session() -> None:
    writer, reader = store()
    c = series(60, seed=8)
    raw = c.copy()
    raw[-5:] /= 2  # 2-for-1 split 5 sessions before the end
    volume = np.full(60, 1000.0)
    raw_volume = volume.copy()
    raw_volume[-5:] *= 2
    days = write_bars(  # open = close: no bar straddles the split
        writer,
        {"EQ:P": c, "EQ:S": raw},
        volume={"EQ:P": volume, "EQ:S": raw_volume},
        opens={"EQ:P": c, "EQ:S": raw},
    )
    write_split(writer, "EQ:S", days[-5], 2.0, stored=END)
    for result in compute_sessions(reader, mo.GROUP, days[-8:]):
        out = rows(result.frame)
        for column in ("atr_14", "rsi_14", "ret_5d", "rel_volume"):
            scale = 0.5 if column == "atr_14" and result.session >= days[-5] else 1.0
            assert out["EQ:S"][column] == pytest.approx(out["EQ:P"][column] * scale, rel=1e-5)


def truncated(full: dict[str, np.ndarray], days: list[date], k: int) -> StoreReader:
    """A store holding only the bars up to ``days[k]``."""
    writer, reader = store()
    offsets = {i: len(days) - len(c) for i, c in full.items()}  # a shorter series starts later
    kept = {i: c[: k + 1 - offsets[i]] for i, c in full.items() if k >= offsets[i]}
    write_bars(writer, kept, end=days[k])
    return reader


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(200, seed=11), "EQ:B": series(120, seed=12, start=50.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (99, 140, 170, 199)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, mo.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), mo.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_registered_with_the_declared_lookback() -> None:
    assert GROUPS["momentum@v1"].table == "rollups/instrument/momentum@v1"
    assert mo.GROUP.inputs[0].sessions_back(None) == mo.WARMUP - 1
    assert len(sessions_ending(END, mo.WARMUP)) == mo.WARMUP
