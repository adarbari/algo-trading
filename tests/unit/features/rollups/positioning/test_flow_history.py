"""``flow_history@v1``: relative volume and the put / call ratio over the last 20 sessions of
``chain_flow@v1``, the ``min_sessions`` threshold, gaps and NO_CHAIN rows, zero denominators,
and the stored read through the runner (each session reads only its own window)."""

from dataclasses import replace

import numpy as np
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.positioning.flow_history import (
    GROUP,
    FlowHistoryParams,
    history,
)
from tests.helpers.rollup_store import END, store, write_rows

NAN = np.nan
P = FlowHistoryParams()
TABLE = "rollups/instrument/chain_flow@v1"


def test_ratios_by_hand_and_the_min_sessions_threshold() -> None:
    calls = np.array([[100.0] * 3] * 9 + [[300.0, 300.0, 300.0]])  # 10 sessions x 3 names
    puts = np.array([[100.0] * 3] * 9 + [[100.0, 100.0, 100.0]])
    calls[:, 1], puts[:, 1] = calls[:, 1] * 0 + NAN, puts[:, 1] * 0 + NAN  # no rows at all
    calls[:3, 2], puts[:3, 2] = NAN, NAN  # 7 sessions with a row
    out = history(calls, puts, replace(P, window=10, min_sessions=7))
    assert list(out["flow_history_days"]) == [10, 0, 7]
    assert out["option_volume_rel_20d"][0] == pytest.approx(400 / 200)  # today over the mean
    assert out["pc_volume_ratio_20d"][0] == pytest.approx((9 * 100 + 100) / (9 * 100 + 300))
    assert out["option_volume_rel_20d"][2] == pytest.approx(2.0)  # 6 earlier sessions
    assert np.isnan(out["option_volume_rel_20d"][1]) and np.isnan(out["pc_volume_ratio_20d"][1])
    strict = history(calls, puts, replace(P, window=10, min_sessions=8))  # 7 < 8: not shown
    assert np.isnan(strict["option_volume_rel_20d"][2]) and strict["flow_history_days"][2] == 7


def test_zero_denominators_and_a_missing_today_are_null() -> None:
    calls = np.array([[0.0, 100.0, 100.0]] * 5 + [[0.0, 100.0, NAN]])
    puts = np.array([[0.0, 100.0, 100.0]] * 5 + [[0.0, 100.0, NAN]])
    out = history(calls, puts, replace(P, window=6, min_sessions=2))
    assert np.isnan(out["option_volume_rel_20d"][0])  # the usual volume is 0
    assert np.isnan(out["pc_volume_ratio_20d"][0])  # no call volume in the window
    assert out["option_volume_rel_20d"][1] == pytest.approx(1.0)
    assert np.isnan(out["option_volume_rel_20d"][2]) and np.isnan(out["pc_volume_ratio_20d"][2])
    assert list(out["flow_history_days"]) == [6, 6, 5]  # a gap today still counts the rest


def test_reads_the_stored_chain_flow_window() -> None:
    writer, reader = store()
    days = sessions_ending(END, 25)
    for i, day in enumerate(days[5:]):  # 20 sessions ending today
        rows = []
        if i >= 8:  # EQ:A: 12 sessions with chain flow, today's call volume 300
            today = day == END
            rows.append(_row("EQ:A", 300.0 if today else 100.0, 100.0))
        if i >= 11:  # EQ:YOUNG: 9 sessions, under min_sessions
            rows.append(_row("EQ:YOUNG", 100.0, 100.0))
        if day == END:
            rows.append(_row("EQ:NEW", 50.0, 10.0))
            rows.append({"instrument_id": "EQ:DARK", "flow_status": "NO_CHAIN"})
        if day == days[-3]:
            rows.append({"instrument_id": "EQ:DARK", "flow_status": "NO_CHAIN"})
        if rows:
            write_rows(writer, TABLE, day, rows)
    frame = compute_one(reader, GROUP, END).frame
    assert frame is not None
    out = frame.set_index("instrument_id")
    a = out.loc["EQ:A"]
    assert a["flow_history_days"] == 12
    assert a["option_volume_rel_20d"] == pytest.approx(400 / 200)
    puts, calls = 12 * 100, 11 * 100 + 300  # today's 300 calls
    assert a["pc_volume_ratio_20d"] == pytest.approx(puts / calls)
    assert (out["flow_history_days"].to_dict()) == {
        "EQ:A": 12, "EQ:YOUNG": 9, "EQ:NEW": 1, "EQ:DARK": 0,
    }  # fmt: skip
    unknown = out.loc[["EQ:YOUNG", "EQ:NEW", "EQ:DARK"]].drop(columns="flow_history_days")
    assert unknown.isna().all().all()
    assert str(frame["option_volume_rel_20d"].dtype) == "float32"
    earlier = compute_one(reader, GROUP, days[-2]).frame  # a session reads only its own window
    assert earlier is not None
    assert earlier.set_index("instrument_id").loc["EQ:A", "flow_history_days"] == 11
    assert compute_one(reader, GROUP, days[0]).no_input  # no chain flow that session


def _row(uid: str, calls: float, puts: float) -> dict[str, object]:
    return {"instrument_id": uid, "flow_status": "OK", "call_volume": calls, "put_volume": puts}


def test_params_validate() -> None:
    with pytest.raises(ValueError, match="min_sessions"):
        replace(P, min_sessions=21)
    with pytest.raises(ValueError, match="min_sessions"):
        replace(P, min_sessions=1)
