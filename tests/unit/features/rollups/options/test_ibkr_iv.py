"""``ibkr_iv@v1``: IBKR's IV30 / HV30 with the iv_history rank rules (rank, percentile,
UNKNOWN / PROVISIONAL / FULL) over stored ``volatility/ibkr_iv30`` rows; every feature is
personal-licence; the site's ``iv_rank`` / ``iv_percentile`` prefer IBKR and fall back to ours
with ``iv_rank_source`` saying which."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.options.ibkr_iv import GROUP, IbkrIvParams, compute
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END, store
from tests.helpers.stored_frames import stamped

TABLE = "volatility/ibkr_iv30"


def _rows(days: list, ivs: dict[str, list[float | None]]) -> pd.DataFrame:  # type: ignore[type-arg]
    return pd.DataFrame(
        [
            {"instrument_id": iid, "session_date": d, "iv30_ibkr": v, "hv30_ibkr": 0.2}
            for iid, values in ivs.items()
            for d, v in zip(days, values, strict=True)
        ]
    )


def test_rank_percentile_and_status_follow_iv_history() -> None:
    p = IbkrIvParams(window=10, min_provisional=3)
    days = sessions_ending(END, 10)
    rows = _rows(
        days,
        {
            "EQ:FULL": [1, 2, 3, 4, 6, 7, 8, 9, 10, 5],
            "EQ:PROV": [None] * 5 + [0.2, 0.3, 0.1, 0.4, 0.3],
            "EQ:UNK": [None] * 8 + [0.2, 0.3],
        },
    )
    out = compute({TABLE: rows}, END, p).set_index("instrument_id")
    assert out["rank_status_ibkr"].to_dict() == {
        "EQ:FULL": "FULL",
        "EQ:PROV": "PROVISIONAL",
        "EQ:UNK": "UNKNOWN",
    }
    assert out.loc["EQ:FULL", "iv_rank_252d_ibkr"] == pytest.approx(4 / 9)
    assert out.loc["EQ:FULL", "iv_percentile_252d_ibkr"] == pytest.approx(4 / 9)
    assert out.loc["EQ:PROV", "history_days_ibkr"] == 5
    assert np.isnan(out.loc["EQ:UNK", "iv_rank_252d_ibkr"])
    assert out.loc["EQ:FULL", "iv30_ibkr"] == 5 and out.loc["EQ:FULL", "hv30_ibkr"] == 0.2
    with pytest.raises(ValueError, match="min_provisional"):
        replace(p, min_provisional=11)


def test_reads_stored_ibkr_rows_and_needs_the_session() -> None:
    writer, reader = store()
    days = sessions_ending(END, 70)
    for i, day in enumerate(days[:-1]):
        rows = [{"instrument_id": "EQ:A", "iv30_ibkr": 0.2 + i / 1000, "hv30_ibkr": 0.18,
                 "source_kind": "history"}]  # fmt: skip
        writer.write_table(TABLE, day, f"h{i}", stamped(rows, day, f"h{i}"))
    assert compute_one(reader, GROUP, END).no_input  # no IBKR row for the session
    today = [{"instrument_id": "EQ:A", "iv30_ibkr": 0.1, "hv30_ibkr": 0.2,
              "source_kind": "snapshot"}]  # fmt: skip
    writer.write_table(TABLE, END, "snap", stamped(today, END, "snap"))
    out = compute_one(reader, GROUP, END).frame
    assert out is not None
    row = out.set_index("instrument_id").loc["EQ:A"]
    assert row["rank_status_ibkr"] == "PROVISIONAL" and row["history_days_ibkr"] == 70
    assert row["iv_rank_252d_ibkr"] == 0.0 and row["iv_percentile_252d_ibkr"] == 0.0
    assert str(out["iv30_ibkr"].dtype) == "float32"


def test_every_feature_is_personal_licence() -> None:
    assert {f.licence for f in GROUP.features} == {"personal"}


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def test_iv_rank_prefers_ibkr_and_falls_back_to_ours_with_its_source(fs: FeatureSet) -> None:
    ours = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C"],
            "session_date": END,
            "iv_rank_252d": [0.4, 0.6, None],
            "iv_percentile_252d": [0.5, 0.7, None],
        }
    )
    ibkr = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B"],
            "session_date": END,
            "iv_rank_252d_ibkr": [0.9, None],  # B: IBKR's rank is UNKNOWN
            "iv_percentile_252d_ibkr": [0.8, None],
        }
    )
    names = ["iv_rank", "iv_percentile", "iv_rank_source"]
    frames = {
        "rollups/instrument/iv_history@v2": ours,
        "rollups/instrument/ibkr_iv@v1": ibkr,
    }
    out = fs.evaluate(frames, names).set_index("instrument_id")
    assert out.loc["EQ:A", "iv_rank"] == pytest.approx(0.9)
    assert out.loc["EQ:A", "iv_rank_source"] == "ibkr"
    assert out.loc["EQ:B", "iv_rank"] == pytest.approx(0.6)
    assert out.loc["EQ:B", "iv_percentile"] == pytest.approx(0.7)
    assert out.loc["EQ:B", "iv_rank_source"] == "ours"
    assert pd.isna(out.loc["EQ:C", "iv_rank"]) and pd.isna(out.loc["EQ:C", "iv_rank_source"])
    # IBKR down for the session (no ibkr_iv rows at all): ours, labelled
    down = fs.evaluate({"rollups/instrument/iv_history@v2": ours}, names)
    assert list(down["iv_rank_source"][:2]) == ["ours", "ours"]


def test_expression_features_take_the_strictest_licence_of_their_inputs(fs: FeatureSet) -> None:
    for name in ("iv_rank", "iv_percentile", "iv_rank_source"):
        assert fs.expressions[name].feature.licence == "personal"
    assert fs.expressions["iv_hv_spread"].feature.licence == "open"
