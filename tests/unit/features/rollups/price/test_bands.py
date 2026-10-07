"""``bands@v1``: the 20-close standard deviation and EMA with hand-computed values, the
bandwidth percentile against the year before, the band walk; gaps and short history are null;
point in time (a session's row computed on bars up to it equals the backfilled row)."""

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.price import bands as bd
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.unit.features.rollups.price.test_momentum import rows, truncated

F32 = 2e-7


def column(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=float)[:, None]


def test_band_edges_by_hand() -> None:
    close = column(list(np.arange(100.0, 120.0)))  # 100..119: sma 109.5, var 665 / 19 = 35
    sma, std, upper, lower = bd.band_edges(close)
    assert sma[-1, 0] == 109.5 and std[-1, 0] == pytest.approx(np.sqrt(35.0))
    assert upper[-1, 0] == pytest.approx(109.5 + 2 * np.sqrt(35.0))
    assert lower[-1, 0] == pytest.approx(109.5 - 2 * np.sqrt(35.0))
    assert np.isnan(sma[-2, 0])  # 19 closes: no band yet


def test_ema_seeds_with_the_first_twenty_then_smooths() -> None:
    flat = column([100.0] * 20)
    assert bd.ema(flat)[0] == 100.0
    assert bd.ema(column([*[100.0] * 20, 121.0]))[0] == pytest.approx(100 + 2 / 21 * 21)  # 102
    assert np.isnan(bd.ema(column([100.0] * 19))[0])
    gap = column([*[50.0] * 30, np.nan, *[100.0] * 20])  # the run after the gap: 20 bars
    assert bd.ema(gap)[0] == 100.0
    assert np.isnan(bd.ema(column([*[50.0] * 30, np.nan, *[100.0] * 19]))[0])


def test_width_percentile_ranks_the_session_against_the_year_before() -> None:
    n = bd.PCTILE_WINDOW + 1
    sma = np.full((n, 2), 100.0)
    std = np.c_[np.r_[np.arange(1.0, n), 100.5], np.r_[np.arange(1.0, n), 100.5]]
    std[: n - bd.MIN_PCTILE, 1] = np.nan  # 13 unknown earlier widths: 239 known, too few
    out = bd.width_percentile(sma, std)
    assert out[0] == pytest.approx(100 / 252)  # widths 1..100 are below 100.5
    assert np.isnan(out[1])
    std[: n - bd.MIN_PCTILE - 1, 1] = np.nan  # ... 240 known: enough, and 88 of them below
    std[n - bd.MIN_PCTILE - 1, 1] = 12.0
    assert bd.width_percentile(sma, std)[1] == pytest.approx(88 / 240)
    std[-1, 0] = np.nan
    assert np.isnan(bd.width_percentile(sma, std)[0])  # the session's own width unknown


def test_band_walk_is_signed_and_stops_at_an_unknown_session() -> None:
    upper = np.full((4, 5), 2.0)
    lower = np.full((4, 5), 0.0)
    close = np.array(
        [
            [1.0, -1.0, 5.0, 5.0, 5.0],
            [5.0, -1.0, 1.0, 5.0, 5.0],
            [5.0, 1.0, 5.0, 5.0, 5.0],
            [5.0, -1.0, 1.0, 5.0, 5.0],
        ]
    )
    upper[1, 3] = np.nan  # an unknown band inside the run
    upper[3, 4] = np.nan  # the session's band unknown
    out = bd.band_walk(close, upper, lower)
    assert out[:4].tolist() == [3.0, -1.0, 0.0, 2.0] and np.isnan(out[4])


def test_compute_from_stored_bars_and_nulls() -> None:
    writer, reader = store()
    c = series(bd.LOOKBACK + 1, seed=4)
    write_bars(
        writer,
        {"EQ:A": c, "EQ:SHORT": c[-19:], "EQ:GAP": c[-60:]},
        skip={"EQ:GAP": [bd.LOOKBACK - 10]},  # no bar 10 sessions before the end
    )
    out = rows(compute_one(reader, bd.GROUP, END).frame)
    a = out["EQ:A"]
    assert a["close_std_20"] == pytest.approx(np.std(c[-20:], ddof=1), rel=F32)
    ema = c[-150:-130].mean()
    for x in c[-130:]:
        ema += 2 / 21 * (x - ema)
    assert a["ema_20"] == pytest.approx(ema, rel=F32)
    widths = [np.std(c[i - 20 : i], ddof=1) / c[i - 20 : i].mean() for i in range(20, len(c) + 1)]
    assert a["bb_width_pctile_252d"] == pytest.approx(
        np.mean(np.array(widths[:-1]) < widths[-1]), abs=1e-6
    )
    assert a["band_walk"] in (-1, 0, 1) or abs(a["band_walk"]) > 1
    for name in bd.COLUMNS:
        assert pd.isna(out["EQ:SHORT"][name]) and pd.isna(out["EQ:GAP"][name]), name


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(300, seed=11), "EQ:B": series(290, seed=12, start=50.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (280, 299)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, bd.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), bd.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_registered_with_the_declared_lookback() -> None:
    assert GROUPS["bands@v1"].table == "rollups/instrument/bands@v1"
    assert bd.GROUP.inputs[0].sessions_back(None) == bd.LOOKBACK == 271
    assert len(sessions_ending(END, bd.LOOKBACK + 1)) == 272
