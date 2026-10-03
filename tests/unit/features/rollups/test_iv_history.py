"""``iv_history@v2``: rank and percentile over the window, UNKNOWN / PROVISIONAL / FULL
thresholds, gaps and the Cboe source option (IV minus HV is an expression feature:
``tests/unit/features/test_site.py``)."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.iv_history import GROUP, IvHistoryParams, history
from tests.helpers.rollup_store import END, store
from tests.helpers.stored_frames import stamped

NAN = np.nan


def test_rank_percentile_and_status_thresholds() -> None:
    p = IvHistoryParams(window=10, min_provisional=3)
    full = [1, 2, 3, 4, 6, 7, 8, 9, 10, 5]
    provisional = [NAN] * 5 + [0.2, 0.3, 0.1, 0.4, 0.3]
    unknown = [NAN] * 8 + [0.2, 0.3]
    no_today = [*range(1, 10), NAN]
    flat = [0.3] * 10
    ivs = np.array([full, provisional, unknown, no_today, flat], dtype=float).T
    out = history(ivs, p)
    assert list(out["rank_status"]) == ["FULL", "PROVISIONAL", "UNKNOWN", "PROVISIONAL", "FULL"]
    assert list(out["history_days"]) == [10, 5, 2, 9, 10]
    assert out["iv_rank_252d"][0] == pytest.approx(4 / 9)
    assert out["iv_percentile_252d"][0] == pytest.approx(4 / 9)
    assert out["iv_rank_252d"][1] == pytest.approx((0.3 - 0.1) / 0.3)
    assert out["iv_percentile_252d"][1] == pytest.approx(2 / 4)  # 0.2 and 0.1 below 0.3
    assert (
        np.isnan(out["iv_rank_252d"][2:4]).all() and np.isnan(out["iv_percentile_252d"][2:4]).all()
    )
    assert np.isnan(out["iv_rank_252d"][4]) and out["iv_percentile_252d"][4] == 0.0  # max == min
    with pytest.raises(ValueError, match="min_provisional"):
        replace(p, min_provisional=11)
    with pytest.raises(ValueError, match="source"):
        replace(p, source="vix")


def _write(writer: object, table: str, day: object, rows: list[dict[str, object]]) -> None:
    writer.write_table(table, day, f"r-{day}", stamped(rows, day, f"r-{day}"))  # type: ignore[attr-defined]


def test_reads_a_year_of_stored_iv30() -> None:
    writer, reader = store()
    days = sessions_ending(END, 70)
    for i, day in enumerate(days[5:]):  # 65 sessions, rising; a gap at days[30]
        if day == days[30]:
            continue
        rows = [{"instrument_id": "EQ:A", "iv30": 0.2 + i / 1000, "iv30_cboe": 0.9 - i / 1000}]
        rows.append({"instrument_id": "EQ:NEW", "iv30": 0.5 if day == END else None})
        _write(writer, "rollups/instrument/iv30@v1", day, rows)
    assert compute_one(reader, GROUP, days[0]).no_input  # no iv30 that session
    out = compute_one(reader, GROUP, END).frame
    assert out is not None
    a, new = (
        out.set_index("instrument_id").loc["EQ:A"],
        out.set_index("instrument_id").loc["EQ:NEW"],
    )
    assert (a["history_days"], a["rank_status"]) == (64, "PROVISIONAL")
    assert (a["iv_rank_252d"], a["iv_percentile_252d"]) == (1.0, 1.0)
    assert (new["history_days"], new["rank_status"]) == (1, "UNKNOWN")
    assert pd.isna(new["iv_rank_252d"])
    cboe = compute_one(reader, GROUP, END, IvHistoryParams(source="cboe")).frame
    row = cboe.set_index("instrument_id").loc["EQ:A"]  # type: ignore[union-attr]
    assert row["iv30"] == pytest.approx(0.9 - 64 / 1000) and row["iv_rank_252d"] == 0.0
