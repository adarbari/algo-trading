"""The API's live quotes: the IBKR feed from the registry (the API's own client id), run on a
``SessionThread``, read-only end to end, and disabled when ``[ibkr]`` cannot be used."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.site.settings import IbkrSettings
from algotrade.services.live.quotes import DisabledFeed, FeedUnavailableError, LiveQuotes
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api import live
from algotrade_sources.framework.registry import Built
from algotrade_sources.framework.session_thread import SessionThread
from algotrade_sources.vendors.ibkr.gateway import (
    CLIENT_CALLS,
    MARKET_DATA_CALLS,
    GatewayConfig,
    IbkrMarketData,
)
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from tests.conftest import REPO_ROOT
from tests.helpers.fake_ib import FakeIB

EXPIRY = date(2026, 11, 20)
CONFIGS = FileConfigStore(REPO_ROOT / "config")


def ibkr(fake: FakeIB) -> IbkrSource:
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 4002, 18), ib_factory=lambda: fake)
    return IbkrSource(gateway)


def test_quotes_key() -> None:
    assert (
        live.quotes_key("BRK.B", EXPIRY, [400, 402.5]) == "quotes__BRK.B__2026-11-20__400.0+402.5"
    )


def test_the_feed_reads_quotes_through_the_read_only_facade_on_its_thread() -> None:
    fake = FakeIB(
        quotes={("20261120", 230.0, "C"): (5.0, 5.2), ("20261120", 230.0, "P"): (4.0, 4.1)}
    )
    source = ibkr(fake)
    feed = live.SessionQuoteFeed(SessionThread(source), IbkrSettings(market_data_type=3))
    frame = feed.quotes("AAPL", EXPIRY, [230.0])
    assert frame["bid"].tolist() == [5.0, 4.0] and feed.market_data_type == 3
    feed.quotes("AAPL", EXPIRY, [230.0])
    assert fake.calls.count("client.connect 127.0.0.1:4002 id=18") == 1  # one session, kept
    feed.close()
    assert fake.calls[-1] == "disconnect"
    assert set(source.gateway.calls) <= MARKET_DATA_CALLS | CLIENT_CALLS
    assert not {"IB.connect", "placeOrder", "reqPositions", "accountValues"} & set(fake.calls)


def test_a_gateway_that_is_down_is_unavailable() -> None:
    source = ibkr(FakeIB(connect_error=ConnectionRefusedError("refused")))
    source.probe = lambda: None  # type: ignore[method-assign]  # the port answers, the API not
    feed = live.SessionQuoteFeed(SessionThread(source), IbkrSettings())
    with pytest.raises(FeedUnavailableError) as raised:
        feed.quotes("AAPL", EXPIRY, [230.0])
    assert raised.value.status == "UNAVAILABLE" and "refused" in raised.value.detail
    feed.close()


def test_without_the_gateway_settings_the_feed_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ALGOTRADE_IBKR_HOST", "ALGOTRADE_IBKR_PORT", "ALGOTRADE_IBKR_CLIENT_ID",
                 "ALGOTRADE_IBKR_API_CLIENT_ID"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    feed, options = live.live_feed(CONFIGS)
    assert isinstance(feed, DisabledFeed) and "is not set" in feed.reason
    assert options.live_cache_s == 60
    quotes = live.open_live("memory://", CONFIGS)
    assert isinstance(quotes.feed, DisabledFeed)
    quotes.close()
    assert isinstance(live.no_live().feed, DisabledFeed)


def test_with_the_gateway_settings_the_feed_is_the_registry_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: dict[str, Any] = {}

    def build_sources(settings: Any, env: Any, names: list[str]) -> Built:
        built["client_id"] = env("ALGOTRADE_IBKR_CLIENT_ID")
        return Built(sources={"ibkr": ibkr(FakeIB())})

    monkeypatch.setenv("ALGOTRADE_IBKR_CLIENT_ID", "17")
    monkeypatch.delenv("ALGOTRADE_IBKR_API_CLIENT_ID", raising=False)
    monkeypatch.setattr(live, "build_sources", build_sources)
    quotes = live.open_live("memory://", CONFIGS)
    assert isinstance(quotes, LiveQuotes) and isinstance(quotes.feed, live.SessionQuoteFeed)
    assert built["client_id"] == "18"  # the API's own session id, never ingestion's
    quotes.close()
