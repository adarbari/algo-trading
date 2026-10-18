"""The site's statement expression features (``config/site/features/company/statements.toml``):
EBITDA, the margins, interest cover, ROE / ROA / ROIC, net debt, debt to equity, P/B, free cash
flow and its yield, enterprise value, EV / EBITDA and EV / EBIT, the cash-based operating
profitability, the composite value yield and the three and five year growth rates:
each formula's value on hand-built group rows, each null guard (a negative equity or invested
capital, no revenue, a status that is not usable, an untagged line), the bank rule (the EBIT
family null, ROE / ROA / P/B kept) and that nothing divides into an infinity."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END

TABLES = {
    "rollups/instrument/price_stats@v2": ("close",),
    "rollups/instrument/fundamentals@v4": ("shares_outstanding", "market_cap_status"),
    "rollups/instrument/financials@v3": (
        "revenue_ttm", "net_income_ttm", "eps_diluted_ttm", "financials_status", "eps_stale",
        "is_adr", "ttm_as_of",
    ),
    "rollups/instrument/income_statement@v2": (
        "gross_profit_ttm", "ebit_ttm", "da_ttm", "interest_expense_ttm", "is_status",
        "is_ttm_as_of",
    ),
    "rollups/instrument/cash_flow@v2": ("ocf_ttm", "capex_ttm", "cf_status", "cf_as_of"),
    "rollups/instrument/balance_sheet@v2": (
        "cash", "total_debt", "total_assets", "stockholders_equity", "bs_status",
    ),
    "rollups/instrument/growth_history@v2": (
        "revenue_ttm_3y_ago", "revenue_ttm_5y_ago", "eps_diluted_ttm_3y_ago",
        "eps_diluted_ttm_5y_ago", "gh_status",
    ),
}  # fmt: skip
BASE = {  # a healthy industrial: market cap 10 x 100 = 1000
    "close": 100.0, "shares_outstanding": 10.0, "market_cap_status": "OK",
    "revenue_ttm": 1000.0, "net_income_ttm": 100.0, "eps_diluted_ttm": 10.0,
    "financials_status": "OK", "eps_stale": False, "is_adr": False,
    "ttm_as_of": pd.Timestamp("2025-03-31"), "is_ttm_as_of": pd.Timestamp("2025-03-31"),
    "cf_as_of": pd.Timestamp("2025-03-31"),
    "gross_profit_ttm": 400.0, "ebit_ttm": 150.0, "da_ttm": 50.0, "interest_expense_ttm": 30.0,
    "is_status": "OK", "ocf_ttm": 200.0, "capex_ttm": 80.0, "cf_status": "OK",
    "cash": 100.0, "total_debt": 300.0, "total_assets": 1000.0, "stockholders_equity": 500.0,
    "bs_status": "OK", "revenue_ttm_3y_ago": 500.0, "revenue_ttm_5y_ago": 250.0,
    "eps_diluted_ttm_3y_ago": 5.0, "eps_diluted_ttm_5y_ago": 2.5, "gh_status": "OK",
}  # fmt: skip
NAMES = [
    "ebitda", "gross_margin", "operating_margin", "interest_cover", "roe", "roa", "roic",
    "net_debt", "debt_to_equity", "pb_ratio", "fcf", "fcf_yield", "enterprise_value",
    "ev_ebitda", "revenue_cagr_3y", "revenue_cagr_5y", "eps_cagr_3y", "eps_cagr_5y",
    "cash_op_profitability", "ev_ebit", "composite_value_yield",
]  # fmt: skip
STALE_ALL = {"is_status": "STALE", "bs_status": "STALE", "cf_status": "STALE"}


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def evaluate(fs: FeatureSet, rows: dict[str, dict]) -> pd.DataFrame:
    """Every statement feature over one row per id: ``BASE`` with the row's overrides."""
    full = {i: {**BASE, **over} for i, over in rows.items()}
    ids = list(full)
    frames = {
        table: pd.DataFrame(
            {"instrument_id": ids, "session_date": END}
            | {c: pd.Series([full[i][c] for i in ids], dtype=object) for c in columns}
        )
        for table, columns in TABLES.items()
    }
    for frame in frames.values():  # numbers as floats (None is NaN), the rest as given
        for c in frame.columns[2:]:
            if c in ("ttm_as_of", "is_ttm_as_of", "cf_as_of"):
                frame[c] = pd.to_datetime(frame[c])
            elif c not in ("market_cap_status", "financials_status", "is_status", "cf_status",
                         "bs_status", "gh_status", "eps_stale", "is_adr"):  # fmt: skip
                frame[c] = frame[c].astype(float)
            elif c in ("eps_stale", "is_adr"):
                frame[c] = frame[c].astype(bool)
    return fs.evaluate(frames, NAMES).set_index("instrument_id")


