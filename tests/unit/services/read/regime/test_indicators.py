"""``services/read/regime/indicators.py`` over the shipped config: every card has a rule in code
whose site threshold lies inside the card's display range, so the meter can mark it; a
switched card's sources are marked by the source stored for the session."""

from dataclasses import replace
from pathlib import Path

from algotrade.config.site.regime.cards import load_cards
from algotrade.core.model.instruments import market_id
from algotrade.features.rollups.market import indicators as rules
from algotrade.features.rollups.market import trend
from algotrade.services.features import catalogue
from algotrade.services.read.regime.indicators import RiskDirection, load_indicators
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import write_rows
from tests.unit.services.read.instruments.conftest import D1, context, store_with

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


def test_the_sessions_stored_source_marks_the_active_one() -> None:
    def index_fed(writer: StoreWriter) -> None:
        row = {"instrument_id": market_id("US"), "spx_source": "index"}
        write_rows(writer, trend.GROUP.table, D1, [row])

    ctx = replace(context(store_with(index_fed)), configs=CONFIG, features=catalogue(CONFIG))
    spx = next(i for i in load_indicators(ctx) if i.key == "spx_trend_200d")
    assert {s.input: s.active for s in spx.sources} == {
        "bars/1d": False, "instruments/symbol_ids": False, "series:SPX": True,
    }  # fmt: skip
    vix = next(i for i in load_indicators(ctx) if i.key == "vix_term")
    assert all(s.active for s in vix.sources)  # no switch: always the source
