"""``ibkr_iv_history@v1``: IBKR's IV30 change over 5 and 21 sessions, null on a gap at either
end, personal licence, through the runner."""

import numpy as np
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.options.ibkr_iv_history import (
    FEATURES,
    GROUP,
    IbkrIvHistoryParams,
)
from tests.helpers.rollup_store import END, store, write_rows

IBKR_IV = "rollups/instrument/ibkr_iv@v1"


def test_changes_over_5_and_21_sessions_and_gaps() -> None:
    writer, reader = store()
    days = sessions_ending(END, 30)
    for i, day in enumerate(days):
        rows = [
            {"instrument_id": "EQ:A", "iv30_ibkr": 0.25 + 0.005 * i},
            {"instrument_id": "EQ:GAP", "iv30_ibkr": None if i == 29 - 5 else 0.3},
        ]
        if i >= 20:  # ten sessions only: no 21-session change
            rows.append({"instrument_id": "EQ:NEW", "iv30_ibkr": 0.2 + 0.01 * i})
        write_rows(writer, IBKR_IV, day, rows)
    out = compute_one(reader, GROUP, END).frame
    assert out is not None
    out = out.set_index("instrument_id")
    assert out.loc["EQ:A", "ibkr_iv_chg_5d"] == pytest.approx(0.025)
    assert out.loc["EQ:A", "ibkr_iv_chg_21d"] == pytest.approx(0.105)
    gap = out.loc["EQ:GAP"]  # no IV 5 sessions ago: null, not filled
    assert np.isnan(gap["ibkr_iv_chg_5d"]) and gap["ibkr_iv_chg_21d"] == pytest.approx(0.0)
    new = out.loc["EQ:NEW"]
    assert new["ibkr_iv_chg_5d"] == pytest.approx(0.05) and np.isnan(new["ibkr_iv_chg_21d"])


def test_personal_licence_and_fixed_windows() -> None:
    assert {f.licence for f in FEATURES} == {"personal"}
    with pytest.raises(ValueError, match="new version"):
        IbkrIvHistoryParams(long=60)
    assert GROUP.table == "rollups/instrument/ibkr_iv_history@v1" and GROUP.optional
