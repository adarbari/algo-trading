"""The B4 characteristic sorts (options-setups build S4): one shape, one preset each.
Every sort screens the same base universe, asks only that its signal exists (a missing value
never passes) and ranks by it; the vol-of-vol sort joins when F7 stores the option history."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen
from tests.conftest import REPO_ROOT

DAY = date(2026, 10, 30)
STORE = FileConfigStore(REPO_ROOT / "config")
# preset -> (signal field, ranked highest first)
SORTS = {
    "cash_op_profitability": ("feature.cash_op_profitability", True),
    "distress_ohlson": ("rollup.mispricing@v1.ohlson_o", False),
    "cash_to_assets_high": ("feature.cash_to_assets", True),
}


def _spec(preset: str) -> Any:
    return resolve_config(STORE, preset, UserContext("site")).screen_spec


def _gates(preset: str, signal: str) -> set[tuple[str, str, Any]]:
    return {
        (c.rule.field, c.rule.op, repr(c.rule.value))
        for c in _spec(preset).criteria
        if c.rule.field != signal
    }


@pytest.mark.parametrize("preset", SORTS)
def test_a_sort_has_the_shared_shape(preset: str) -> None:
    signal, descending = SORTS[preset]
    spec = _spec(preset)
    own = [c.rule for c in spec.criteria if c.rule.field == signal]
    assert [r.op for r in own] == ["not_null"]
    assert spec.tie_break == signal and spec.tie_break_descending is descending
    assert _gates(preset, signal) == _gates(
        "cash_op_profitability", SORTS["cash_op_profitability"][0]
    )


def test_cash_to_assets_high_ranks_the_most_cash_first_and_never_passes_a_missing_value() -> None:
    field = "feature.cash_to_assets"

    def row(v: float | None) -> dict[str, Any]:
        r: dict[str, Any] = {
            "instrument.security_type": "COMMON_STOCK",
            "instrument.status": "ACTIVE",
            "rollup.price_stats@v2.close": 40.0,
            "rollup.price_stats@v2.adv_usd_20d": 6e7,
        }
        if v is not None:
            r[field] = v
        return r

    view = FeatureView(
        DAY, {"EQ:A": row(0.1), "EQ:B": row(0.6), "EQ:C": row(0.3), "EQ:N": row(None)}
    )
    rows = evaluate_screen(_spec("cash_to_assets_high"), view).rows
    assert [r.instrument_id for r in rows if r.decision is Decision.QUALIFIED] == [
        "EQ:B",
        "EQ:C",
        "EQ:A",
    ]
    assert {r.instrument_id: r.decision for r in rows}["EQ:N"] is Decision.REJECT
