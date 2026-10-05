"""``etf_top_holdings``: the explore answer behind GET /instruments/{id}/holdings."""

from datetime import date

import pytest

from algotrade.config.user import UserContext
from algotrade.services.explore.funds.holdings import etf_top_holdings
from algotrade.services.explore.store import NotFoundError, ReadStore, store_over
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import holdings_rows, stamped

D1, D2 = date(2026, 9, 29), date(2026, 10, 2)
LINES: list[tuple[str | None, str, float]] = [
    ("AAA", "AAA Corp", 0.4),
    ("CAT", "Caterpillar", 0.3),
    (None, "US Dollar", 0.2),
    ("ZZZ", "Zeta", 0.1),
]


def reference(symbols: dict[str, str]) -> list[dict[str, object]]:
    return [
        {"instrument_id": f"EQ:{s}", "symbol": s, "asset_class": "EQ", "security_type": kind,
         "multiplier": 1.0, "status": "ACTIVE"}
        for s, kind in symbols.items()
    ]  # fmt: skip


@pytest.fixture
def store() -> ReadStore:
    writer = StoreWriter(MemoryBackend())
    kinds = {"FUND": "ETF", "EMPTY": "ETF", "NOTE": "ETN", "AAA": "COMMON_STOCK"}
    writer.write_table("instruments/reference", D2, "ref", stamped(reference(kinds), D2, "ref"))
    first = holdings_rows("EQ:FUND", date(2026, 9, 28), LINES[:2])
    writer.write_table("holdings/etf", D1, "h1", stamped(first, D1, "h1"))
    latest = holdings_rows("EQ:FUND", date(2026, 10, 1), LINES, total=500, linked={"AAA": "EQ:AAA"})
    writer.write_table(
        "holdings/etf", D2, "h2", stamped(latest, D2, "h2", source="ishares_holdings")
    )
    return store_over(writer._backend, MemoryConfigStore({}), UserContext("local"))


def test_the_top_holdings_with_links_total_date_and_source(store: ReadStore) -> None:
    result = etf_top_holdings(store, "FUND", top=3)
    assert (result.instrument_id, result.is_etf, result.as_of) == (
        "EQ:FUND",
        True,
        date(2026, 10, 1),
    )
    assert (result.source, result.total) == ("ishares_holdings", 500)
    assert [(h.rank, h.symbol, h.instrument_id, h.weight) for h in result.items] == [
        (1, "AAA", "EQ:AAA", 0.4),
        (2, "CAT", None, 0.3),  # printed with a ticker the universe does not have
        (3, None, None, 0.2),  # cash: name only
    ]


def test_a_key_may_be_a_ticker_or_an_id_and_top_larger_than_stored_returns_all(
    store: ReadStore,
) -> None:
    assert etf_top_holdings(store, "EQ:FUND", top=50) == etf_top_holdings(store, "fund", top=50)
    assert len(etf_top_holdings(store, "FUND", top=50).items) == 4


def test_a_date_before_the_latest_read_gets_the_earlier_one(store: ReadStore) -> None:
    result = etf_top_holdings(store, "FUND", top=10, on=date(2026, 10, 1))
    assert result.as_of == date(2026, 9, 28) and result.total == 2


def test_an_etf_without_holdings_and_other_security_types_are_empty_not_errors(
    store: ReadStore,
) -> None:
    for key, etf in (("EMPTY", True), ("NOTE", False), ("AAA", False)):
        result = etf_top_holdings(store, key)
        assert (result.is_etf, result.items, result.total, result.as_of) == (etf, [], 0, None)


def test_an_unknown_instrument_is_not_found(store: ReadStore) -> None:
    with pytest.raises(NotFoundError):
        etf_top_holdings(store, "NOPE")
