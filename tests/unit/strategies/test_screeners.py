"""The screener registry, and the ``short_premium_liquidity`` rule preset (ADR 0088 S5): the
decisions the deleted Python screener gave a pass, a one-sided pass and a miss, now by rules."""

from datetime import date

import pytest

from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import SCREENERS, Decision, create_screener
from algotrade.strategies.screeners.rules import evaluate_screen
from tests.conftest import REPO_ROOT

G = "rollup.option_liquidity@v1."
ROWS = {
    "EQ:PUT": {
        G + "liq_status": "OK",
        G + "short_put_ok": True,
        G + "short_call_ok": False,
        G + "put_tier": "A",
    },
    "EQ:CALL": {
        G + "liq_status": "OK",
        G + "short_put_ok": False,
        G + "short_call_ok": True,
        G + "call_tier": "B",
    },
    "EQ:THIN": {
        G + "liq_status": "OK",
        G + "short_put_ok": False,
        G + "short_call_ok": False,
        G + "put_tier": "C",
    },
    "EQ:NONE": {G + "liq_status": "NO_CHAIN"},
    "EQ:ERR": {G + "liq_status": "FETCH_ERROR: timeout"},
    "EQ:STALE": {G + "liq_status": "STALE_DATA: chain is for 2026-10-01", G + "short_put_ok": True},
    "EQ:MISSING": {},
}


def test_short_premium_liquidity_preset_passes_a_tradeable_put_or_call() -> None:
    config = resolve_config(FileConfigStore(REPO_ROOT / "config"), "short_premium_liquidity",
                            UserContext(SITE_USER))  # fmt: skip
    rows = {
        r.instrument_id: r
        for r in evaluate_screen(config.screen_spec, FeatureView(date(2026, 10, 2), ROWS)).rows
    }
    picked = {i for i, r in rows.items() if r.decision is Decision.QUALIFIED}
    assert picked == {"EQ:PUT", "EQ:CALL"}
    assert all(rows[i].decision is Decision.REJECT for i in set(ROWS) - picked)  # fail closed
    assert dict(rows["EQ:PUT"].columns)["put_tier"] == "A"  # the legacy export's column name
    assert config.config.exports == ("legacy_liquidity_csv",)


def test_registry() -> None:
    assert "short_premium_liquidity" not in SCREENERS  # a rule preset now, not Python
    with pytest.raises(ConfigurationError):
        create_screener("short_premium_liquidity")
