"""``cutler_rsi@v1``: Cutler's RSI(3) by hand (simple means, not Wilder's recursion); a gap, a
short history and a flat close are null, never zero; no row for an instrument without a bar on
the session; point in time (a later bar never leaks); split-adjusted as of each session."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.oscillators import cutler_rsi as cr
from tests.helpers.rollup_store import END, series, store, write_bars, write_split

F32 = 2e-7


def rsi(frame: pd.DataFrame | None) -> dict[str, float]:
    assert frame is not None
    return frame.set_index("instrument_id")["rsi_3"].to_dict()


def by_hand(closes: np.ndarray) -> float:
    change = np.diff(closes[-4:])
    gain, loss = np.clip(change, 0, None).mean(), np.clip(-change, 0, None).mean()
    return 100 - 100 / (1 + gain / loss)


def test_simple_average_rsi_by_hand_and_the_extremes() -> None:
    writer, reader = store()
    c = series(40)
    down = c.copy()
    down[-4:] = down[-5] * np.array([0.98, 0.96, 0.95, 0.93])  # three straight falls
    up = c.copy()
    up[-4:] = up[-5] * np.array([1.01, 1.02, 1.03, 1.05])
    mixed = c.copy()
    mixed[-4:] = mixed[-5] * np.array([0.99, 0.97, 1.0, 0.98])  # only the last 3 changes count
    write_bars(writer, {"EQ:A": c, "EQ:DOWN": down, "EQ:UP": up, "EQ:MIX": mixed})
    out = rsi(compute_one(reader, cr.GROUP, END).frame)
    assert out["EQ:A"] == pytest.approx(by_hand(c), rel=F32)
    assert out["EQ:MIX"] == pytest.approx(by_hand(mixed), rel=F32)
    assert out["EQ:DOWN"] == pytest.approx(0.0, abs=1e-4)  # no gain in the window
    assert out["EQ:UP"] == 100.0  # no loss: 100, not null
    assert set(compute_one(reader, cr.GROUP, END).frame.dtypes.astype(str)) >= {"float32"}


def test_it_is_not_wilders_rsi() -> None:
    """The simple mean of 3 changes differs from the recursive smoothing of the same changes."""
    c = np.array([100.0, 101.0, 99.0, 100.5, 98.0])
    change = np.diff(c)[-3:]
    cutler = 100 - 100 / (1 + np.clip(change, 0, None).mean() / np.clip(-change, 0, None).mean())
    gain = loss = 0.0  # a Wilder recursion with period 3 seeded at the first change
    for x in np.diff(c):
        gain, loss = (gain * 2 + max(x, 0)) / 3, (loss * 2 + max(-x, 0)) / 3
    assert cutler != pytest.approx(100 - 100 / (1 + gain / loss), rel=1e-3)


def test_gaps_short_history_and_a_flat_close_are_null_not_zero() -> None:
    writer, reader = store()
    flat = series(40)
    flat[-4:] = flat[-5]  # no move over the 3 changes (the 4 closes are equal to the one before)
    write_bars(
        writer,
        {"EQ:NEW": series(3, seed=2), "EQ:GAP": series(40, seed=3), "EQ:OK": series(4),
         "EQ:FLAT": flat},
        skip={"EQ:GAP": [38]},  # no bar 1 session before the end
    )  # fmt: skip
    out = rsi(compute_one(reader, cr.GROUP, END).frame)
    assert np.isnan(out["EQ:NEW"]) and np.isnan(out["EQ:GAP"]) and np.isnan(out["EQ:FLAT"])
    assert not np.isnan(out["EQ:OK"])  # exactly 4 closes is enough


def test_split_is_not_a_move_and_no_later_split_leaks() -> None:
    writer, reader = store()
    c = series(40, seed=7)
    raw = c.copy()
    raw[-2:] /= 2  # 2-for-1 split 2 sessions before the end
    days = write_bars(writer, {"EQ:P": c, "EQ:S": raw})
    write_split(writer, "EQ:S", days[-2], 2.0, stored=END)
    for result in compute_sessions(reader, cr.GROUP, days[-6:]):
        out = rsi(result.frame)
        assert out["EQ:S"] == pytest.approx(out["EQ:P"], rel=F32)


def test_only_instruments_trading_on_the_session_and_registered() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(30)})
    write_bars(writer, {"EQ:OLD": series(30)}, end=pd.Timestamp(END).date().replace(day=1))
    assert set(rsi(compute_one(reader, cr.GROUP, END).frame)) == {"EQ:A"}
    assert GROUPS["cutler_rsi@v1"].table == "rollups/instrument/cutler_rsi@v1"
    assert cr.GROUP.inputs[0].sessions_back(None) == cr.WINDOW
