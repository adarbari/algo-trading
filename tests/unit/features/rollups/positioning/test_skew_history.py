"""``skew_history@v1``: rank and percentile of the 30-day skew over the window (the
``iv_history`` rules): the OP3 example (min 0.10, max 0.30, today 0.25 over 70 sessions: rank
0.75, PROVISIONAL), UNKNOWN below 60 sessions, a gap or no skew today, and the params."""

from dataclasses import replace

import numpy as np
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.positioning.skew_history import GROUP, SkewHistoryParams
from tests.helpers.rollup_store import END, store, write_rows

SKEW = "rollups/instrument/skew@v1"


def test_rank_percentile_and_status_over_stored_skews() -> None:
    writer, reader = store()
    days = sessions_ending(END, 70)
    wave = [0.10, 0.30, *np.linspace(0.12, 0.28, 67), 0.25]  # 70 skews, today 0.25
    for i, day in enumerate(days):
        rows = [{"instrument_id": "EQ:A", "skew": wave[i], "skew_status": "OK"}]
        if i >= 40:  # 30 sessions with a skew only
            rows.append({"instrument_id": "EQ:YOUNG", "skew": 0.2 + i / 1000})
        rows.append({"instrument_id": "EQ:NOSKEW", "skew": None if i == 69 else 0.2})
        if i != 30:  # a gap in EQ:GAPPED's history, counted out
            rows.append({"instrument_id": "EQ:GAPPED", "skew": wave[i]})
        write_rows(writer, SKEW, day, rows)
    assert compute_one(reader, GROUP, days[0]).frame is not None  # one session: UNKNOWN below
    out = compute_one(reader, GROUP, END).frame
    assert out is not None
    out = out.set_index("instrument_id")
    a = out.loc["EQ:A"]
    assert (a["history_days"], a["skew_rank_status"]) == (70, "PROVISIONAL")
    assert a["skew_rank_252d"] == pytest.approx((0.25 - 0.10) / (0.30 - 0.10))  # 0.75
    below = sum(1 for v in wave[:-1] if v < 0.25)
    assert a["skew_percentile_252d"] == pytest.approx(below / 69)
    young = out.loc["EQ:YOUNG"]
    assert (young["history_days"], young["skew_rank_status"]) == (30, "UNKNOWN")
    assert np.isnan(young["skew_rank_252d"]) and np.isnan(young["skew_percentile_252d"])
    noskew = out.loc["EQ:NOSKEW"]  # no skew today (a status, not a zero): no rank
    assert noskew["history_days"] == 69 and noskew["skew_rank_status"] == "PROVISIONAL"
    assert np.isnan(noskew["skew_rank_252d"])
    assert out.loc["EQ:GAPPED", "history_days"] == 69  # the gap is not filled


def test_params_validate_like_iv_history() -> None:
    p = SkewHistoryParams()
    assert (p.window, p.min_provisional) == (252, 60)
    with pytest.raises(ValueError, match="min_provisional"):
        replace(p, min_provisional=253)
    assert GROUP.table == "rollups/instrument/skew_history@v1"
