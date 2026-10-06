"""``Market`` (ADR 0047): the US market for the session, identified by its ``MKT:`` entity id."""

from algotrade.services.read.market.market import Market, load_market
from tests.unit.services.read.instruments.conftest import D1, context, store_with


def test_the_us_market_for_the_session() -> None:
    assert load_market(context(store_with())) == Market(D1, "MKT:US")
