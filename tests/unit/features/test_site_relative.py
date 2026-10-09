"""The relative-strength expression features (``config/site/features/technical/price.toml``):
``rs_spy_positive``, ``rs_improving`` and ``sector_leader`` over ``relative_strength@v1`` rows."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


RELATIVE_STRENGTH = "rollups/instrument/relative_strength@v1"


def _relative_rows(**columns: list[float]) -> dict[str, pd.DataFrame | None]:
    ids = ["EQ:A", "EQ:B", "EQ:C", "EQ:NONE"]
    frame = pd.DataFrame({"instrument_id": ids, "session_date": END, **columns})
    return {RELATIVE_STRENGTH: frame.astype(dict.fromkeys(columns, "float32"))}


def test_rs_spy_positive_is_true_above_zero_and_unknown_when_null(fs: FeatureSet) -> None:
    frames = _relative_rows(rs_spy_63d=[0.10, 0.0, -0.05, np.nan])
    out = fs.evaluate(frames, ["rs_spy_positive"]).set_index("instrument_id")
    assert out["rs_spy_positive"].to_dict() == {
        "EQ:A": True,
        "EQ:B": False,  # level with SPY is not outperforming
        "EQ:C": False,
        "EQ:NONE": None,
    }


def test_rs_improving_is_true_when_the_trend_is_above_zero(fs: FeatureSet) -> None:
    frames = _relative_rows(rs_spy_trend_20d=[0.03, 0.0, -0.02, np.nan])
    out = fs.evaluate(frames, ["rs_improving"]).set_index("instrument_id")
    assert out["rs_improving"].to_dict() == {
        "EQ:A": True,
        "EQ:B": False,
        "EQ:C": False,
        "EQ:NONE": None,
    }


def test_sector_leader_is_a_top_three_sector_and_unknown_without_a_rank(fs: FeatureSet) -> None:
    frames = _relative_rows(sector_rank_63d=[1, 3, 4, np.nan])
    out = fs.evaluate(frames, ["sector_leader"]).set_index("instrument_id")
    assert out["sector_leader"].to_dict() == {
        "EQ:A": True,
        "EQ:B": True,  # the edge counts
        "EQ:C": False,
        "EQ:NONE": None,
    }
