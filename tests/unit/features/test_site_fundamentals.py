"""The site's fundamentals expression features that read the financials / fundamentals /
dividends groups (``config/site/features/company/fundamentals.toml``): ``ps_ratio``, ``net_margin``,
``payout_ratio``, the growth rates (``eps_growth_yoy``, ``revenue_growth_qtr_yoy``,
``eps_growth_qtr_yoy``) and ``shares_change_yoy``: values, and null on a zero or negative base,
an unknown input, a stale figure or an ADR. Split from ``test_site.py`` (at its line cap)."""

import pandas as pd
import pytest

from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import END

PRICE_STATS = "rollups/instrument/price_stats@v2"
FUNDAMENTALS = "rollups/instrument/fundamentals@v3"
FINANCIALS = "rollups/instrument/financials@v2"
DIVIDENDS = "rollups/instrument/dividends@v2"


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return site_features(FileConfigStore(REPO_ROOT / "config"))


def _fundamental_expressions(fs: FeatureSet, ids: list[str], names: list[str], **tables):  # type: ignore[no-untyped-def]
    """``names`` over one row per id; ``tables`` maps ``fin`` / ``fund`` / ``div`` to columns."""
    keys = {"fin": FINANCIALS, "fund": FUNDAMENTALS, "div": DIVIDENDS}
    stats = pd.DataFrame({"instrument_id": ids, "session_date": END, "close": 100.0})
    frames = {PRICE_STATS: stats} | {
        keys[k]: pd.DataFrame({"instrument_id": ids, "session_date": END, **cols})
        for k, cols in tables.items()
    }
    return fs.evaluate(frames, names).set_index("instrument_id")


def test_ps_ratio_is_market_cap_over_ttm_revenue(fs: FeatureSet) -> None:
    ids = ["EQ:A", "EQ:ZERO", "EQ:NOREV", "EQ:STALE", "EQ:NOCAP", "EQ:ADR"]
    fund = {"shares_outstanding": 10.0, "market_cap_status": ["OK"] * 4 + ["NO_PRICE", "OK"]}
    fin = {
        "revenue_ttm": [500.0, 0.0, None, 500.0, 500.0, 500.0],
        "financials_status": ["OK", "OK", "NO_FACTS", "STALE", "OK", "OK"],
        "is_adr": [False] * 5 + [True],
    }
    out = _fundamental_expressions(fs, ids, ["ps_ratio"], fund=fund, fin=fin)["ps_ratio"]
    assert out["EQ:A"] == pytest.approx(2.0)  # 10 shares x 100 / 500
    assert out.drop("EQ:A").isna().all()  # zero or no revenue, stale, no market cap, an ADR


def test_net_margin_is_net_income_over_revenue(fs: FeatureSet) -> None:
    ids = ["EQ:A", "EQ:LOSS", "EQ:ZERO", "EQ:NOREV", "EQ:NONI", "EQ:OLD"]
    fin = {
        "financials_status": ["OK"] * 5 + ["STALE"],
        "net_income_ttm": [50.0, -25.0, 5.0, 5.0, None, 50.0],
        "revenue_ttm": [500.0, 500.0, 0.0, None, 500.0, 500.0],
    }
    out = _fundamental_expressions(fs, ids, ["net_margin"], fin=fin)["net_margin"]
    assert out["EQ:A"] == pytest.approx(0.1) and out["EQ:LOSS"] == pytest.approx(-0.05)
    assert out[["EQ:ZERO", "EQ:NOREV", "EQ:NONI", "EQ:OLD"]].isna().all()


