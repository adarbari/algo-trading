"""``volume_profile@v1``: the histogram spreads each bar's volume over the bins it covers,
the point of control and value area by hand, the nearest high- and low-volume nodes on each
side of the close, the share of volume near the close, the statuses, params, point in time."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.activity import volume_profile as vp
from algotrade.features.rollups.price.price_stats import Panel
from tests.helpers.rollup_store import END, series, store, write_bars, write_rows
from tests.unit.features.rollups.price.test_momentum import rows, truncated

P = vp.VolumeProfileParams(bins=10, min_bars=1)


def one(highs: list[float], lows: list[float], volumes: list[float], close: float) -> Panel:
    col = lambda v: np.asarray(v, dtype=float)[:, None]  # noqa: E731
    closes = [close] * len(highs)
    return Panel(np.array(["EQ:A"]), col(closes), col(highs), col(lows), col(closes), col(volumes))


def test_histogram_spreads_a_bar_over_the_bins_it_covers() -> None:
    # range 100..110, 10 bins of 1.00; bar 1 covers 100..102 (two bins), bar 2 is a point at 105
    px = one([102.0, 105.0, 110.0], [100.0, 105.0, 109.0], [200.0, 50.0, 10.0], 105.0)
    volume, lo, width = vp.histogram(px, P)
    assert lo[0] == 100.0 and width[0] == 1.0
    assert (
        volume[0, :2].tolist() == [100.0, 100.0] and volume[0, 5] == 50.0 and volume[0, 9] == 10.0
    )
    assert volume[0].sum() == 260.0


def test_point_of_control_value_area_and_nodes_by_hand() -> None:
    # 10 bins over 100..110; volume per bin set by one-bin bars: bins 2, 3 and 7 are heavy
    highs = [103.0, 104.0, 108.0, 106.0, 101.0, 110.0]
    lows = [102.0, 103.0, 107.0, 105.0, 100.0, 109.0]
    volumes = [300.0, 250.0, 200.0, 20.0, 20.0, 10.0]  # mean bin volume 80
    px = one(highs, lows, volumes, 105.5)  # the close sits in bin 5 (105..106)
    out = vp.profile(px, np.array([1.0]), P)
    assert out["profile_status"][0] == "OK"
    assert out["poc_252d"][0] == 102.5  # bin 2, 300 of 800
    # value area: 70% of 800 = 560: bin 2 (300) + bin 3 (250) = 550, then bin 7? no: neighbours
    # of the run 2..3 are bin 1 (0) and bin 4 (0): take above (ties go up), 550 + 0 < 560,
    # then bin 5 (20): 570 >= 560 -> run 2..5
    assert out["value_area_low"][0] == 102.0 and out["value_area_high"][0] == 106.0
    assert out["hvn_above"][0] == 107.5 and out["hvn_below"][0] == 103.5  # >= 120
    assert out["lvn_above"][0] == 106.5 and out["lvn_below"][0] == 104.5  # <= 40
    # within one ATR (1.0) of 105.5: bin centres 104.5, 105.5, 106.5 -> 0 + 20 + 0 of 800
    assert out["volume_near_close_share"][0] == pytest.approx(20 / 800)


def test_statuses_and_atr() -> None:
    px = one([100.0] * 3, [100.0] * 3, [10.0] * 3, 100.0)
    out = vp.profile(px, np.array([np.nan]), P)
    assert out["profile_status"][0] == "NO_RANGE" and np.isnan(out["poc_252d"][0])
    px = one([101.0] * 3, [99.0] * 3, [10.0] * 3, 100.0)
    out = vp.profile(px, np.array([np.nan]), vp.VolumeProfileParams(bins=10, min_bars=5))
    assert out["profile_status"][0] == "FEW_BARS" and np.isnan(out["value_area_high"][0])
    out = vp.profile(px, np.array([np.nan]), P)
    assert out["profile_status"][0] == "OK" and np.isnan(out["volume_near_close_share"][0])


def test_params_are_validated() -> None:
    with pytest.raises(ValueError):
        vp.VolumeProfileParams(bins=2)
    with pytest.raises(ValueError):
        vp.VolumeProfileParams(hvn_factor=0.5)


def test_compute_from_the_store_reads_the_momentum_row() -> None:
    writer, reader = store()
    c = series(vp.WINDOW, seed=7)
    write_bars(writer, {"EQ:A": c, "EQ:NEW": c[-100:]})
    write_rows(writer, vp.MOMENTUM, END, [{"instrument_id": "EQ:A", "atr_14": 1.0}])
    out = rows(compute_one(reader, vp.GROUP, END).frame)
    a = out["EQ:A"]
    assert a["profile_status"] == "OK" and 0 <= a["volume_near_close_share"] <= 1
    assert a["value_area_low"] <= a["poc_252d"] <= a["value_area_high"]
    assert out["EQ:NEW"]["profile_status"] == "FEW_BARS"


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(280, seed=11), "EQ:B": series(270, seed=12, start=50.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (265, 279)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, vp.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), vp.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_registered_with_params() -> None:
    assert GROUPS["volume_profile@v1"].table == "rollups/instrument/volume_profile@v1"
    assert vp.GROUP.inputs[0].sessions_back(None) == vp.WINDOW - 1
