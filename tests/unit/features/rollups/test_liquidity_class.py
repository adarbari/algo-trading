"""``liquidity_class@v1``: each threshold decides, the worse option tier counts, unknown
inputs give UNKNOWN only when they could change the class, and the rule hash."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups import liquidity_class as lc
from algotrade.features.rollups.liquidity_class import LiquidityClassParams
from tests.rollup_helpers import END

STATS = {  # id: (adv_usd_20d, close)
    "EQ:BIG": (500e6, 150.0),
    "EQ:PUTONLY": (500e6, 150.0),
    "EQ:MID": (20e6, 30.0),
    "EQ:PENNY": (500e6, 2.0),
    "EQ:NOOPT": (500e6, 150.0),
    "EQ:FAILED": (500e6, 150.0),
    "EQ:FAILEDSMALL": (1e6, 150.0),
    "EQ:NOADV": (np.nan, 150.0),
}
OPTIONS = {  # id: (liq_status, put_tier, call_tier, chain_oi, chain_volume)
    "EQ:BIG": ("OK", "A", "A", 900_000, 90_000),
    "EQ:PUTONLY": ("OK", "A", "C", 900_000, 90_000),
    "EQ:MID": ("OK", "B", "A", 20_000, 100),
    "EQ:PENNY": ("OK", "A", "A", 900_000, 90_000),
    "EQ:FAILED": ("FETCH_ERROR", "D", "D", None, None),
    "EQ:FAILEDSMALL": ("FETCH_ERROR", "D", "D", None, None),
    "EQ:NOADV": ("OK", "A", "A", 900_000, 90_000),
}


def _inputs(with_options: bool = True) -> dict[str, pd.DataFrame | None]:
    stats = pd.DataFrame(
        {
            "instrument_id": list(STATS),
            "session_date": END,
            "adv_usd_20d": [v[0] for v in STATS.values()],
            "close": [v[1] for v in STATS.values()],
        }
    )
    options = pd.DataFrame(
        [
            {
                "instrument_id": k,
                "session_date": END,
                "liq_status": v[0],
                "put_tier": v[1],
                "call_tier": v[2],
                "chain_oi": v[3],
                "chain_volume": v[4],
            }
            for k, v in OPTIONS.items()
        ]
    )
    return {lc.PRICE_STATS: stats, lc.OPTIONS: options if with_options else None}


def test_classes_by_threshold() -> None:
    out = lc.compute(_inputs(), END, LiquidityClassParams()).set_index("instrument_id")
    assert out["liquidity_class"].to_dict() == {
        "EQ:BIG": "HIGH",
        "EQ:PUTONLY": "LOW",  # worse tier C: below MEDIUM's A,B
        "EQ:MID": "MEDIUM",
        "EQ:PENNY": "LOW",
        "EQ:NOOPT": "LOW",  # not in the chain run: no options
        "EQ:FAILED": "UNKNOWN",  # options unknown and could make it HIGH
        "EQ:FAILEDSMALL": "LOW",  # too small for MEDIUM whatever the options
        "EQ:NOADV": "UNKNOWN",
    }
    assert out.loc["EQ:PUTONLY", "option_tier"] == "C" and out.loc["EQ:NOOPT", "option_tier"] == "D"
    assert pd.isna(out.loc["EQ:FAILED", "option_tier"]) and pd.isna(
        out.loc["EQ:FAILED", "chain_oi"]
    )
    assert out["rule_hash"].nunique() == 1 and len(out["rule_hash"].iloc[0]) == 12


def test_options_requirements_can_be_dropped_and_change_the_hash() -> None:
    p = replace(
        LiquidityClassParams(),
        high_option_tiers="",
        high_min_chain_oi=0,
        high_min_chain_volume=0,
    )
    out = lc.compute(_inputs(with_options=False), END, p).set_index("instrument_id")
    assert out.loc["EQ:NOOPT", "liquidity_class"] == "HIGH"
    assert out.loc["EQ:MID", "liquidity_class"] == "UNKNOWN"  # MEDIUM still needs options
    assert out["rule_hash"].iloc[0] != LiquidityClassParams().rule_hash


def test_params_are_validated() -> None:
    with pytest.raises(ValueError, match="unknown tiers"):
        LiquidityClassParams(high_option_tiers="A,Z")
    with pytest.raises(ValueError, match="high_min_adv_usd"):
        LiquidityClassParams(high_min_adv_usd=1.0)
    assert LiquidityClassParams(medium_option_tiers=" a , b ").tiers("medium") == ["A", "B"]
