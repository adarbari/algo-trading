"""``max_return@v1``: the best day of the last 21 sessions, by hand; gaps and short history are
null; a window that is one session short does not see the older day."""

import numpy as np

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.activity import max_return as mr
from tests.helpers.rollup_store import END, store, write_bars


def test_best_day_by_hand() -> None:
    n = 30
    flat = np.full(n, 100.0)
    spike = flat.copy()
    spike[-10:] = 110.0  # +10% on the 10th-last session
    old = flat.copy()
    old[-23:] = 120.0  # +20% 23 sessions back: outside the 21 returns
    down = 100.0 * 0.99 ** np.arange(n)  # every day loses 1%
    writer, reader = store()
    write_bars(writer, {"EQ:SPIKE": spike, "EQ:OLD": old, "EQ:DOWN": down, "EQ:SHORT": flat[:10]})
    out = compute_one(reader, GROUPS["max_return@v1"], END)
    frame = out.frame
    assert frame is not None
    rows = frame.set_index("instrument_id")["max_ret_21d"]
    assert abs(rows["EQ:SPIKE"] - 0.10) < 1e-6
    assert abs(rows["EQ:OLD"]) < 1e-6  # the jump left the window
    assert abs(rows["EQ:DOWN"] - (-0.01)) < 1e-6  # signed: the best of all-losing days
    assert np.isnan(rows["EQ:SHORT"])  # history shorter than 22 closes


def test_the_window_is_21_returns() -> None:
    closes = np.full((mr.WINDOW + 1, 1), 100.0)
    closes[1, 0] = 130.0  # the first return of the window
    closes[2:, 0] = 130.0
    assert abs(mr.best_day(closes)[0] - 0.30) < 1e-12
    closes[0, 0] = np.nan  # a gap anywhere is unknown
    assert np.isnan(mr.best_day(closes)[0])
