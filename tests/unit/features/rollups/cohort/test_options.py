"""``cohort_pct_options@v1`` on hand-built iv_history rows: the IV rank ranked by cohort, a
fund, a name without a rank, a missing source, and the open licence of every column."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.registry import GROUPS
from algotrade.features.rollups.cohort import options
from algotrade.features.rollups.cohort.members import CohortParams

DAY = date(2026, 10, 2)
P = CohortParams(min_members_universe=3, min_members_sector=2, min_members_industry=2)
IDS = ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "ETF:X"]


def inputs(ranks: list[float], day: date = DAY) -> dict[str, pd.DataFrame | None]:
    return {
        options.IV_HISTORY: pd.DataFrame(
            {"instrument_id": IDS, "session_date": day, "iv_rank_252d": ranks}
        ),
        "universe": pd.DataFrame({"instrument_id": IDS, "asset_class": ["STOCK"] * 4 + ["ETF"]}),
        "instruments/company": pd.DataFrame(
            {
                "instrument_id": IDS,
                "sector": ["Tech", "Tech", "Tech", "Energy", "Tech"],
                "industry": ["Soft", "Soft", "Hard", "Oil", "Soft"],
            }
        ),
    }


def test_ranks_by_cohort_and_a_name_without_a_rank_is_not_counted() -> None:
    got = options.compute(inputs([0.1, 0.9, np.nan, 0.5, 0.99]), DAY, P).set_index("instrument_id")
    assert got["iv_rank_252d_pct_universe"].loc[["EQ:A", "EQ:B", "EQ:D"]].tolist() == [0, 1, 0.5]
    assert np.isnan(got.loc["EQ:C", "iv_rank_252d_pct_universe"])
    assert got["iv_rank_252d_pct_sector"].loc[["EQ:A", "EQ:B"]].tolist() == [0.0, 1.0]
    assert got.loc["ETF:X"].isna().all()  # a fund is no member, whatever its IV rank


def test_a_missing_source_or_a_later_session_gives_no_rows() -> None:
    assert options.compute({**inputs([0.1] * 5), options.IV_HISTORY: None}, DAY, P).empty
    assert options.compute(inputs([0.1] * 5, date(2026, 10, 1)), DAY, P).empty


def test_the_columns_are_open_and_read_the_open_rank() -> None:
    origin = next(f for f in GROUPS["iv_history@v2"].features if f.name == "iv_rank_252d")
    assert origin.licence == "open"
    for feature in options.FEATURES:
        assert feature.licence == origin.licence
        assert feature.inputs[0] == "iv_history.iv_rank_252d@v2"
