"""``cohort_pct_price@v1`` and its cohorts on hand-built source rows: the universe, sector and
industry percentiles, ETFs and name without a sector, the member floor, a partial day, a missing
source, the licence of every column, and a session that never reads a later company snapshot."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.data.feature_inputs import INPUTS
from algotrade.features.framework.feature import strictest
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.cohort import price
from algotrade.features.rollups.cohort.members import CohortParams, cohorts

DAY = date(2026, 10, 2)
P = CohortParams(min_members_universe=3, min_members_sector=2, min_members_industry=2)
STOCKS = ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:E"]


def universe(*stocks: str, funds: tuple[str, ...] = ()) -> pd.DataFrame:
    rows = [(i, "STOCK") for i in stocks] + [(i, "ETF") for i in funds]
    return pd.DataFrame(rows, columns=["instrument_id", "asset_class"])


def company() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:E", "ETF:X"],
            "sector": ["Tech", "Tech", "Tech", "Energy", None, "Tech"],
            "industry": ["Soft", "Soft", "Hard", "Oil", None, "Soft"],
        }
    )


def rows(table: str, column: str, values: dict[str, float], day: date = DAY) -> pd.DataFrame:
    return pd.DataFrame(
        {"instrument_id": list(values), "session_date": day, column: list(values.values())}
    )


def inputs(**over: pd.DataFrame | None) -> dict[str, pd.DataFrame | None]:
    ids = [*STOCKS, "ETF:X"]
    mom, adv, rs = [1, 2, 3, 4, 5, 9], [5, 4, 3, 2, 1, 9], [0, 1, 2, 3, 4, 5]
    base: dict[str, pd.DataFrame | None] = {
        price.TREND: rows(price.TREND, "mom_12_1", dict(zip(ids, mom, strict=True))),
        price.STATS: rows(price.STATS, "adv_usd_20d", dict(zip(ids, adv, strict=True))),
        price.RELATIVE: rows(price.RELATIVE, "rs_spy_63d", dict(zip(ids, rs, strict=True))),
        "universe": universe(*STOCKS, funds=("ETF:X",)),
        "instruments/company": company(),
    }  # fmt: skip
    return base | over


def out(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.set_index("instrument_id")


def test_percentiles_by_cohort() -> None:
    got = out(price.compute(inputs(), DAY, P))
    assert got.loc["EQ:A", "mom_12_1_pct_universe"] == 0.0
    assert got.loc["EQ:E", "mom_12_1_pct_universe"] == 1.0
    assert got.loc["EQ:C", "mom_12_1_pct_universe"] == 0.5
    assert got["adv_usd_20d_pct_universe"].loc["EQ:A"] == 1.0
    # sector Tech = A, B, C: ranked among themselves; Energy has one stock: below the floor
    assert got.loc[["EQ:A", "EQ:B", "EQ:C"], "mom_12_1_pct_sector"].tolist() == [0.0, 0.5, 1.0]
    assert np.isnan(got.loc["EQ:D", "mom_12_1_pct_sector"])
    # industry Soft = A, B
    assert got.loc[["EQ:A", "EQ:B"], "rs_spy_63d_pct_industry"].tolist() == [0.0, 1.0]
    assert "rs_spy_63d_pct_universe" not in got.columns


def test_a_fund_is_null_and_a_stock_without_a_sector_keeps_its_universe_rank() -> None:
    got = out(price.compute(inputs(), DAY, P))
    assert got.loc["ETF:X"].isna().all()
    assert got.loc["EQ:E", "mom_12_1_pct_universe"] == 1.0
    assert got.loc["EQ:E", ["mom_12_1_pct_sector", "mom_12_1_pct_industry"]].isna().all()


def test_a_cohort_below_the_floor_is_null() -> None:
    got = out(price.compute(inputs(), DAY, replace(P, min_members_universe=6)))
    assert got["mom_12_1_pct_universe"].isna().all()
    assert got["mom_12_1_pct_sector"].notna().any()


def test_a_missing_source_nulls_only_its_columns() -> None:
    got = out(price.compute(inputs(**{price.TREND: None}), DAY, P))
    assert got.filter(like="mom_12_1").isna().all().all()
    assert got["adv_usd_20d_pct_universe"].notna().any()


def test_low_coverage_makes_every_column_null() -> None:
    thin = rows(price.STATS, "adv_usd_20d", {"EQ:A": 1.0, "EQ:B": 2.0})  # 2 of 5 stocks
    got = out(price.compute(inputs(**{price.STATS: thin}), DAY, P))
    assert got.drop(columns=[]).isna().all().all()


def test_no_universe_or_no_company_snapshot() -> None:
    assert out(price.compute(inputs(universe=None), DAY, P)).isna().all().all()
    got = out(price.compute(inputs(**{"instruments/company": None}), DAY, P))
    assert got["mom_12_1_pct_universe"].notna().any()
    assert got.filter(regex="sector|industry").isna().all().all()


def test_only_the_session_rows_are_read() -> None:
    old = rows(
        price.TREND, "mom_12_1", {i: 100.0 - n for n, i in enumerate(STOCKS)}, date(2026, 9, 1)
    )
    both = pd.concat([old, inputs()[price.TREND]], ignore_index=True)
    assert out(price.compute(inputs(**{price.TREND: both}), DAY, P)).equals(
        out(price.compute(inputs(), DAY, P))
    )


def test_two_company_snapshots_never_leak_backward() -> None:
    """The loader hands compute the snapshot on or before the session; the cohorts follow it."""
    early = company()
    later = company().assign(sector="Tech")  # everyone moved into one sector later
    a = cohorts({"universe": universe(*STOCKS), "instruments/company": early}, STOCKS)["sector"]
    b = cohorts({"universe": universe(*STOCKS), "instruments/company": later}, STOCKS)["sector"]
    assert a.tolist() != b.tolist()
    assert a[3] != a[0]  # D is Energy in the early snapshot
    assert len(set(b.tolist())) == 1


def test_a_duplicate_company_row_takes_the_last() -> None:
    dup = pd.concat([company(), company().iloc[[0]].assign(sector="Energy")], ignore_index=True)
    codes = cohorts({"universe": universe(*STOCKS), "instruments/company": dup}, STOCKS)["sector"]
    assert codes[0] == codes[3]  # A moved to Energy with D


def test_output_is_deterministic_and_row_order_free() -> None:
    a = out(price.compute(inputs(), DAY, P))
    shuffled = {
        k: v.sample(frac=1, random_state=3) if v is not None else None for k, v in inputs().items()
    }
    pd.testing.assert_frame_equal(a, out(price.compute(shuffled, DAY, P)).loc[a.index])


def test_params_are_validated() -> None:
    with pytest.raises(ValueError, match="min_coverage"):
        CohortParams(min_coverage=1.5)
    with pytest.raises(ValueError, match="min_members_sector"):
        CohortParams(min_members_sector=1)


def test_every_column_carries_the_strictest_licence_of_its_source() -> None:
    for feature in price.FEATURES:
        source = feature.inputs[0]
        group, rest = source.split(".", 1)
        column, version = rest.split("@")
        origin = GROUPS[f"{group}@{version}"]
        licence = next(f.licence for f in origin.features if f.name == column)
        assert feature.licence == strictest([licence]), feature.name


def test_the_group_reads_registered_tables_only() -> None:
    for inp in price.GROUP.inputs:
        assert inp.table in INPUTS or inp.table.removeprefix("rollups/instrument/") in {
            g.key for g in GROUPS.values()
        }
