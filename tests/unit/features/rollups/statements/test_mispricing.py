"""mispricing@v1: the year-ago assets (point in time), each anomaly's formula, the percentile
ranks, the QMJ-like score and the composite rank (missing never passes, stale is not used)."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.statements import mispricing as mp
from algotrade.features.rollups.statements.lines import PRICE_STATS, STATEMENTS

SESSION = date(2025, 6, 30)
AS_OF = date(2025, 3, 31)
AGO = date(2024, 3, 31)
N = 6
PARAMS = mp.MispricingParams(min_members=3)
FACT_COLUMNS = [
    "instrument_id",
    "concept",
    "tag",
    "period_start",
    "period_end",
    "filed",
    "value",
    "accn",
]


def ids() -> list[str]:
    return [f"EQ:{i}" for i in range(N)]


def asset_fact(iid: str, value: float, end: date = AGO, filed: date | None = None) -> tuple:
    return (
        iid,
        "assets",
        "us-gaap:Assets",
        None,
        end,
        filed or end + timedelta(days=40),
        value,
        "A",
    )


def frames(**over: dict) -> dict:
    """A cross-section where a higher index is riskier on every anomaly and worse on quality."""
    rows = range(N)
    stats = pd.DataFrame({"instrument_id": ids(), "session_date": SESSION})
    bs = pd.DataFrame(
        {
            "instrument_id": ids(),
            "session_date": SESSION,
            "total_assets": 1000.0,
            "total_debt": [100.0 + 50 * i for i in rows],
            "stockholders_equity": 400.0,
            "cash": 50.0,
            "total_liabilities": 600.0,
            "current_assets": 300.0,
            "current_liabilities": [150.0 + 10 * i for i in rows],
            "bs_as_of": AS_OF,
            "is_financial": False,
            "bs_status": "OK",
        }
    )
    inc = pd.DataFrame(
        {
            "instrument_id": ids(),
            "session_date": SESSION,
            "gross_profit_ttm": [500.0 - 50 * i for i in rows],
            "is_ttm_as_of": AS_OF,
            "is_status": "OK",
        }
    )
    cf = pd.DataFrame(
        {
            "instrument_id": ids(),
            "session_date": SESSION,
            "ocf_ttm": [100.0 - 25 * i for i in rows],
            "cf_as_of": AS_OF,
            "cf_status": "OK",
        }
    )
    fin = pd.DataFrame(
        {
            "instrument_id": ids(),
            "session_date": SESSION,
            "net_income_ttm": [100.0 - 15 * i for i in rows],
            "revenue_ttm": 1000.0,
            "ttm_as_of": AS_OF,
            "financials_status": "OK",
        }
    )
    fun = pd.DataFrame(
        {
            "instrument_id": ids(),
            "session_date": SESSION,
            "shares_outstanding": [100.0 + i for i in rows],
            "shares_outstanding_year_ago": 100.0,
            "market_cap_status": "OK",
        }
    )
    facts = pd.DataFrame(
        [asset_fact(f"EQ:{i}", 1000.0 - 30 * i) for i in rows], columns=FACT_COLUMNS
    )
    out = {
        PRICE_STATS: stats, mp.BALANCE: bs, mp.INCOME: inc, mp.CASH_FLOW: cf,
        mp.FINANCIALS: fin, mp.FUNDAMENTALS: fun, STATEMENTS: facts,
    }  # fmt: skip
    return {**out, **over}


def run(inputs: dict | None = None, p: mp.MispricingParams = PARAMS) -> pd.DataFrame:
    return mp.compute(inputs or frames(), SESSION, p).set_index("instrument_id")


def test_formulas_of_one_instrument() -> None:
    row = run().loc["EQ:2"]
    assert row["total_assets_1y_ago"] == 940.0
    assert row["asset_growth"] == pytest.approx(1000 / 940 - 1)
    assert row["accruals"] == pytest.approx((70 - 50) / 1000)
    assert row["gross_profit_to_assets"] == pytest.approx(0.4)
    assert row["net_operating_assets"] == pytest.approx((200 + 400 - 50) / 1000)
    ohlson = (
        -1.32 - 0.407 * np.log(1000) + 6.03 * 0.6 - 1.43 * (300 - 170) / 1000
        + 0.0757 * 170 / 300 - 2.37 * 70 / 1000 - 1.83 * 50 / 600
    )  # fmt: skip
    assert row["ohlson_o"] == pytest.approx(ohlson)


def test_riskier_names_rank_higher_and_quality_lower() -> None:
    out = run()
    assert out["composite_rank"].is_monotonic_increasing
    assert out["composite_rank"].iloc[0] == pytest.approx(0.0)
    assert out["composite_rank"].iloc[-1] == pytest.approx(1.0)
    assert out["quality_score"].is_monotonic_decreasing
    assert (out["composite_inputs"] == 7).all()


def test_year_ago_assets_ignores_a_restatement_filed_after_the_session_and_far_ends() -> None:
    inputs = frames()
    late = asset_fact("EQ:0", 5.0, AGO, filed=SESSION + timedelta(days=1))  # not yet public
    far = asset_fact("EQ:1", 5.0, AGO - timedelta(days=200))  # not about a year back
    facts = pd.concat([inputs[STATEMENTS], pd.DataFrame([late, far], columns=FACT_COLUMNS)])
    facts = facts[~((facts["instrument_id"] == "EQ:1") & (facts["period_end"] == AGO))]
    out = run(frames(**{STATEMENTS: facts}))
    assert (
        out.loc["EQ:0", "total_assets_1y_ago"] == 1000.0
    )  # the original figure, as of the session
    assert pd.isna(out.loc["EQ:1", "total_assets_1y_ago"])
    assert pd.isna(out.loc["EQ:1", "asset_growth"])


def test_a_restatement_filed_by_the_session_replaces_the_original() -> None:
    inputs = frames()
    restated = asset_fact("EQ:0", 900.0, AGO, filed=date(2025, 1, 5))
    facts = pd.concat([inputs[STATEMENTS], pd.DataFrame([restated], columns=FACT_COLUMNS)])
    assert run(frames(**{STATEMENTS: facts})).loc["EQ:0", "total_assets_1y_ago"] == 900.0


def test_missing_never_passes() -> None:
    inputs = frames()
    cf = inputs[mp.CASH_FLOW].copy()
    cf.loc[cf["instrument_id"] == "EQ:3", "ocf_ttm"] = np.nan  # accruals and ohlson unknown: 5 left
    out = run(frames(**{mp.CASH_FLOW: cf}))
    assert pd.isna(out.loc["EQ:3", "accruals"]) and pd.isna(out.loc["EQ:3", "ohlson_o"])
    assert out.loc["EQ:3", "composite_inputs"] == 5
    assert pd.notna(out.loc["EQ:3", "composite_rank"])
    cf.loc[cf["instrument_id"] == "EQ:4", ["ocf_ttm"]] = np.nan
    inc = inputs[mp.INCOME].copy()
    inc.loc[inc["instrument_id"] == "EQ:4", "gross_profit_ttm"] = np.nan  # a third gone: 4 left
    out = run(frames(**{mp.CASH_FLOW: cf, mp.INCOME: inc}))
    assert pd.isna(out.loc["EQ:4", "composite_rank"]) and pd.isna(
        out.loc["EQ:4", "composite_inputs"]
    )


def test_a_thin_cross_section_is_not_ranked() -> None:
    out = run(p=mp.MispricingParams(min_members=N + 1))
    assert out["composite_rank"].isna().all() and out["quality_score"].isna().all()


def test_stale_statements_are_not_used() -> None:
    inputs = frames()
    bs = inputs[mp.BALANCE].copy()
    bs.loc[bs["instrument_id"] == "EQ:5", "bs_status"] = "STALE"
    out = run(frames(**{mp.BALANCE: bs}))
    assert out.loc["EQ:5", ["asset_growth", "accruals", "net_operating_assets"]].isna().all()
    assert pd.isna(out.loc["EQ:5", "composite_rank"])


def test_banks_have_no_balance_sheet_anomalies() -> None:
    bs = frames()[mp.BALANCE].copy()
    bs.loc[bs["instrument_id"] == "EQ:1", "is_financial"] = True
    row = run(frames(**{mp.BALANCE: bs})).loc["EQ:1"]
    assert (
        row[["accruals", "gross_profit_to_assets", "net_operating_assets", "ohlson_o"]].isna().all()
    )
    assert pd.notna(row["asset_growth"])


def test_no_statement_tables_gives_unknown_not_an_error() -> None:
    stats = frames()[PRICE_STATS]
    out = run({PRICE_STATS: stats})
    assert set(mp.COLUMNS) == set(out.columns)
    assert out["composite_rank"].isna().all()


@pytest.mark.parametrize(
    "bad",
    [
        {"ago_tolerance_days": 0},
        {"min_members": 1},
        {"min_quality_inputs": 7},
        {"min_anomalies": 8},
    ],
)
def test_params_are_validated(bad: dict) -> None:
    with pytest.raises(ValueError):
        mp.MispricingParams(**bad)


def test_a_partial_balance_sheet_is_not_mixed_across_dates() -> None:
    bs = frames()[mp.BALANCE].copy()
    bs.loc[bs["instrument_id"] == "EQ:2", "bs_status"] = "PARTIAL"
    row = run(frames(**{mp.BALANCE: bs})).loc["EQ:2"]
    measures = ["asset_growth", "net_operating_assets", "ohlson_o", "accruals"]
    assert row[[*measures, "gross_profit_to_assets", "total_assets_1y_ago"]].isna().all()
    assert pd.isna(row["composite_rank"])


def test_net_income_and_cash_flow_must_end_on_the_same_quarter() -> None:
    cf = frames()[mp.CASH_FLOW].copy()
    cf["cf_as_of"] = pd.Series(
        pd.NaT, index=cf.index, dtype="datetime64[ns]"
    )  # an unknown end is not aligned
    cf.loc[cf["instrument_id"] == "EQ:1", "cf_as_of"] = pd.Timestamp(AS_OF - timedelta(days=91))
    cf.loc[cf["instrument_id"] == "EQ:0", "cf_as_of"] = pd.Timestamp(AS_OF)
    out = run(frames(**{mp.CASH_FLOW: cf}))
    assert pd.notna(out.loc["EQ:0", "accruals"]) and pd.notna(out.loc["EQ:0", "ohlson_o"])
    for iid in ("EQ:1", "EQ:2"):
        assert out.loc[iid, ["accruals", "ohlson_o"]].isna().all()
