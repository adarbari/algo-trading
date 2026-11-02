"""``total_vol_high`` (options-setups build S2): the total-volatility twin of ``ivol_high``, on the
same base gates so the two compare on one universe; a missing hv60 never passes; ranked by hv60,
the most volatile first."""

from datetime import date
from typing import Any

from algotrade.config.user import UserContext
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen
from tests.conftest import REPO_ROOT

DAY = date(2026, 10, 30)
STORE = FileConfigStore(REPO_ROOT / "config")
HV60 = "rollup.vol_stats@v1.hv60"
IVOL = "rollup.factor_betas@v1.ivol_252d"


def _spec(preset: str) -> Any:
    return resolve_config(STORE, preset, UserContext("site")).screen_spec


def _gates(preset: str, signal: str) -> set[tuple[str, str, Any]]:
    return {
        (c.rule.field, c.rule.op, repr(c.rule.value))
        for c in _spec(preset).criteria
        if c.rule.field != signal
    }


def _base(hv60: float | None = 0.4) -> dict[str, Any]:
    row: dict[str, Any] = {
        "instrument.security_type": "COMMON_STOCK",
        "instrument.status": "ACTIVE",
        "rollup.price_stats@v2.close": 40.0,
        "rollup.price_stats@v2.adv_usd_20d": 2e7,
    }
    if hv60 is not None:
        row[HV60] = hv60
    return row


def test_total_vol_high_screens_the_same_universe_as_ivol_high() -> None:
    assert _gates("total_vol_high", HV60) == _gates("ivol_high", IVOL)


def test_total_vol_high_ranks_the_most_volatile_first_and_never_passes_a_missing_hv60() -> None:
    spec = _spec("total_vol_high")
    assert spec.tie_break == HV60 and spec.tie_break_descending is True
    vols = {"EQ:A": 0.3, "EQ:B": 0.9, "EQ:C": 0.5}
    view = FeatureView(
        DAY,
        {
            **{i: _base(v) for i, v in vols.items()},
            "EQ:NOHV": _base(None),
            "EQ:ETF": {**_base(), "instrument.security_type": "ETF"},
        },
    )
    rows = evaluate_screen(spec, view).rows
    got = {r.instrument_id: r.decision for r in rows}
    assert got["EQ:NOHV"] is got["EQ:ETF"] is Decision.REJECT
    qualified = [r.instrument_id for r in rows if r.decision is Decision.QUALIFIED]
    assert qualified == ["EQ:B", "EQ:C", "EQ:A"]