def test_each_formula_on_a_healthy_company(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:A": {}}).loc["EQ:A"]
    assert out["ebitda"] == 200.0 and out["gross_margin"] == pytest.approx(0.4)
    assert out["operating_margin"] == pytest.approx(0.15) and out["interest_cover"] == 5.0
    assert out["roe"] == pytest.approx(0.2) and out["roa"] == pytest.approx(0.1)
    assert out["roic"] == pytest.approx(150 * 0.79 / 700)  # equity 500 + debt 300 - cash 100
    assert out["net_debt"] == 200.0 and out["debt_to_equity"] == pytest.approx(0.6)
    assert out["pb_ratio"] == pytest.approx(2.0)  # market cap 1000 / equity 500
    assert out["fcf"] == 120.0 and out["fcf_yield"] == pytest.approx(0.12)
    assert out["enterprise_value"] == 1200.0 and out["ev_ebitda"] == pytest.approx(6.0)
    assert out["revenue_cagr_3y"] == pytest.approx(2 ** (1 / 3) - 1)  # 500 -> 1000
    assert out["revenue_cagr_5y"] == pytest.approx(4 ** (1 / 5) - 1)  # 250 -> 1000
    assert out["eps_cagr_3y"] == pytest.approx(2 ** (1 / 3) - 1)  # 5 -> 10
    assert out["eps_cagr_5y"] == pytest.approx(4 ** (1 / 5) - 1)  # 2.5 -> 10


def test_a_shrinking_company_has_a_negative_growth_rate_above_minus_one(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:S": {"revenue_ttm_3y_ago": 8000.0, "eps_diluted_ttm_3y_ago": 80.0}})
    assert out.loc["EQ:S", "revenue_cagr_3y"] == pytest.approx(0.125 ** (1 / 3) - 1)
    assert -1 < out.loc["EQ:S", "eps_cagr_3y"] < 0


def test_negative_equity_gives_no_return_ratio_but_invested_capital_can_still_be_positive(
    fs: FeatureSet,
) -> None:
    out = evaluate(fs, {"EQ:N": {"stockholders_equity": -50.0}}).loc["EQ:N"]
    assert out[["roe", "debt_to_equity", "pb_ratio"]].isna().all()
    assert out["roic"] == pytest.approx(150 * 0.79 / 150)  # -50 + 300 - 100
    assert out["roa"] == pytest.approx(0.1) and out["net_debt"] == 200.0  # equity not used


def test_invested_capital_not_positive_gives_no_roic(fs: FeatureSet) -> None:
    rows = {
        "EQ:C": {"stockholders_equity": 50.0, "total_debt": 0.0, "cash": 200.0},  # -150
        "EQ:Z": {"stockholders_equity": 100.0, "total_debt": 0.0, "cash": 100.0},  # exactly 0
    }
    assert evaluate(fs, rows)["roic"].isna().all()


def test_zero_or_missing_revenue_is_null_not_infinite(fs: FeatureSet) -> None:
    rows = {"EQ:0": {"revenue_ttm": 0.0}, "EQ:NA": {"revenue_ttm": None}}
    out = evaluate(fs, rows)
    assert (
        out[["gross_margin", "operating_margin", "revenue_cagr_3y", "revenue_cagr_5y"]]
        .isna()
        .all()
        .all()
    )
    assert out["ebitda"].notna().all()  # revenue is not an input of EBITDA


def test_a_status_that_is_not_usable_nulls_what_is_built_on_it(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:OLD": STALE_ALL}).loc["EQ:OLD"]
    built = [
        *("ebitda", "gross_margin", "operating_margin", "interest_cover", "roe", "roa", "roic"),
        *("net_debt", "debt_to_equity", "pb_ratio", "fcf", "enterprise_value"),
    ]
    assert out[built].isna().all()
    assert out[["fcf_yield", "ev_ebitda"]].isna().all()  # built on a stale fcf / ebitda
    only = {"EQ:BS": {"bs_status": "STALE"}, "EQ:CF": {"cf_status": "STALE"},
            "EQ:IS": {"is_status": "STALE"}, "EQ:FIN": {"financials_status": "STALE"},
            "EQ:GH": {"gh_status": "STALE"}}  # fmt: skip
    got = evaluate(fs, only)
    assert (
        got.loc["EQ:BS", ["net_debt", "roe", "roic", "pb_ratio", "enterprise_value"]].isna().all()
    )
    assert got.loc["EQ:BS", ["ebitda", "fcf", "gross_margin"]].notna().all()
    assert pd.isna(got.loc["EQ:CF", "fcf"]) and got.loc["EQ:CF", "ebitda"] == 200.0
    assert pd.isna(got.loc["EQ:IS", "ebitda"]) and got.loc["EQ:IS", "roe"] == pytest.approx(0.2)
    assert got.loc["EQ:FIN", ["roe", "roa", "gross_margin", "revenue_cagr_3y"]].isna().all()
    assert got.loc["EQ:FIN", ["eps_cagr_3y", "eps_cagr_5y"]].notna().all()  # the EPS is not stale
    assert got.loc["EQ:GH", ["revenue_cagr_3y", "eps_cagr_5y"]].isna().all()
    assert got.loc["EQ:GH", "revenue_cagr_3y"] != got.loc["EQ:GH", "revenue_cagr_3y"]


def test_a_bank_keeps_roe_roa_and_pb_but_has_no_ebit_family(fs: FeatureSet) -> None:
    bank = {
        "is_status": "FINANCIAL",
        "ebit_ttm": None,
        "da_ttm": None,
        "interest_expense_ttm": None,
    }
    leak = {**bank, "ebit_ttm": 100.0, "da_ttm": 10.0, "interest_expense_ttm": 5.0}  # gated anyway
    out = evaluate(fs, {"EQ:BANK": bank, "EQ:LEAK": leak})
    assert (
        out[["ebitda", "operating_margin", "interest_cover", "roic", "ev_ebitda"]]
        .isna()
        .all()
        .all()
    )
    kept = out.loc["EQ:BANK"]
    assert kept["roe"] == pytest.approx(0.2) and kept["roa"] == pytest.approx(0.1)
    assert kept["pb_ratio"] == pytest.approx(2.0) and kept["gross_margin"] == pytest.approx(0.4)


def test_untagged_lines_are_null_never_zero(fs: FeatureSet) -> None:
    rows = {
        "EQ:NOCAPEX": {"capex_ttm": None},
        "EQ:NODEBT": {"total_debt": None},
        "EQ:NOCASH": {"cash": None},
        "EQ:NODA": {"da_ttm": None},
    }
    out = evaluate(fs, rows)
    assert out.loc["EQ:NOCAPEX", ["fcf", "fcf_yield"]].isna().all()  # not equal to the OCF
    assert (
        out.loc[
            "EQ:NODEBT", ["net_debt", "enterprise_value", "ev_ebitda", "roic", "debt_to_equity"]
        ]
        .isna()
        .all()
    )
    assert out.loc["EQ:NOCASH", ["net_debt", "enterprise_value", "ev_ebitda", "roic"]].isna().all()
    assert out.loc["EQ:NODA", ["ebitda", "ev_ebitda"]].isna().all()
    assert out.loc["EQ:NODA", "operating_margin"] == pytest.approx(0.15)  # D&A is not an input


def test_a_non_positive_denominator_is_null(fs: FeatureSet) -> None:
    rows = {
        "EQ:LOSS": {"ebit_ttm": -10.0, "da_ttm": 5.0},  # EBITDA -5
        "EQ:NOINT": {"interest_expense_ttm": 0.0},
        "EQ:NEGINT": {"interest_expense_ttm": -4.0},
        "EQ:NOCAP": {"market_cap_status": "NO_PRICE"},
        "EQ:ADR": {"is_adr": True},
    }
    out = evaluate(fs, rows)
    assert pd.isna(out.loc["EQ:LOSS", "ev_ebitda"]) and out.loc["EQ:LOSS", "ebitda"] == -5.0
    assert out.loc[["EQ:NOINT", "EQ:NEGINT"], "interest_cover"].isna().all()
    for iid in ("EQ:NOCAP", "EQ:ADR"):  # no market cap or not comparable with the company totals
        assert out.loc[iid, ["pb_ratio", "fcf_yield", "enterprise_value", "ev_ebitda"]].isna().all()
        assert out.loc[iid, "roe"] == pytest.approx(0.2)


def test_growth_rates_are_null_from_or_to_a_loss_and_with_no_history(fs: FeatureSet) -> None:
    rows = {
        "EQ:FROMLOSS": {"eps_diluted_ttm_3y_ago": -1.0, "eps_diluted_ttm_5y_ago": 0.0},
        "EQ:TOLOSS": {"eps_diluted_ttm": -2.0},
        "EQ:NOHIST": {"revenue_ttm_5y_ago": None, "eps_diluted_ttm_5y_ago": None},
        "EQ:ZEROREV": {"revenue_ttm_3y_ago": 0.0, "revenue_ttm_5y_ago": -5.0},
        "EQ:EPSSTALE": {"eps_stale": True},
    }
    out = evaluate(fs, rows)
    assert out.loc["EQ:FROMLOSS", ["eps_cagr_3y", "eps_cagr_5y"]].isna().all()
    assert out.loc["EQ:TOLOSS", ["eps_cagr_3y", "eps_cagr_5y"]].isna().all()
    assert out.loc["EQ:TOLOSS", "revenue_cagr_3y"] == pytest.approx(2 ** (1 / 3) - 1)
    assert out.loc["EQ:NOHIST", ["revenue_cagr_5y", "eps_cagr_5y"]].isna().all()
    assert out.loc["EQ:NOHIST", ["revenue_cagr_3y", "eps_cagr_3y"]].notna().all()
    assert out.loc["EQ:ZEROREV", ["revenue_cagr_3y", "revenue_cagr_5y"]].isna().all()
    assert out.loc["EQ:EPSSTALE", ["eps_cagr_3y", "eps_cagr_5y"]].isna().all()


def test_no_feature_is_ever_infinite(fs: FeatureSet) -> None:
    rows = {
        "EQ:A": {},
        "EQ:ZERO": {"revenue_ttm": 0.0, "total_assets": 0.0, "stockholders_equity": 0.0},
        "EQ:TINY": {"revenue_ttm_3y_ago": 1e-300, "eps_diluted_ttm_3y_ago": 1e-300},
        "EQ:HUGE": {"revenue_ttm": 1e300, "revenue_ttm_5y_ago": 1e-300},
    }
    values = evaluate(fs, rows)[NAMES].to_numpy(dtype=float)
    assert not np.isinf(values).any()


def test_a_ratio_of_two_ttms_needs_them_to_end_on_the_same_quarter(fs: FeatureSet) -> None:
    other = pd.Timestamp("2024-12-31")
    rows = {"EQ:SKEW": {"is_ttm_as_of": other}, "EQ:NOEND": {"is_ttm_as_of": pd.NaT}}
    out = evaluate(fs, rows)
    assert out[["operating_margin", "gross_margin"]].isna().all().all()
    assert out["ebitda"].notna().all() and out["roe"].notna().all()  # no revenue in them


def test_formulas_over_several_lines_need_complete_statuses(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:BSP": {"bs_status": "PARTIAL"}, "EQ:CFP": {"cf_status": "PARTIAL"}})
    several = ["net_debt", "enterprise_value", "roic", "debt_to_equity", "ev_ebitda"]
    assert out.loc["EQ:BSP", several].isna().all()
    assert out.loc["EQ:BSP", ["roe", "roa", "pb_ratio"]].notna().all()  # one line each
    assert out.loc["EQ:CFP", ["fcf", "fcf_yield"]].isna().all() and out.loc["EQ:CFP", "roe"] > 0


def test_a_negative_enterprise_value_gives_no_multiple(fs: FeatureSet) -> None:
    out = evaluate(fs, {"EQ:CASH": {"cash": 5000.0, "total_debt": 0.0}}).loc["EQ:CASH"]
    assert out["enterprise_value"] == -4000.0 and pd.isna(out["ev_ebitda"])


def test_cash_op_profitability_is_ebit_less_the_accruals_over_assets(fs: FeatureSet) -> None:
    rows = {
        "EQ:A": {},  # (150 - (100 - 200)) / 1000
        "EQ:ACCRUAL": {"ocf_ttm": 40.0},  # earnings far above cash: (150 - (100 - 40)) / 1000
    }
    out = evaluate(fs, rows)["cash_op_profitability"]
    assert out["EQ:A"] == pytest.approx(0.25) and out["EQ:ACCRUAL"] == pytest.approx(0.09)


def test_cash_op_profitability_is_null_for_a_bank_a_stale_group_or_a_skewed_quarter(
    fs: FeatureSet,
) -> None:
    other = pd.Timestamp("2024-12-31")
    rows = {
        "EQ:BANK": {"is_status": "FINANCIAL", "ebit_ttm": None},
        "EQ:STALEBS": {"bs_status": "STALE"},
        "EQ:STALECF": {"cf_status": "STALE"},
        "EQ:CFSKEW": {"cf_as_of": other},
        "EQ:ISSKEW": {"is_ttm_as_of": other},
        "EQ:NOASSETS": {"total_assets": 0.0},
        "EQ:NOOCF": {"ocf_ttm": None},
    }
    assert evaluate(fs, rows)["cash_op_profitability"].isna().all()
    assert evaluate(fs, {"EQ:P": {"is_status": "PARTIAL"}})["cash_op_profitability"].notna().all()


def test_ev_ebit_and_the_composite_value_yield(fs: FeatureSet) -> None:
    rows = {
        "EQ:A": {},
        "EQ:LOSS": {"ebit_ttm": -10.0},  # no multiple, so no composite
        "EQ:NOCAPEX": {"capex_ttm": None},  # no fcf yield, so no composite
        "EQ:BANK": {"is_status": "FINANCIAL", "ebit_ttm": None},
    }
    out = evaluate(fs, rows)
    assert out.loc["EQ:A", "ev_ebit"] == pytest.approx(8.0)  # 1200 / 150
    assert out.loc["EQ:A", "composite_value_yield"] == pytest.approx((1 / 8 + 0.12) / 2)
    assert out.loc[["EQ:LOSS", "EQ:BANK"], ["ev_ebit", "composite_value_yield"]].isna().all().all()
    assert out.loc["EQ:NOCAPEX", "ev_ebit"] == pytest.approx(8.0)
    assert pd.isna(out.loc["EQ:NOCAPEX", "composite_value_yield"])
