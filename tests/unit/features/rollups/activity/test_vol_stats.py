"""``vol_stats@v1``: ATR(5) and ATR(20) against the momentum reference, hv10 / hv60 against
quant.realized_vol, the hv20 and volume percentiles by hand (240 known sessions needed), the
60-session volume average; gaps and short history are null; point in time."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.activity import vol_stats as vs
from algotrade.quant import realized_vol
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.unit.features.rollups.price.test_momentum import reference_wilder, rows, truncated

F32 = 2e-7


def test_pocket_pivot_by_hand() -> None:
    writer, reader = store()
    n = 40
    close = np.full(n, 100.0)
    close[-6], close[-4], close[-1] = 98.0, 97.0, 101.0  # two down days in the window, up today
    volume = np.full(n, 1000.0)
    volume[-6], volume[-4] = 1500.0, 1200.0  # the down days' volumes
    volume[-1] = 1600.0  # today beats both
    write_bars(
        writer,
        {"EQ:A": close, "EQ:WEAK": close, "EQ:DOWN": close, "EQ:FLAT": np.full(n, 100.0)},
        volume={
            "EQ:A": volume,
            "EQ:WEAK": np.where(np.arange(n) == n - 1, 1400.0, volume),
            "EQ:DOWN": volume,
            "EQ:FLAT": volume,
        },
    )
    out = rows(compute_one(reader, vs.GROUP, END).frame)
    assert out["EQ:A"]["pocket_pivot"] is True
    assert out["EQ:WEAK"]["pocket_pivot"] is False  # 1400 does not beat the 1500 down day
    assert out["EQ:FLAT"]["pocket_pivot"] is False  # no up close, no down day to beat


def test_compute_against_references_and_nulls() -> None:
    writer, reader = store()
    c = series(vs.LOOKBACK + 1, seed=5)
    volume = np.random.default_rng(1).uniform(1e5, 1e6, len(c))
    volume[-1] = 2e6  # the busiest session of the year
    write_bars(
        writer,
        {"EQ:A": c, "EQ:NEW": c[-15:], "EQ:GAP": c},
        volume={"EQ:A": volume, "EQ:NEW": volume[-15:], "EQ:GAP": volume},
        skip={"EQ:GAP": [vs.LOOKBACK - 30]},  # no bar 30 sessions before the end
    )
    out = rows(compute_one(reader, vs.GROUP, END).frame)
    a = out["EQ:A"]
    last = c[-vs.ATR_WARMUP :]
    hi = np.maximum(np.r_[c[-vs.ATR_WARMUP - 1], last[:-1]], last) * 1.01
    lo = np.minimum(np.r_[c[-vs.ATR_WARMUP - 1], last[:-1]], last) * 0.99
    prev = last[:-1]
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(abs(hi[1:] - prev), abs(lo[1:] - prev)))
    assert a["atr_5"] == pytest.approx(reference_wilder(list(tr), 5), rel=F32)
    assert a["atr_20"] == pytest.approx(reference_wilder(list(tr), 20), rel=F32)
    for n in vs.HV_WINDOWS:
        ref = realized_vol.close_to_close(c[-n - 1 :], n)[-1]
        assert a[f"hv{n}"] == pytest.approx(ref, rel=F32), n
    hv20 = realized_vol.close_to_close(c, 20)
    assert a["hv20_pctile_252d"] == pytest.approx(np.mean(hv20[-253:-1] < hv20[-1]), abs=1e-6)
    assert a["adv_shares_60d"] == pytest.approx(volume[-60:].mean(), rel=F32)
    assert a["volume_pctile_252d"] == 1.0
    assert a["pocket_pivot"] in (True, False)
    new = out["EQ:NEW"]
    assert not np.isnan(new["atr_5"]) and not np.isnan(new["hv10"])
    assert all(
        np.isnan(new[k])
        for k in ("atr_20", "hv60", "hv20_pctile_252d", "adv_shares_60d", "volume_pctile_252d")
    )
    gap = out["EQ:GAP"]
    assert np.isnan(gap["hv60"]) and np.isnan(gap["adv_shares_60d"])
    assert not np.isnan(gap["atr_20"])  # a 29-bar run is enough for ATR(20)
    assert np.isnan(gap["hv20_pctile_252d"])  # the gap voids 21 hv20 windows: 231 known < 240
    assert not np.isnan(gap["volume_pctile_252d"])  # 251 known volumes


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(300, seed=11), "EQ:B": series(280, seed=12, start=50.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (285, 299)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, vs.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), vs.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_registered() -> None:
    assert GROUPS["vol_stats@v1"].table == "rollups/instrument/vol_stats@v1"
    assert vs.GROUP.inputs[0].sessions_back(None) == vs.LOOKBACK == 272
