"""``vol_long@v1``: hv126 / hv252 against quant.realized_vol, the downside deviation by hand,
nulls for a short history or a gap, and point in time (a session never sees later bars)."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.activity import vol_long as vl
from algotrade.quant import realized_vol
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.unit.features.rollups.price.test_momentum import rows, truncated

F32 = 2e-7


def test_hv_against_the_reference_and_downside_by_hand() -> None:
    writer, reader = store()
    c = series(vl.LOOKBACK + 1, seed=7)
    write_bars(writer, {"EQ:A": c})
    a = rows(compute_one(reader, vl.GROUP, END).frame)["EQ:A"]
    for n in vl.HV_WINDOWS:
        ref = realized_vol.close_to_close(c[-n - 1 :], n)[-1]
        assert a[f"hv{n}"] == pytest.approx(ref, rel=F32), n
    r = np.diff(np.log(c))[-252:]
    expected = np.sqrt(np.mean(np.minimum(r, 0.0) ** 2) * 252)
    assert a["downside_dev_252"] == pytest.approx(expected, rel=F32)


def test_a_name_that_only_jumps_up_has_no_downside() -> None:
    writer, reader = store()
    up = 100.0 * np.exp(np.cumsum(np.abs(np.random.default_rng(3).normal(0.001, 0.02, 253))))
    write_bars(writer, {"EQ:UP": up})
    a = rows(compute_one(reader, vl.GROUP, END).frame)["EQ:UP"]
    assert a["downside_dev_252"] == 0.0 and a["hv252"] > 0


def test_short_history_and_gaps_are_null_never_a_shorter_window() -> None:
    writer, reader = store()
    c = series(vl.LOOKBACK + 1, seed=5)
    write_bars(
        writer,
        {"EQ:A": c, "EQ:NEW": c[-200:], "EQ:GAP": c},
        skip={"EQ:GAP": [vl.LOOKBACK - 30]},
    )
    out = rows(compute_one(reader, vl.GROUP, END).frame)
    new = out["EQ:NEW"]  # 199 returns: enough for hv126, not hv252 or the year's downside
    assert not np.isnan(new["hv126"])
    assert np.isnan(new["hv252"]) and np.isnan(new["downside_dev_252"])
    gap = out["EQ:GAP"]  # a missing bar 30 sessions back voids every window that spans it
    assert np.isnan(gap["hv126"]) and np.isnan(gap["hv252"]) and np.isnan(gap["downside_dev_252"])


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(300, seed=11), "EQ:B": series(290, seed=12, start=50.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (289, 299)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, vl.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), vl.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_registered_and_a_leaf() -> None:
    assert GROUPS["vol_long@v1"].table == "rollups/instrument/vol_long@v1"
    assert vl.GROUP.inputs[0].sessions_back(None) == vl.LOOKBACK == 252
    readers = [k for k, g in GROUPS.items() if any("vol_long" in i.table for i in g.inputs)]
    assert readers == []  # nothing reads vol_long as an input