def test_payout_ratio_is_dividend_over_eps(fs: FeatureSet) -> None:
    ids = ["EQ:A", "EQ:OVER", "EQ:NEG", "EQ:NONPAY", "EQ:ZERO", "EQ:NOEPS", "EQ:ADR", "EQ:OLD"]
    div = {"div_ttm": [1.0, 5.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0]}
    fin = {
        "eps_diluted_ttm": [4.0, 4.0, -2.0, 4.0, 0.0, None, 4.0, 4.0],
        "eps_stale": [False] * 7 + [True],
        "is_adr": [False] * 6 + [True, False],
    }
    out = _fundamental_expressions(fs, ids, ["payout_ratio"], div=div, fin=fin)["payout_ratio"]
    assert out["EQ:A"] == pytest.approx(0.25) and out["EQ:OVER"] == pytest.approx(1.25)
    assert out["EQ:NEG"] == pytest.approx(-0.5)  # a payer with negative earnings
    assert out["EQ:NONPAY"] == 0.0
    assert out[["EQ:ZERO", "EQ:NOEPS", "EQ:ADR", "EQ:OLD"]].isna().all()


def test_eps_growth_yoy_is_null_from_a_loss(fs: FeatureSet) -> None:
    ids = ["EQ:A", "EQ:ZERO", "EQ:LOSS", "EQ:NEW", "EQ:TURN", "EQ:OLD"]
    fin = {
        "eps_diluted_ttm": [5.0, 5.0, 5.0, 5.0, -1.0, 5.0],
        "eps_diluted_ttm_year_ago": [4.0, 0.0, -1.0, None, 2.0, 4.0],
        "eps_stale": [False] * 5 + [True],
    }
    out = _fundamental_expressions(fs, ids, ["eps_growth_yoy"], fin=fin)["eps_growth_yoy"]
    assert out["EQ:A"] == pytest.approx(0.25) and out["EQ:TURN"] == pytest.approx(-1.5)
    assert out[["EQ:ZERO", "EQ:LOSS", "EQ:NEW", "EQ:OLD"]].isna().all()


def test_quarterly_growth_expressions(fs: FeatureSet) -> None:
    ids = ["EQ:A", "EQ:ZERO", "EQ:LOSS", "EQ:TURN", "EQ:NONE"]
    fin = {
        "revenue_qtr": [130.0, 130.0, 130.0, 130.0, None],
        "revenue_qtr_year_ago": [100.0, 0.0, 100.0, None, None],
        "eps_diluted_qtr": [1.5, 1.5, 1.5, -0.2, None],
        "eps_diluted_qtr_year_ago": [1.0, 0.0, -0.5, 1.0, None],
    }
    out = _fundamental_expressions(
        fs, ids, ["revenue_growth_qtr_yoy", "eps_growth_qtr_yoy"], fin=fin
    )
    assert out.loc["EQ:A", "revenue_growth_qtr_yoy"] == pytest.approx(0.3)
    assert out.loc["EQ:A", "eps_growth_qtr_yoy"] == pytest.approx(0.5)
    assert out.loc["EQ:TURN", "eps_growth_qtr_yoy"] == pytest.approx(-1.2)
    assert out["revenue_growth_qtr_yoy"][["EQ:ZERO", "EQ:TURN", "EQ:NONE"]].isna().all()
    assert out["eps_growth_qtr_yoy"][["EQ:ZERO", "EQ:LOSS", "EQ:NONE"]].isna().all()


def test_shares_change_yoy_is_negative_for_buybacks(fs: FeatureSet) -> None:
    ids = ["EQ:BUYBACK", "EQ:DILUTE", "EQ:NEW", "EQ:OLD"]
    fund = {
        "shares_outstanding": [95.0, 112.0, 100.0, 100.0],
        "shares_outstanding_year_ago": [100.0, 100.0, None, 90.0],
        "market_cap_status": ["OK", "OK", "OK", "STALE"],
    }
    out = _fundamental_expressions(fs, ids, ["shares_change_yoy"], fund=fund)["shares_change_yoy"]
    assert out["EQ:BUYBACK"] == pytest.approx(-0.05) and out["EQ:DILUTE"] == pytest.approx(0.12)
    assert out[["EQ:NEW", "EQ:OLD"]].isna().all()  # no count a year back, a stale count
