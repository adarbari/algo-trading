"""``cohort_pct_valuation@v1`` on hand-built pe_ratio rows: the P/E ranked by cohort, a
loss-making name not counted, a missing source, and the licence and no-ML freedom of every
column."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.rollups.cohort import valuation
from algotrade.features.rollups.cohort.members import CohortParams
from algotrade.features.site import site_features
from algotrade.services.evaluation.training.no_ml import no_ml_reads
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

DAY = date(2026, 10, 2)
P = CohortParams(min_members_universe=3, min_members_sector=2, min_members_industry=2)
IDS = ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "ETF:X"]


def inputs(pe: list[float], day: date = DAY) -> dict[str, pd.DataFrame | None]:
    return {
        valuation.PE: pd.DataFrame({"instrument_id": IDS, "session_date": day, "pe_ratio": pe}),
        "universe": pd.DataFrame({"instrument_id": IDS, "asset_class": ["STOCK"] * 4 + ["ETF"]}),
        "instruments/company": pd.DataFrame(
            {
                "instrument_id": IDS,
                "sector": ["Tech", "Tech", "Tech", "Energy", "Tech"],
                "industry": ["Soft", "Soft", "Hard", "Oil", "Soft"],
            }
        ),
    }


def test_ranks_by_cohort_and_a_loss_making_name_is_not_counted() -> None:
    got = valuation.compute(inputs([30.0, 10.0, np.nan, 20.0, 5.0]), DAY, P).set_index(
        "instrument_id"
    )
    assert got["pe_ratio_pct_universe"].loc[["EQ:A", "EQ:B", "EQ:D"]].tolist() == [1.0, 0.0, 0.5]
    assert np.isnan(got.loc["EQ:C", "pe_ratio_pct_universe"])
    assert got["pe_ratio_pct_sector"].loc[["EQ:A", "EQ:B"]].tolist() == [1.0, 0.0]
    assert got.loc["ETF:X"].isna().all()


def test_a_missing_source_or_a_later_session_gives_no_rows() -> None:
    assert valuation.compute({**inputs([1.0] * 5), valuation.PE: None}, DAY, P).empty
    assert valuation.compute(inputs([1.0] * 5, date(2026, 10, 1)), DAY, P).empty


def test_the_columns_are_open_and_no_learned_scorer_is_barred() -> None:
    features = site_features(FileConfigStore(REPO_ROOT / "config", local=False))
    names = [f"rollup.cohort_pct_valuation@v1.{f.name}" for f in valuation.FEATURES]
    assert not no_ml_reads(features, names)
    for feature in valuation.FEATURES:
        assert feature.inputs[0] == "pe_ratio@v1"  # the expression feature over open inputs
        assert feature.licence == "open", feature.name
