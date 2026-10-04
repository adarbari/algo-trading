"""``price_moves@v1``: the largest one-day move over 20 sessions, by hand; gaps and short
history are null (never a shorter window); split-adjusted as of each session (a split is not
a move); point in time (a later session never leaks)."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.price import price_moves as pm
from tests.helpers.rollup_store import END, series, store, write_bars, write_split

F32 = 2e-7


def moves(frame: pd.DataFrame | None) -> dict[str, float]:
    assert frame is not None
    return frame.set_index("instrument_id")["one_day_move"].to_dict()


def test_largest_absolute_move_by_hand() -> None:
    writer, reader = store()
    c = series(40)
    down = c.copy()
    down[-10:] *= 0.85  # a 15% drop 10 sessions before the end, held
    up = c.copy()
    up[-21:] *= 1.12  # a 12% jump exactly 21 sessions back: outside the 20 returns
    write_bars(writer, {"EQ:A": c, "EQ:DOWN": down, "EQ:UP": up})
    out = moves(compute_one(reader, pm.GROUP, END).frame)
    expected = float(np.max(np.abs(c[-20:] / c[-21:-1] - 1)))
    assert out["EQ:A"] == pytest.approx(expected, rel=F32)
    assert out["EQ:DOWN"] == pytest.approx(abs(c[-10] * 0.85 / c[-11] - 1), rel=F32)
    assert out["EQ:UP"] == pytest.approx(out["EQ:A"], rel=F32)
    assert set(compute_one(reader, pm.GROUP, END).frame.dtypes.astype(str)) >= {"float32"}


def test_gaps_and_short_history_are_null_not_zero() -> None:
    writer, reader = store()
    write_bars(
        writer,
        {"EQ:NEW": series(20, seed=2), "EQ:GAP": series(40, seed=3), "EQ:OK": series(21)},
        skip={"EQ:GAP": [30]},  # no bar 9 sessions before the end
    )
    out = moves(compute_one(reader, pm.GROUP, END).frame)
    assert np.isnan(out["EQ:NEW"]) and np.isnan(out["EQ:GAP"])
    assert out["EQ:OK"] > 0  # exactly 21 closes is enough


def test_split_is_not_a_move_and_no_later_split_leaks() -> None:
    writer, reader = store()
    c = series(40, seed=7)
    raw = c.copy()
    raw[-5:] /= 2  # 2-for-1 split 5 sessions before the end
    days = write_bars(writer, {"EQ:P": c, "EQ:S": raw})
    write_split(writer, "EQ:S", days[-5], 2.0, stored=END)
    results = list(compute_sessions(reader, pm.GROUP, days[-8:]))
    for result in results:
        out = moves(result.frame)
        assert out["EQ:S"] == pytest.approx(out["EQ:P"], rel=F32)
        assert out["EQ:S"] < 0.2


def test_only_instruments_trading_on_the_session_and_registered() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(30)})
    write_bars(writer, {"EQ:OLD": series(30)}, end=pd.Timestamp(END).date().replace(day=1))
    assert set(moves(compute_one(reader, pm.GROUP, END).frame)) == {"EQ:A"}
    assert GROUPS["price_moves@v1"].table == "rollups/instrument/price_moves@v1"
    assert pm.GROUP.inputs[0].sessions_back(None) == pm.WINDOW
