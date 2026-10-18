"""``cp_iv_history@v1``: the change of each cp_iv column and of IV30 over 5 and 21 sessions,
null on a gap at either end, through the runner."""

import numpy as np
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.positioning.cp_iv_history import GROUP, CpIvHistoryParams
from tests.helpers.rollup_store import END, store, write_rows

CP_IV = "rollups/instrument/cp_iv@v1"
IV30 = "rollups/instrument/iv30@v1"


def test_changes_over_5_and_21_sessions_and_gaps() -> None:
    writer, reader = store()
    days = sessions_ending(END, 30)
    for i, day in enumerate(days):
        cp = [
            {"instrument_id": "EQ:A", "cp_iv_spread": 0.001 * i, "atm_call_iv": 0.3 + 0.01 * i,
             "atm_put_iv": 0.3 - 0.002 * i},
            {"instrument_id": "EQ:GAP", "cp_iv_spread": None if i == 29 - 5 else 0.01 * i,
             "atm_call_iv": 0.3, "atm_put_iv": 0.3},
        ]  # fmt: skip
        if i >= 20:  # EQ:NEW has 10 sessions: no 21-session change
            cp.append({"instrument_id": "EQ:NEW", "cp_iv_spread": 0.01 * i,
                       "atm_call_iv": 0.3, "atm_put_iv": 0.3})  # fmt: skip
        write_rows(writer, CP_IV, day, cp)
        iv = [{"instrument_id": "EQ:A", "iv30": 0.25 + 0.005 * i}]
        write_rows(writer, IV30, day, iv)  # EQ:NEW and EQ:GAP have no iv30
    out = compute_one(reader, GROUP, END).frame
    assert out is not None
    out = out.set_index("instrument_id")
    a = out.loc["EQ:A"]
    assert a["cp_iv_spread_chg_5d"] == pytest.approx(0.005)
    assert a["cp_iv_spread_chg_21d"] == pytest.approx(0.021)
    assert a["atm_call_iv_chg_5d"] == pytest.approx(0.05)
    assert a["atm_put_iv_chg_21d"] == pytest.approx(-0.042)
    assert a["iv30_chg_5d"] == pytest.approx(0.025)
    gap = out.loc["EQ:GAP"]  # no spread 5 sessions ago: null, not filled
    assert np.isnan(gap["cp_iv_spread_chg_5d"]) and not np.isnan(gap["cp_iv_spread_chg_21d"])
    assert np.isnan(gap["iv30_chg_5d"])
    new = out.loc["EQ:NEW"]
    assert new["cp_iv_spread_chg_5d"] == pytest.approx(0.05) and np.isnan(
        new["cp_iv_spread_chg_21d"]
    )


def test_params_are_fixed_by_the_column_names() -> None:
    assert (CpIvHistoryParams().short, CpIvHistoryParams().long) == (5, 21)
    with pytest.raises(ValueError, match="new version"):
        CpIvHistoryParams(short=10)
    assert GROUP.table == "rollups/instrument/cp_iv_history@v1"
