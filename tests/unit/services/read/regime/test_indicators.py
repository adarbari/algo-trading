"""``services/read/regime/indicators.py`` over the shipped config: every card has a rule in code
whose site threshold lies inside the card's display range, so the meter can mark it."""

from dataclasses import replace
from pathlib import Path

from algotrade.config.site.regime.cards import load_cards
from algotrade.features.rollups.market import indicators as rules
from algotrade.services.features import catalogue
from algotrade.services.read.regime.indicators import RiskDirection, load_indicators
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.read.instruments.conftest import context, store_with

CONFIG = FileConfigStore(Path(REPO_ROOT / "config"))


def test_every_shipped_card_has_a_rule_with_its_threshold_in_range() -> None:
    ctx = replace(context(store_with()), configs=CONFIG, features=catalogue(CONFIG))
    found = {i.key: i for i in load_indicators(ctx)}
    assert set(found) == {c.key for c in rules.CARDS} == {c.key for c in load_cards(CONFIG).cards}
    for key, indicator in found.items():
        assert indicator.threshold is not None, key
        assert indicator.range.min <= indicator.threshold <= indicator.range.max, key
        assert indicator.sources, key
    assert found["curve_10y3m"].direction is RiskDirection.LOWER_IS_RISK
    assert found["vix_term"].direction is RiskDirection.HIGHER_IS_RISK
    assert found["hy_oas"].threshold == 0.05  # the primary of its two rules
