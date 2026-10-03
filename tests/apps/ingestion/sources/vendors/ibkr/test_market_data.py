"""``IbkrSource``: a session source whose answers are saved as JSON and replayed by
``normalize`` into frames, one request kind per key."""

import json
from datetime import date

import pytest

from algotrade_ingestion.sources.framework.base import (
    FetchRequest,
    SessionSource,
    Source,
    opened,
)
from algotrade_ingestion.sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_ingestion.sources.vendors.ibkr.market_data import (
    IbkrSource,
    option_key,
    parse_key,
)
from tests.helpers.fake_ib import FakeIB

SESSION = date(2026, 10, 2)


def source(fake: FakeIB, sessions: int = 2) -> IbkrSource:
    gateway = IbkrMarketData(GatewayConfig("127.0.0.1", 4002, 1), ib_factory=lambda: fake)
    return IbkrSource(gateway, sessions)


def fake() -> FakeIB:
    bars = [(date(2026, 10, d), 10.0, 11.0, 9.0, 10.5, 1e6) for d in (1, 2)]
    return FakeIB(
        bars={"AAPL": bars},
        iv={"AAPL": bars},
        dividends={"AAPL": (1.0, 250.0)},
        expirations=["20261120", "20261218"],
        strikes=[230.0, 235.0],
        quotes={("20261120", 230.0, "C"): (5.0, 5.2)},
    )


def test_is_a_session_source_opened_and_always_closed() -> None:
    ib = fake()
    src = source(ib)
    assert isinstance(src, Source) and isinstance(src, SessionSource)
    with pytest.raises(RuntimeError), opened(src):
        assert "client.isReady" in ib.calls
        raise RuntimeError("boom")
    assert ib.calls[-1] == "disconnect"


def test_every_kind_round_trips_through_raw_json() -> None:
    ib = fake()
    src = source(ib)
    src.open()
    keys = {
        "bars/AAPL": "bars",
        "iv/AAPL": "iv",
        "div/AAPL": "div",
        option_key("AAPL", date(2026, 11, 20), "C", 230.0): "option",
    }
    for key, kind in keys.items():
        request = FetchRequest(key, "EQ:AAPL", SESSION)
        payload = src.fetch(request)
        assert payload is not None and json.loads(payload)["session"] == "2026-10-02"
        normalized = src.normalize(request, payload)
        assert normalized is not None and normalized.tables == {}
        assert not normalized.parsed[kind].empty, key
    bars = src.normalize(
        FetchRequest("bars/AAPL"), src.fetch(FetchRequest("bars/AAPL", None, SESSION)) or b""
    )
    assert bars is not None and list(bars.parsed["bars"]["date"]) == [date(2026, 10, 1), SESSION]
    request = FetchRequest("option_params/AAPL", "EQ:AAPL", SESSION)
    params = src.normalize(request, src.fetch(request) or b"")
    assert params is not None
    assert list(params.parsed["expirations"]["expiration"]) == [
        date(2026, 11, 20),
        date(2026, 12, 18),
    ]
    assert list(params.parsed["strikes"]["strike"]) == [230.0, 235.0]


def test_probe_reports_an_unreachable_gateway() -> None:
    src = IbkrSource(IbkrMarketData(GatewayConfig("127.0.0.1", 1, 1)))
    assert (src.probe() or "").startswith("IB Gateway not reachable on 127.0.0.1:1")


@pytest.mark.parametrize("key", ["orders/AAPL", "bars", "option/AAPL/2026-11-20", "x/Y"])
def test_unknown_keys_are_rejected(key: str) -> None:
    with pytest.raises(ValueError, match="unknown IBKR request key"):
        parse_key(key)
