"""The IB Gateway facade is read-only: only market-data calls, a guarded IB object, the API
handshake instead of ``IB.connect`` (which syncs positions and accounts), paced requests."""

import socket
from datetime import date

import pytest

from algotrade_sources.framework.base import SessionUnavailableError
from algotrade_sources.vendors.ibkr.gateway import (
    CLIENT_CALLS,
    MARKET_DATA_CALLS,
    GatewayConfig,
    IbkrMarketData,
    ReadOnlyViolationError,
    ib_symbol,
)
from tests.helpers.fake_ib import FakeIB
from tests.helpers.ingest_fakes import CountingLimiter

SESSION = date(2026, 10, 2)
BARS = [(date(2026, 10, 1 + i), 10.0, 11.0, 9.0, 10.0 + i, 100.0) for i in range(2)]
FORBIDDEN = ("IB.connect", "placeOrder", "client.placeOrder", "reqPositions", "accountValues")


def gateway(
    fake: FakeIB, **config: object
) -> tuple[IbkrMarketData, CountingLimiter, CountingLimiter]:
    general, historical = CountingLimiter(), CountingLimiter()
    cfg = GatewayConfig("127.0.0.1", 4002, 7, **config)  # type: ignore[arg-type]
    return IbkrMarketData(cfg, general, historical, ib_factory=lambda: fake), general, historical


def test_connect_is_the_api_handshake_only_then_the_market_data_type() -> None:
    fake = FakeIB(bars={"AAPL": BARS})
    gw, general, _ = gateway(fake, market_data_type=3)
    gw.connect()
    assert fake.calls == [
        "client.connect 127.0.0.1:4002 id=7",
        "client.isReady",
        "reqMarketDataType 3",
    ]
    assert general.waits == 2
    gw.close()
    assert fake.calls[-1] == "disconnect" and gw._ib is None
    gw.close()  # closing twice is harmless


def test_refuses_to_connect_unless_read_only() -> None:
    built: list[FakeIB] = []
    cfg = GatewayConfig("127.0.0.1", 4002, 7, readonly=False)
    gw = IbkrMarketData(cfg, ib_factory=lambda: built.append(FakeIB()) or FakeIB())
    with pytest.raises(ReadOnlyViolationError, match="read-only"):
        gw.connect()
    assert built == []  # nothing was even constructed


def test_the_guard_blocks_order_and_account_calls_before_they_are_sent() -> None:
    fake = FakeIB(bars={"AAPL": BARS})
    gw, _, _ = gateway(fake)
    gw.connect()
    for name in ("placeOrder", "cancelOrder", "reqPositions", "accountValues", "connect"):
        with pytest.raises(ReadOnlyViolationError, match=name):
            getattr(gw.ib, name)
    assert not set(FORBIDDEN) & set(fake.calls)
    assert set(gw.calls) <= MARKET_DATA_CALLS | CLIENT_CALLS


def test_every_facade_method_makes_only_allowed_calls_and_is_paced() -> None:
    fake = FakeIB(
        bars={"AAPL": BARS},
        iv={"AAPL": BARS[-1:]},
        dividends={"AAPL": (1.04, 250.0)},
        expirations=["20261120"],
        strikes=[230.0, 235.0],
        quotes={("20261120", 230.0, "C"): (5.0, 5.2)},
    )
    gw, general, historical = gateway(fake)
    gw.connect()
    bars = gw.historical_bars("AAPL", SESSION, 1)
    assert bars == [
        {"date": "2026-10-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": 11.0,
         "volume": 100.0}
    ]  # fmt: skip
    assert gw.implied_volatility("AAPL", SESSION)[0]["close"] == 11.0
    assert gw.dividends("AAPL") == {
        "past12Months": 1.04, "next12Months": 1.04, "nextDate": None, "nextAmount": None,
        "close": 250.0,
    }  # fmt: skip
    params = gw.option_params("AAPL")
    assert params == [
        {"trading_class": "AAPL", "multiplier": "100", "expirations": ["20261120"],
         "strikes": [230.0, 235.0]}
    ]  # fmt: skip
    quote = gw.option_quote("AAPL", date(2026, 11, 20), 230.0, "C")
    assert quote == {"listed": True, "bid": 5.0, "ask": 5.2, "last": None, "close": None}
    assert gw.option_quote("AAPL", date(2026, 11, 20), 999.0, "P") == {"listed": False}
    assert historical.waits == 2  # bars + implied vol: the historical-data pacing
    sent = [c for c in gw.calls if c in MARKET_DATA_CALLS and c != "waitOnUpdate"]
    assert general.waits == len(sent) + 1  # every message, and the handshake
    assert set(gw.calls) <= MARKET_DATA_CALLS | CLIENT_CALLS
    assert not set(FORBIDDEN) & set(fake.calls)
    first = fake.requests[0]
    assert first["whatToShow"] == "TRADES" and first["durationStr"] == "1 Y"
    assert first["endDateTime"] == "20261002 23:59:59 US/Eastern" and first["useRTH"] is True


def test_dividends_stop_waiting_after_the_stream_window() -> None:
    fake = FakeIB(dividends={"KO": (None, 70.0)})
    now = iter([0.0, 0.0, 5.0])
    cfg = GatewayConfig("127.0.0.1", 4002, 7, stream_wait_s=4.0)
    gw = IbkrMarketData(cfg, ib_factory=lambda: fake, clock=lambda: next(now))
    gw.connect()
    out = gw.dividends("KO")
    assert out["past12Months"] is None and out["close"] == 70.0
    assert fake.calls.count("cancelMktData") == 1  # the subscription always ends


def test_unknown_symbol_and_closed_session_fail_clearly() -> None:
    fake = FakeIB(dividends={"AAPL": (None, 1.0)})
    gw, _, _ = gateway(fake)
    with pytest.raises(SessionUnavailableError, match="not open"):
        gw.historical_bars("AAPL", SESSION, 5)
    gw.connect()
    assert gw.historical_bars("AAPL", SESSION, 260) == []  # IB had nothing
    assert fake.requests[-1]["durationStr"] == "2 Y"  # 260 sessions need two years
    with pytest.raises(LookupError, match="ZZZZ"):
        gw.historical_bars("ZZZZ", SESSION, 5)


@pytest.mark.parametrize("error", [ConnectionRefusedError("refused"), TimeoutError("slow")])
def test_an_unreachable_gateway_is_a_session_error(error: Exception) -> None:
    gw, _, _ = gateway(FakeIB(connect_error=error))
    with pytest.raises(SessionUnavailableError, match=r"not reachable on 127\.0\.0\.1:4002"):
        gw.connect()


def test_a_gateway_whose_api_is_not_ready_is_a_session_error() -> None:
    fake = FakeIB()
    fake.client.ready = False
    gw, _, _ = gateway(fake)
    with pytest.raises(SessionUnavailableError, match="not ready"):
        gw.connect()


def test_reachable_checks_the_port_without_the_api() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert IbkrMarketData(GatewayConfig("127.0.0.1", port, 1)).reachable() is None
    reason = IbkrMarketData(GatewayConfig("127.0.0.1", port, 1)).reachable()
    assert reason is not None and reason.startswith(f"IB Gateway not reachable on 127.0.0.1:{port}")


def test_ib_symbols() -> None:
    assert ib_symbol("BRK.B") == "BRK B" and ib_symbol("AAPL") == "AAPL"
