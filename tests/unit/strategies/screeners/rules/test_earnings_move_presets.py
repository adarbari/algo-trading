"""``earnings_move_rich`` and ``earnings_move_cheap`` (options-setups design S3): S&P 500 names
with a tradeable option tier whose report straddle is rich (or cheap) against the name's past
earnings moves; a missing value never passes; ranked by the ratio."""

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

DAY = date(2026, 10, 27)
STORE = FileConfigStore(REPO_ROOT / "config")
RATIO = "feature.earnings_move_ratio"


def _spec(preset: str) -> Any:
    return resolve_config(STORE, preset, UserContext("site")).screen_spec


def _base(flag: str) -> dict[str, Any]:
    return {
        "instrument.security_type": "COMMON_STOCK",
        "instrument.status": "ACTIVE",
        "instrument.in_sp500": True,
        "instrument.optionable": True,
        "rollup.price_stats@v2.close": 120.0,
        "rollup.price_stats@v2.adv_usd_20d": 2e8,
        "feature.option_tier": "A",
        f"feature.{flag}": True,
    }


@pytest.mark.parametrize(
    ("preset", "flag", "descending"),
    [
        ("earnings_move_rich", "earnings_move_rich", True),
        ("earnings_move_cheap", "earnings_move_cheap", False),
    ],
)
def test_the_screen_gates_on_sp500_option_tier_and_the_flag_and_never_passes_a_missing_value(
    preset: str, flag: str, descending: bool
) -> None:
    spec = _spec(preset)
    assert spec.tie_break == RATIO and spec.tie_break_descending is descending
    base = _base(flag)
    assert {c.rule.field for c in spec.criteria} == set(base)  # nothing else gates
    view = FeatureView(
        DAY,
        {
            "EQ:GOOD": base,
            "EQ:NOTSP": {**base, "instrument.in_sp500": False},
            "EQ:TIERC": {**base, "feature.option_tier": "C"},
            "EQ:TIERB": {**base, "feature.option_tier": "B"},
            "EQ:FLAGOFF": {**base, f"feature.{flag}": False},
            "EQ:NOFLAG": {k: v for k, v in base.items() if k != f"feature.{flag}"},
            "EQ:NOTIER": {k: v for k, v in base.items() if k != "feature.option_tier"},
        },
    )
    got = {r.instrument_id: r.decision for r in evaluate_screen(spec, view).rows}
    assert got["EQ:GOOD"] is got["EQ:TIERB"] is Decision.QUALIFIED
    for rejected in ("EQ:NOTSP", "EQ:TIERC", "EQ:FLAGOFF", "EQ:NOFLAG", "EQ:NOTIER"):
        assert got[rejected] is Decision.REJECT


def test_rich_ranks_the_highest_ratio_first_and_cheap_the_lowest_first() -> None:
    for preset, flag, ratios, first in (
        (
            "earnings_move_rich",
            "earnings_move_rich",
            {"EQ:A": 1.4, "EQ:B": 2.5, "EQ:C": 1.9},
            "EQ:B",
        ),
        (
            "earnings_move_cheap",
            "earnings_move_cheap",
            {"EQ:A": 0.7, "EQ:B": 0.4, "EQ:C": 0.6},
            "EQ:B",
        ),
    ):
        spec = _spec(preset)
        view = FeatureView(DAY, {i: {**_base(flag), RATIO: r} for i, r in ratios.items()})
        order = [r.instrument_id for r in evaluate_screen(spec, view).rows]
        assert order[0] == first
        expected = sorted(ratios, key=ratios.get, reverse=preset == "earnings_move_rich")
        assert order == expected
