"""A store and configs for the on-request screen runs: a rule screen ``big_liquid`` (a site
preset) over two instruments with their features for ``DAY``, and a strategy that is no screener."""

from datetime import date, timedelta
from typing import Any

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import reference_rows, stamped, universe_rows

DAY = date(2026, 10, 2)
SNAPSHOT = DAY - timedelta(days=2)
LIQ = "rollup.option_liquidity@v1"
SCREEN: dict[str, Any] = {
    "id": "big_liquid",
    "kind": "screener",
    "impl": "rules",
    "version": 1,
    "selection": "active",
    "screening": {"min_coverage": 0.5},
    "criteria": {"price": {"field": f"{LIQ}.underlying_price", "op": "gt", "value": 50}},
}
ACTIVE = {
    "name": "active",
    "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
}


def seeded_backend() -> MemoryBackend:
    store = MemoryBackend()
    writer = StoreWriter(store)
    universe = universe_rows(["AAA", "BBB"], last_verified="2026-10-01")
    writer.write_table("universe", SNAPSHOT, "u1", stamped(universe, DAY, "u1"))
    writer.write_table(
        "instruments/reference", SNAPSHOT, "u1", stamped(reference_rows(universe), DAY, "u1")
    )
    features = [
        {"instrument_id": "EQ:AAA", "underlying_price": 100.0},
        {"instrument_id": "EQ:BBB", "underlying_price": 40.0},
    ]
    writer.write_table(
        "rollups/instrument/option_liquidity@v1", DAY, "f1", stamped(features, DAY, "f1")
    )
    return store


def site_configs(extra: dict[tuple[str, str, str], Any] | None = None) -> MemoryConfigStore:
    return MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE,
            ("site", "strategies", "big_liquid"): SCREEN,
            ("site", "strategies", "sma_trend"): {
                "id": "sma_trend",
                "kind": "strategy",
                "impl": "sma_trend",
                "selection": "active",
            },
            **(extra or {}),
        }
    )
