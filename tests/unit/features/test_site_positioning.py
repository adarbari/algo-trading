"""The skew and term-structure expression features of
``config/site/features/options/positioning.toml``
(``skew_rr25``, ``term_ratio_30_90``, ``term_ratio_next_30``,
``option_stock_volume_ratio``): values, the sign conventions
(backwardation above 1, contango below), and nulls (UNKNOWN, never zero or infinity)."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END

SKEW_TABLE = "rollups/instrument/skew@v1"
IV30 = "rollups/instrument/iv30@v1"
IV_TERM = "rollups/instrument/iv_term@v1"


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def _frame(ids: list[str], **columns: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"instrument_id": ids, "session_date": END, **columns})


def test_skew_rr25_is_the_put_vol_minus_the_call_vol(fs: FeatureSet) -> None:
    skew = _frame(
        ["EQ:A", "EQ:CALLRICH", "EQ:NONE"],
        iv_25p=[0.325, 0.30, np.nan],
        iv_25c=[0.265, 0.34, np.nan],
    )
    out = fs.evaluate({SKEW_TABLE: skew}, ["skew_rr25"]).set_index("instrument_id")
    assert out.loc["EQ:A", "skew_rr25"] == pytest.approx(0.06)  # six vol points: puts rich
    assert out.loc["EQ:CALLRICH", "skew_rr25"] == pytest.approx(-0.04)  # negative: call-rich
    assert pd.isna(out.loc["EQ:NONE", "skew_rr25"])  # no skew (status not OK): UNKNOWN
    assert fs.expressions["skew_rr25"].feature.licence == "open"


def test_term_ratios_read_backwardation_above_one_and_the_front_premium(fs: FeatureSet) -> None:
    ids = ["EQ:BACK", "EQ:CONTANGO", "EQ:EVENT", "EQ:NO90", "EQ:NONEXT", "EQ:NOIV30"]
    iv30 = _frame(ids, iv30=[0.44, 0.28, 0.30, 0.30, 0.30, np.nan])
    term = _frame(
        ids,
        iv_next=[0.50, 0.28, 0.42, 0.31, np.nan, 0.31],
        iv_90d=[0.40, 0.32, 0.30, np.nan, 0.30, 0.30],
    )
    names = ["term_ratio_30_90", "term_ratio_next_30"]
    out = fs.evaluate({IV30: iv30, IV_TERM: term}, names).set_index("instrument_id")
    assert out.loc["EQ:BACK", "term_ratio_30_90"] == pytest.approx(1.1)  # backwardation
    assert out.loc["EQ:CONTANGO", "term_ratio_30_90"] == pytest.approx(0.875)  # contango
    assert out.loc["EQ:EVENT", "term_ratio_next_30"] == pytest.approx(1.4)  # event in the front
    assert out.loc["EQ:BACK", "term_ratio_next_30"] == pytest.approx(0.50 / 0.44)
    assert pd.isna(out.loc["EQ:NO90", "term_ratio_30_90"])  # no 90-day vol
    assert out.loc["EQ:NO90", "term_ratio_next_30"] == pytest.approx(
        31 / 30
    )  # the side that exists
    assert pd.isna(out.loc["EQ:NONEXT", "term_ratio_next_30"])
    assert out.loc["EQ:NOIV30", names].isna().all()  # no iv30: both ratios UNKNOWN
    assert {fs.expressions[n].feature.licence for n in names} == {"open"}


def test_option_stock_volume_ratio_is_contracts_times_100_over_shares(fs: FeatureSet) -> None:
    flow = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:ZERO", "EQ:DARK"],
            "session_date": END,
            "call_volume": [3000.0, 10.0, np.nan],
            "put_volume": [2000.0, 10.0, np.nan],
        }
    )
    volume = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:ZERO", "EQ:DARK"],
            "session_date": END,
            "session_volume": [10_000_000.0, 0.0, 1e6],
        }
    )
    out = fs.evaluate(
        {"rollups/instrument/chain_flow@v1": flow, "rollups/instrument/volume@v1": volume},
        ["option_stock_volume_ratio"],
    ).set_index("instrument_id")["option_stock_volume_ratio"]
    assert out["EQ:A"] == pytest.approx(0.05)  # 5,000 contracts x 100 over 10m shares
    assert pd.isna(out["EQ:ZERO"]) and pd.isna(out["EQ:DARK"])  # never infinity; no chain
    assert fs.expressions["option_stock_volume_ratio"].feature.licence == "open"
