from datetime import date

import pytest

from algotrade.core.errors import ConfigurationError
from algotrade.core.feature_view import FeatureView
from algotrade.strategies.screeners import SCREENERS, Decision, create_screener
from algotrade.strategies.screeners.short_premium_liquidity import ShortPremiumLiquidity

ROWS = {
    "EQ:GOOD": {"liq_status": "OK", "put_tier": "A", "call_tier": "C", "short_put_ok": True},
    "EQ:THIN": {"liq_status": "OK", "put_tier": "C", "call_tier": "D", "short_put_ok": False},
    "EQ:NONE": {"liq_status": "NO_CHAIN"},
    "EQ:ERR": {"liq_status": "FETCH_ERROR: timeout"},
    "EQ:MISSING": {},
}


def test_short_premium_liquidity_decisions() -> None:
    rows = {
        r.instrument_id: r
        for r in ShortPremiumLiquidity().screen(FeatureView(date(2026, 10, 2), ROWS))
    }
    assert rows["EQ:GOOD"].decision is Decision.QUALIFIED
    assert rows["EQ:GOOD"].score == 3.0
    assert rows["EQ:GOOD"].reasons == ("put tier A", "call tier C")
    assert rows["EQ:THIN"].decision is Decision.LIQUIDITY_RISK
    assert rows["EQ:NONE"].decision is Decision.REJECT
    assert rows["EQ:ERR"].decision is Decision.UNKNOWN  # fail closed
    assert rows["EQ:MISSING"].reasons == ("no liquidity data",)


def test_registry() -> None:
    assert "short_premium_liquidity" in SCREENERS
    assert isinstance(create_screener("short_premium_liquidity"), ShortPremiumLiquidity)
    with pytest.raises(ConfigurationError):
        create_screener("nope")
