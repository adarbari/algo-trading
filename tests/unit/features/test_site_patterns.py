"""The site's candle expression features (``config/site/features/swing.toml``):
``inside_day_breakout`` and ``strong_close`` by their cases and nulls."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END

TREND = "rollups/instrument/trend_stats@v2"
CANDLE = "rollups/instrument/candle@v1"


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def test_inside_day_breakout(fs: FeatureSet) -> None:
    ids = ["EQ:UP", "EQ:DOWN", "EQ:NOTINSIDE", "EQ:NOREL", "EQ:NORET", "EQ:FLATFALSE"]
    trend = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "ret_1d": [0.02, -0.01, 0.03, 0.02, np.nan, 0.0],
        }
    )
    candle = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "prev_bar_relation": ["INSIDE", "INSIDE", "OVERLAP", None, "INSIDE", "INSIDE"],
        }
    )
    out = fs.evaluate({TREND: trend, CANDLE: candle}, ["inside_day_breakout"])
    got = out.set_index("instrument_id")["inside_day_breakout"]
    assert got["EQ:UP"] is True
    assert got["EQ:DOWN"] is False and got["EQ:NOTINSIDE"] is False  # a false leg decides
    assert got["EQ:FLATFALSE"] is False  # an unchanged close is not a breakout up
    assert pd.isna(got["EQ:NOREL"]) and pd.isna(got["EQ:NORET"])


def test_strong_close(fs: FeatureSet) -> None:
    ids = ["EQ:STRONG", "EQ:EDGE", "EQ:WEAKCLOSE", "EQ:DOJI", "EQ:NORANGE"]
    trend = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "close_range_pos": [0.9, 0.7, 0.5, 0.95, np.nan],
        }
    )
    candle = pd.DataFrame(
        {
            "instrument_id": ids,
            "session_date": END,
            "body_share": [0.8, 0.5, 0.6, 0.05, np.nan],
        }
    )
    out = fs.evaluate({TREND: trend, CANDLE: candle}, ["strong_close"])
    got = out.set_index("instrument_id")["strong_close"]
    assert got.loc[ids[:4]].tolist() == [True, True, False, False]  # both thresholds inclusive
    assert pd.isna(got["EQ:NORANGE"])
