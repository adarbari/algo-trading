"""The eight technical-analysis site presets (``docs/data/technical.md`` "Presets": breakout,
pullback, support reversal, exhaustion, trend continuation, range breakout, failed breakout,
oversold reversal): each resolves and validates against the catalogue, opens with the site's
base tradeability gates, and on a row built to satisfy every criterion is QUALIFIED while a
miss on a hard setup criterion (or a missing value) is a REJECT."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen
from algotrade.strategies.screeners.rules.criteria import Criterion
from tests.conftest import REPO_ROOT

DAY = date(2022, 11, 23)
STORE = FileConfigStore(REPO_ROOT / "config")
PRESETS = (
    "breakout",
    "pullback",
    "support_reversal",
    "exhaustion",
    "trend_continuation",
    "range_breakout",
    "failed_breakout",
    "oversold_reversal",
)
BASE = ("security_type", "status", "price", "adv")


PASSING: dict[str, Callable[[Any], Any]] = {  # op -> a value satisfying it with room to spare
    "eq": lambda v: v,
    "ne": lambda v: "OTHER",
    "in": lambda v: v[0],
    "between": lambda v: (v[0] + v[1]) / 2,
    "gt": lambda v: v + 1,
    "gte": lambda v: v + 1,
    "lt": lambda v: v - 1,
    "lte": lambda v: v - 1,
}


def _passing(criterion: Criterion) -> Any:
    return PASSING[criterion.rule.op](criterion.rule.value)


@pytest.mark.parametrize("preset", PRESETS)
def test_preset_is_a_gated_rule_screen_with_a_setup(preset: str) -> None:
    config = resolve_config(STORE, preset, UserContext("site"))
    spec = config.screen_spec
    assert config.config.impl == "rules"
    assert (
        tuple(c.id for c in spec.criteria)[: len(BASE)] == BASE
    )  # who is screened and tradeable, first
    setup = [c for c in spec.criteria if c.id not in BASE]
    assert len(setup) >= 5 and any(c.mode.gating for c in setup)
    assert spec.columns  # the row shows the numbers behind the decision


@pytest.mark.parametrize("preset", PRESETS)
def test_a_row_meeting_every_criterion_qualifies_and_a_miss_rejects(preset: str) -> None:
    spec = resolve_config(STORE, preset, UserContext("site")).screen_spec
    good = {c.rule.field: _passing(c) for c in spec.criteria}
    hard = next(c for c in spec.criteria if c.id not in BASE and c.mode.value == "hard")
    broke = {**good, hard.rule.field: None}
    view = FeatureView(DAY, {"EQ:GOOD": good, "EQ:MISSING": broke, "EQ:EMPTY": {}})
    rows = {r.instrument_id: r for r in evaluate_screen(spec, view).rows}
    assert rows["EQ:GOOD"].decision is Decision.QUALIFIED
    assert rows["EQ:MISSING"].decision is Decision.REJECT  # missing data never passes
    assert rows["EQ:EMPTY"].decision is Decision.REJECT
