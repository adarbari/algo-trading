"""``signed_volume@v1``: the 20-session on-balance volume change over the volume traded, by
hand; a flat close counts only in the total; gaps, no volume and short history are null."""

import numpy as np

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.activity import signed_volume as sv
from tests.helpers.rollup_store import END, store, write_bars


def test_obv_trend_by_hand() -> None:
    n = 30
    up = 100.0 + np.arange(n)  # every close is higher: all volume is buying
    down = 200.0 - np.arange(n)  # every close is lower: all volume is selling
    flat = np.full(n, 100.0)  # unchanged: signed volume 0
    mixed = 100.0 + np.arange(n) % 2  # alternates up, down: equal volume each way
    writer, reader = store()
    write_bars(
        writer,
        {"EQ:UP": up, "EQ:DOWN": down, "EQ:FLAT": flat, "EQ:MIXED": mixed, "EQ:SHORT": up[:10]},
    )
    frame = compute_one(reader, GROUPS["signed_volume@v1"], END).frame
    assert frame is not None
    rows = frame.set_index("instrument_id")["obv_trend_20d"]
    assert abs(rows["EQ:UP"] - 1.0) < 1e-6
    assert abs(rows["EQ:DOWN"] + 1.0) < 1e-6
    assert abs(rows["EQ:FLAT"]) < 1e-6
    assert abs(rows["EQ:MIXED"]) < 1e-6
    assert np.isnan(rows["EQ:SHORT"])  # fewer than 21 closes


def test_the_window_is_20_returns_and_volume_weights_the_days() -> None:
    closes = np.full((sv.WINDOW + 1, 1), 100.0)
    volumes = np.full((sv.WINDOW + 1, 1), 100.0)
    closes[1, 0] = 101.0  # an up day on 100 shares
    closes[2:, 0] = 101.0  # then flat: no signed volume
    assert abs(sv.obv_trend(closes, volumes)[0] - 100.0 / 2000.0) < 1e-12
    volumes[0, 0] = 1e9  # the base session's volume is not in the window
    assert abs(sv.obv_trend(closes, volumes)[0] - 100.0 / 2000.0) < 1e-12
    closes[5, 0] = np.nan  # a gap anywhere is unknown
    assert np.isnan(sv.obv_trend(closes, volumes)[0])
    closes[5, 0] = 101.0
    volumes[1:, 0] = 0.0  # no volume at all is unknown, never 0
    assert np.isnan(sv.obv_trend(closes, volumes)[0])
