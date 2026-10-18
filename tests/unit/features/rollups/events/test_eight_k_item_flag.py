"""``feature.eight_k_item_flag``: the adverse 8-K items 4.02, 4.01 and 5.02 within 20 sessions,
false for a name with other filings only, null for a name the filings group has no row for."""

import pandas as pd

from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END


def test_eight_k_item_flag_is_true_within_twenty_sessions_of_an_adverse_item() -> None:
    fs = site_features(FileConfigStore(REPO_ROOT / "config"))
    ids = ["EQ:RESTATE", "EQ:AUDITOR", "EQ:OFFICER", "EQ:OLD", "EQ:EDGE", "EQ:OTHER", "EQ:NONE"]
    cols = {
        "sessions_since_8k_4_02": [3, None, None, 21, None, None],
        "sessions_since_8k_4_01": [None, 20, None, None, None, None],
        "sessions_since_8k_5_02": [None, None, 0, 40, 20, None],
    }
    filings = pd.DataFrame(
        {
            "instrument_id": ids[:6],  # EQ:NONE has no row in the group
            "session_date": END,
            **{k: pd.array(v, dtype="Int64") for k, v in cols.items()},
        }
    )
    out = fs.evaluate({"rollups/instrument/filing_events@v1": filings}, ["eight_k_item_flag"])
    got = out.set_index("instrument_id")["eight_k_item_flag"].to_dict()
    assert got["EQ:RESTATE"] is True and got["EQ:AUDITOR"] is True and got["EQ:OFFICER"] is True
    assert got["EQ:EDGE"] is True  # exactly 20 sessions: the edge counts
    assert got["EQ:OLD"] is False  # 21 and 40 sessions
    assert got["EQ:OTHER"] is False  # a row (some other filing), no adverse item
    assert got.get("EQ:NONE") is None  # no row: never "no 8-K"
