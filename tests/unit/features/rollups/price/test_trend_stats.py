"""``trend_stats@v2``: the long returns and the 12-1 momentum by hand, the return z-score,
the signed close and SMA20 streaks and the tight-range count; gaps and short history are null;
point in time (a session's row computed on bars up to it equals the backfilled row)."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.price import trend_stats as ts
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.unit.features.rollups.price.test_momentum import rows, truncated

F32 = 2e-7
P = ts.TrendStatsParams()


def test_returns_and_momentum_by_hand() -> None:
    n = ts.LOOKBACK + 1
    close = np.full(n, 100.0)
    close[-121], close[-253], close[-22], close[-1] = 80.0, 50.0, 60.0, 90.0
    close[-2], close[-4], close[-11] = 95.0, 85.0, 75.0
    close[-6] = 100.0  # five sessions earlier: ret_5d = -0.10; the five before: 100 / 75 - 1
    out = ts.returns(close[:, None])
    assert out["ret_1d"][0] == pytest.approx(90 / 95 - 1)
    assert out["ret_3d"][0] == pytest.approx(90 / 85 - 1)
    assert out["ret_10d"][0] == pytest.approx(90 / 75 - 1)
    assert out["ret_120d"][0] == pytest.approx(90 / 80 - 1)
    assert out["ret_252d"][0] == pytest.approx(90 / 50 - 1)
    assert out["mom_12_1"][0] == pytest.approx(60 / 50 - 1)
    assert out["mom_accel_5d"][0] == pytest.approx((90 / 100 - 1) - (100 / 75 - 1))
    close[-200] = np.nan  # a gap inside the year: the long return and the momentum are unknown
    out = ts.returns(close[:, None])
    assert np.isnan(out["ret_252d"][0]) and np.isnan(out["mom_12_1"][0])
    assert out["ret_120d"][0] == pytest.approx(90 / 80 - 1)


def test_return_z_score_by_hand() -> None:
    steps = np.array([0.01, -0.01] * 10)  # 20 returns alternating +1% / -1%
    close = 100 * np.cumprod(np.r_[1.0, 1 + steps, 1.03])  # then a +3% session
    z = ts.return_z(close[:, None])[0]
    assert z == pytest.approx(0.03 / np.std(steps, ddof=1))  # 2.92
    flat = 100 * np.cumprod(np.r_[1.0, [1.01] * 20, 1.03])  # every base return equal: null
    assert np.isnan(ts.return_z(flat[:, None])[0])
    assert np.isnan(ts.return_z(close[-21:, None])[0])  # 21 closes: one return short


def test_streaks_by_hand() -> None:
    writer, reader = store()
    n = 60
    up = np.linspace(100.0, 110.0, n)  # every close above the last, and above its mean
    down = up[::-1].copy()
    flat = np.full(n, 100.0)
    flat[-1] = 100.0  # unchanged on the session
    mean_cross = np.full(n, 100.0)
    mean_cross[-3:] = [103.0, 101.0, 102.0]  # above the 20-session mean for 3 sessions
    write_bars(writer, {"EQ:UP": up, "EQ:DOWN": down, "EQ:FLAT": flat, "EQ:CROSS": mean_cross})
    out = rows(compute_one(reader, ts.GROUP, END).frame)
    assert out["EQ:UP"]["close_streak"] == n - 1 and out["EQ:DOWN"]["close_streak"] == -(n - 1)
    assert out["EQ:FLAT"]["close_streak"] == 0 and out["EQ:FLAT"]["sma20_streak"] == 0
    assert out["EQ:UP"]["sma20_streak"] == n - 19  # from the first session with a mean
    assert out["EQ:DOWN"]["sma20_streak"] == -(n - 19)
    assert out["EQ:CROSS"]["sma20_streak"] == 3


def test_tight_range_counts_sessions_inside_the_threshold() -> None:
    writer, reader = store()
    n = 60
    close = np.full(n, 100.0)
    high, low = np.full(n, 101.0), np.full(n, 99.0)  # a 2% range: tight
    high[-30] = 130.0  # a spike 30 sessions ago: the 20-session range was wide until it left
    write_bars(
        writer, {"EQ:A": close}, opens={"EQ:A": close}, highs={"EQ:A": high}, lows={"EQ:A": low}
    )
    out = rows(compute_one(reader, ts.GROUP, END).frame)["EQ:A"]
    assert out["tight_range_sessions"] == 10  # the spike sits in the window for 20 sessions
    high[-1] = 120.0  # wide today
    write_bars(
        writer, {"EQ:A": close}, opens={"EQ:A": close}, highs={"EQ:A": high}, lows={"EQ:A": low}
    )
    assert rows(compute_one(reader, ts.GROUP, END).frame)["EQ:A"]["tight_range_sessions"] == 0


def test_channels_prior_levels_pullback_age_and_range_position() -> None:
    writer, reader = store()
    n = 260
    close = np.full(n, 100.0)
    high, low = np.full(n, 101.0), np.full(n, 99.0)
    high[-150], low[-150] = 130.0, 70.0  # inside the 200 window, outside the 100
    high[-80], low[-80] = 120.0, 80.0  # inside the 100 window
    high[-30], low[-30] = 115.0, 85.0  # inside the 50 windows, outside the 20
    high[-8], low[-8] = 110.0, 90.0  # inside the 20 window: the pullback started 7 sessions ago
    high[-1], low[-1], close[-1] = 104.0, 96.0, 102.0  # closed at 75% of today's range
    write_bars(
        writer, {"EQ:A": close}, opens={"EQ:A": close}, highs={"EQ:A": high}, lows={"EQ:A": low}
    )
    out = rows(compute_one(reader, ts.GROUP, END).frame)["EQ:A"]
    assert (out["high_200d"], out["low_200d"]) == (130.0, 70.0)
    assert (out["high_100d"], out["low_100d"]) == (120.0, 80.0)
    assert (out["prior_high_50d"], out["prior_low_50d"], out["prior_low_20d"]) == (
        115.0,
        85.0,
        90.0,
    )
    assert out["sessions_since_high_20d"] == 7
    assert out["close_range_pos"] == pytest.approx(0.75)
    high[-1] = 112.0  # today's high is the 20-session high: age 0
    write_bars(
        writer, {"EQ:A": close}, opens={"EQ:A": close}, highs={"EQ:A": high}, lows={"EQ:A": low}
    )
    out = rows(compute_one(reader, ts.GROUP, END).frame)["EQ:A"]
    assert out["sessions_since_high_20d"] == 0 and out["prior_high_50d"] == 115.0


def test_gaps_and_short_history_are_null() -> None:
    writer, reader = store()
    c = series(ts.LOOKBACK + 1, seed=3)
    write_bars(
        writer,
        {"EQ:A": c, "EQ:NEW": c[-15:], "EQ:GAP": c, "EQ:GAPYEST": c},
        skip={"EQ:GAP": [ts.LOOKBACK - 10], "EQ:GAPYEST": [ts.LOOKBACK - 1]},
    )
    out = rows(compute_one(reader, ts.GROUP, END).frame)
    assert not any(pd.isna(v) for v in out["EQ:A"].values())
    new = out["EQ:NEW"]
    assert pd.isna(new["ret_120d"]) and pd.isna(new["mom_12_1"]) and pd.isna(new["ret_z_20d"])
    assert pd.isna(new["sma20_streak"]) and pd.isna(new["tight_range_sessions"])
    assert not pd.isna(new["ret_10d"]) and not pd.isna(new["mom_accel_5d"])  # 15 bars: enough
    assert (
        pd.isna(new["high_100d"])
        and pd.isna(new["prior_low_20d"])
        and not pd.isna(new["close_range_pos"])
    )
    assert pd.isna(new["sessions_since_high_20d"])
    assert new["close_streak"] in (-14, *range(-13, 14), 14)  # 15 bars: a streak of at most 14
    gap = out["EQ:GAP"]
    assert pd.isna(gap["ret_252d"]) and pd.isna(gap["ret_z_20d"]) and pd.isna(gap["sma20_streak"])
    assert abs(gap["close_streak"]) <= 9
    yest = out["EQ:GAPYEST"]
    assert pd.isna(yest["close_streak"]) and pd.isna(yest["ret_z_20d"]) and pd.isna(yest["ret_1d"])
    assert not pd.isna(yest["close_range_pos"])


def test_params_are_validated() -> None:
    with pytest.raises(ValueError):
        ts.TrendStatsParams(tight_range_pct=1.5)


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(300, seed=21), "EQ:B": series(280, seed=22, start=40.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (270, 299)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, ts.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), ts.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_registered_with_params_and_lookback() -> None:
    assert GROUPS["trend_stats@v2"].table == "rollups/instrument/trend_stats@v2"
    assert ts.GROUP.inputs[0].sessions_back(None) == ts.LOOKBACK == 252


def test_regression_trend_quality_by_hand() -> None:
    n = ts.LOOKBACK + 1
    daily = 0.001  # a perfectly smooth exponential trend: r2 = 1, slope exactly annualised
    smooth = 100 * np.exp(daily * np.arange(n))
    r2, slope = ts.regression(smooth[:, None])
    assert r2[0] == pytest.approx(1.0) and slope[0] == pytest.approx(np.expm1(daily * 252))
    noisy = smooth * np.exp(np.random.default_rng(2).normal(0, 0.02, n))
    r2n, _ = ts.regression(noisy[:, None])
    assert 0 < r2n[0] < 1
    flat = np.full(n, 100.0)
    r2f, slope_f = ts.regression(flat[:, None])
    assert np.isnan(r2f[0]) and slope_f[0] == pytest.approx(0.0)
    gap = smooth.copy()
    gap[-10] = np.nan
    assert np.isnan(ts.regression(gap[:, None])[0][0])
