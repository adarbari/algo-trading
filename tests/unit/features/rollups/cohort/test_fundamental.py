"""``cohort_pct_fundamental@v1`` on hand-built short-interest rows: days to cover ranked by
cohort, a fund, a missing source, the licence and the no-ML reach of every column."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.feature import strictest
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.cohort import fundamental
from algotrade.features.rollups.cohort.members import CohortParams
from algotrade.features.site import site_features
from algotrade.services.evaluation.training.no_ml import no_ml_reads
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

DAY = date(2026, 10, 2)
P = CohortParams(min_members_universe=3, min_members_sector=2, min_members_industry=2)
IDS = ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "ETF:X"]


def rows(column: str, values: list[float], day: date = DAY) -> pd.DataFrame:
    return pd.DataFrame({"instrument_id": IDS, "session_date": day, column: values})


def inputs(**over: pd.DataFrame | None) -> dict[str, pd.DataFrame | None]:
    base: dict[str, pd.DataFrame | None] = {
        fundamental.SHORT: rows("days_to_cover", [1.0, 4.0, 2.0, 3.0, 9.0]),
        "universe": pd.DataFrame({"instrument_id": IDS, "asset_class": ["STOCK"] * 4 + ["ETF"]}),
        "instruments/company": pd.DataFrame(
            {
                "instrument_id": IDS,
                "sector": ["Tech", "Tech", "Tech", "Energy", "Tech"],
                "industry": ["Soft", "Soft", "Hard", "Oil", "Soft"],
            }
        ),
    }
    return base | over


def test_universe_sector_and_industry_ranks() -> None:
    got = fundamental.compute(inputs(), DAY, P).set_index("instrument_id")
    assert got["days_to_cover_pct_universe"].loc[IDS[:4]].tolist() == [0.0, 1.0, 1 / 3, 2 / 3]
    # sector Tech = A, B, C (ETF X is no member); Energy has one stock: below the floor
    assert got["days_to_cover_pct_sector"].loc[["EQ:A", "EQ:B", "EQ:C"]].tolist() == [0.0, 1.0, 0.5]
    assert np.isnan(got.loc["EQ:D", "days_to_cover_pct_sector"])
    assert got["days_to_cover_pct_industry"].loc[["EQ:A", "EQ:B"]].tolist() == [0.0, 1.0]
    assert got.loc["ETF:X"].isna().all()


def test_a_missing_source_gives_no_rows() -> None:
    assert fundamental.compute(inputs(**{fundamental.SHORT: None}), DAY, P).empty


def test_only_the_session_rows_are_read() -> None:
    old = rows("days_to_cover", [9.0, 8.0, 7.0, 6.0, 5.0], date(2026, 9, 1))
    both = pd.concat([old, inputs()[fundamental.SHORT]], ignore_index=True)
    a = fundamental.compute(inputs(**{fundamental.SHORT: both}), DAY, P)
    pd.testing.assert_frame_equal(a, fundamental.compute(inputs(), DAY, P))


def test_every_column_carries_the_strictest_licence_of_its_source() -> None:
    for feature in fundamental.FEATURES:
        group, rest = feature.inputs[0].split(".", 1)
        column, version = rest.split("@")
        licence = next(f.licence for f in GROUPS[f"{group}@{version}"].features if f.name == column)
        assert feature.licence == strictest([licence]), feature.name


def test_every_column_reaches_the_no_ml_table() -> None:
    """A percentile of FINRA's figure is FINRA's data: a learned scorer may not read it."""
    features = site_features(FileConfigStore(REPO_ROOT / "config", local=False))
    names = [f"rollup.cohort_pct_fundamental@v1.{f.name}" for f in fundamental.FEATURES]
    reads = no_ml_reads(features, names)
    assert set(reads) == set(names)
    assert all(t == ["events/short_interest"] for t in reads.values())
