"""The relative-strength and own-trend expression features (``config/site/features/technical/
price.toml``): ``rs_spy_positive``, ``rs_improving`` and ``sector_leader`` over
``relative_strength@v1`` rows, ``stock_tsmom_sign`` and ``capital_gains_overhang`` (EB E1),
and ``year_loser_flag``."""

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


def test_mom_12_1_vol_scaled_divides_by_hv60_and_is_unknown_on_zero_or_null(
    fs: FeatureSet,
) -> None:
    ids = ["EQ:A", "EQ:B", "EQ:C", "EQ:D"]
    frames: dict[str, pd.DataFrame | None] = {
        "rollups/instrument/trend_stats@v2": pd.DataFrame(
            {"instrument_id": ids, "session_date": END, "mom_12_1": [0.30, -0.10, 0.20, np.nan]}
        ).astype({"mom_12_1": "float32"}),
        "rollups/instrument/vol_stats@v1": pd.DataFrame(
            {"instrument_id": ids, "session_date": END, "hv60": [0.30, 0.20, 0.0, 0.25]}
        ).astype({"hv60": "float32"}),
    }
    out = fs.evaluate(frames, ["mom_12_1_vol_scaled"]).set_index("instrument_id")
    value = out["mom_12_1_vol_scaled"]
    assert value["EQ:A"] == pytest.approx(1.0, rel=1e-5)
    assert value["EQ:B"] == pytest.approx(-0.5, rel=1e-5)
    assert pd.isna(value["EQ:C"]) and pd.isna(value["EQ:D"])  # hv60 of 0, mom_12_1 null


def test_stock_tsmom_sign_needs_the_return_and_the_average_to_agree(fs: FeatureSet) -> None:
    ids = ["EQ:UP", "EQ:DOWN", "EQ:MIXED", "EQ:ZERO", "EQ:NONE"]
    frames: dict[str, pd.DataFrame | None] = {
        "rollups/instrument/trend_stats@v2": pd.DataFrame(
            {"instrument_id": ids, "session_date": END, "ret_252d": [0.2, -0.2, 0.2, 0.0, np.nan]}
        ).astype({"ret_252d": "float32"}),
        "rollups/instrument/price_stats@v2": pd.DataFrame(
            {
                "instrument_id": ids,
                "session_date": END,
                "close": [110.0, 90.0, 90.0, 110.0, 100.0],
                "sma_200": [100.0, 100.0, 100.0, 100.0, 100.0],
            }
        ).astype({"close": "float32", "sma_200": "float32"}),
    }
    out = fs.evaluate(frames, ["stock_tsmom_sign"]).set_index("instrument_id")
    value = out["stock_tsmom_sign"]
    assert value["EQ:UP"] == 1 and value["EQ:DOWN"] == -1
    assert value["EQ:MIXED"] == 0  # a year up but under the 200-day average
    assert value["EQ:ZERO"] == 0  # a flat year is neither sign
    assert pd.isna(value["EQ:NONE"])  # no 252-session return: unknown, never 0


def test_capital_gains_overhang_is_the_close_against_the_earnings_vwap(fs: FeatureSet) -> None:
    ids = ["EQ:ABOVE", "EQ:BELOW", "EQ:NOVWAP"]
    frames: dict[str, pd.DataFrame | None] = {
        "rollups/instrument/price_stats@v2": pd.DataFrame(
            {"instrument_id": ids, "session_date": END, "close": [105.0, 90.0, 100.0]}
        ).astype({"close": "float32"}),
        "rollups/instrument/anchored_vwap@v2": pd.DataFrame(
            {"instrument_id": ids, "session_date": END, "avwap_earnings": [100.0, 100.0, np.nan]}
        ).astype({"avwap_earnings": "float32"}),
    }
    out = fs.evaluate(frames, ["capital_gains_overhang"]).set_index("instrument_id")
    value = out["capital_gains_overhang"]
    assert value["EQ:ABOVE"] == pytest.approx(5 / 105, rel=1e-5)
    assert value["EQ:BELOW"] == pytest.approx(-10 / 90, rel=1e-5)
    assert pd.isna(value["EQ:NOVWAP"])  # no earnings anchor: unknown


def test_year_loser_flag_is_a_fixed_level_on_the_year_return_and_null_when_unknown(
    fs: FeatureSet,
) -> None:
    """A 252-session return of -30% or lower flags (the level is the flag's own, not a decile);
    a missing return is unknown, never False."""
    trend = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C", "EQ:D"],
            "session_date": END,
            "ret_252d": [-0.55, -0.30, -0.29, np.nan],
        }
    )
    out = fs.evaluate({"rollups/instrument/trend_stats@v2": trend}, ["year_loser_flag"])
    flags = out.set_index("instrument_id")["year_loser_flag"]
    assert [flags["EQ:A"], flags["EQ:B"], flags["EQ:C"]] == [True, True, False]
    assert pd.isna(flags["EQ:D"])
