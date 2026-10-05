"""The IB Gateway facade is read-only: only market-data calls, a guarded IB object, the API
handshake instead of ``IB.connect`` (which syncs positions and accounts), paced requests."""

import asyncio
import socket
from datetime import date
from types import SimpleNamespace

import pytest
from ib_async import IB

from algotrade_sources.framework.base import SessionUnavailableError, TransientFetchError
from algotrade_sources.vendors.ibkr.gateway import (
    CLIENT_CALLS,
    MARKET_DATA_CALLS,
    GatewayConfig,
    IbkrMarketData,
    ReadOnlyViolationError,
    _detach_resubscribe,
    ib_symbol,
    refused,
    unanswered,
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


@pytest.mark.allow_localhost
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


def test_enrichment_calls_are_market_data_only_and_paced() -> None:
    """ADR 0028: contracts, the IV history and the vol snapshot use only allowlisted calls;
    order and account calls stay blocked on the same session."""
    fake = FakeIB(
        bars={"AAPL": BARS},
        iv={"AAPL": BARS},
        hv={"AAPL": BARS[-1:]},
        vols={"AAPL": (0.31, 0.25), "SPY": (0.12, float("nan"))},
    )
    gw, general, historical = gateway(fake, stream_wait_s=0.01)
    gw.connect()
    found = gw.stock_contracts(["AAPL", "SPY", "ZZZZ"])
    assert found["AAPL"] == {"conid": 1004, "primary_exchange": "NASDAQ", "sec_type": "STK",
                             "currency": "USD"}  # fmt: skip
    assert found["ZZZZ"] is None
    assert fake.calls.count("qualifyContracts") == 1  # one call for the batch
    assert general.waits == 2 + 3  # the handshake + market data type, then one per contract
    hist = gw.volatility_history("AAPL", date(2026, 10, 2), SESSION, conid=1004)
    assert hist == {"OPTION_IMPLIED_VOLATILITY": [{"date": "2026-10-02", "close": 11.0}]}
    assert historical.waits == 1 and [r["durationStr"] for r in fake.requests] == ["1 D"]
    assert [r["whatToShow"] for r in fake.requests] == ["OPTION_IMPLIED_VOLATILITY"]  # no HV
    gw.volatility_history("MSFT", date(2024, 10, 2), SESSION, conid=272093)  # no lookup
    assert fake.requests[-1]["durationStr"] == "3 Y" and fake.requests[-1]["symbol"] == "MSFT"
    vols = gw.underlying_vols({"AAPL": 1004, "SPY": None, "ZZZZ": None})
    assert vols == {
        "AAPL": {"listed": True, "iv": 0.31, "hv": 0.25},
        "SPY": {"listed": True, "iv": 0.12, "hv": None},
        "ZZZZ": {"listed": False, "iv": None, "hv": None},
    }
    assert fake.calls.count("reqMktData 104,106") == 2 and fake.calls.count("cancelMktData") == 2
    for name in ("placeOrder", "reqPositions", "accountValues", "reqAccountUpdates"):
        with pytest.raises(ReadOnlyViolationError, match=name):
            getattr(gw.ib, name)
    assert set(gw.calls) <= MARKET_DATA_CALLS | CLIENT_CALLS
    assert not set(FORBIDDEN) & set(fake.calls)


def test_vol_streams_are_cancelled_even_when_waiting_fails() -> None:
    fake = FakeIB(vols={"AAPL": (0.3, 0.2)})

    def broken(timeout: float = 0) -> bool:
        raise RuntimeError("socket closed")

    fake.waitOnUpdate = broken  # type: ignore[method-assign]
    gw, _, _ = gateway(fake)
    gw.connect()
    with pytest.raises(RuntimeError):
        gw.underlying_vols({"AAPL": None})
    assert fake.calls.count("cancelMktData") == 1


def test_option_quotes_qualify_once_per_session_then_stream_and_cancel() -> None:
    fake = FakeIB(
        quotes={("20261120", 230.0, "C"): (5.0, 5.2), ("20261120", 230.0, "P"): (4.0, 4.3)}
    )
    gw, general, historical = gateway(fake)
    gw.connect()
    rows = gw.option_quotes("AAPL", date(2026, 11, 20), [230.0, 999.0])
    assert [(r["strike"], r["right"], r["listed"]) for r in rows] == [
        (230.0, "C", True), (230.0, "P", True), (999.0, "C", False), (999.0, "P", False)
    ]  # fmt: skip
    assert rows[0] == {
        "strike": 230.0, "right": "C", "listed": True, "conid": 1004, "bid": 5.0, "ask": 5.2,
        "last": None, "close": None, "volume": None, "iv": None, "delta": None,
    }  # fmt: skip
    assert fake.calls.count("qualifyContracts") == 1 and fake.calls.count("reqMktData ") == 2
    assert fake.calls.count("cancelMktData") == 2  # every stream ends
    assert general.waits == 2 + 4 + 2 + 2  # handshake + type, 4 qualified, 2 streams + cancels
    gw.option_quotes("AAPL", date(2026, 11, 20), [230.0])  # known contracts: no lookup
    assert fake.calls.count("qualifyContracts") == 1 and fake.calls.count("reqMktData ") == 4
    assert historical.waits == 0
    assert set(gw.calls) <= MARKET_DATA_CALLS | CLIENT_CALLS
    assert not set(FORBIDDEN) & set(fake.calls)
    gw.close()
    assert gw._options == {}


def test_option_quotes_with_nothing_listed_send_no_snapshot_request() -> None:
    fake = FakeIB()
    gw, _, _ = gateway(fake)
    gw.connect()
    rows = gw.option_quotes("ZZZ", date(2026, 11, 20), [1.0])
    assert all(not r["listed"] for r in rows) and "reqMktData " not in fake.calls


def test_option_quotes_stop_waiting_after_the_stream_window() -> None:
    fake = FakeIB(quotes={("20261120", 230.0, "C"): (5.0, 5.2)})
    fake.quotes = {}  # listed (qualified below), but no quote ever arrives
    now = iter([0.0, 0.0, 5.0])
    cfg = GatewayConfig("127.0.0.1", 4002, 7, stream_wait_s=4.0)
    gw = IbkrMarketData(cfg, ib_factory=lambda: fake, clock=lambda: next(now))
    gw.connect()
    gw._options[("AAPL", date(2026, 11, 20), 230.0, "C")] = SimpleNamespace(
        conId=1, secType="OPT", lastTradeDateOrContractMonth="20261120", strike=230.0,
        right="C", symbol="AAPL",
    )  # fmt: skip
    gw._options[("AAPL", date(2026, 11, 20), 230.0, "P")] = None
    rows = gw.option_quotes("AAPL", date(2026, 11, 20), [230.0])
    assert rows[0]["listed"] and rows[0]["bid"] is None
    assert fake.calls.count("waitOnUpdate") == 1 and fake.calls.count("cancelMktData") == 1


def test_a_restored_connection_sends_no_account_request() -> None:
    """ib_async's IB re-requests the account summary on error 1102 by itself; the facade
    detaches that reaction, so a connectivity blip sends nothing outside the guard."""

    async def emit_restored(ib: IB) -> list[str]:
        sent: list[str] = []

        async def record() -> None:
            sent.append("reqAccountSummary")

        ib.reqAccountSummaryAsync = record  # type: ignore[method-assign]
        ib.errorEvent.emit(-1, 1102, "Connectivity ... restored - data maintained", None)
        await asyncio.sleep(0)
        return sent

    assert asyncio.run(emit_restored(IB())) == ["reqAccountSummary"]  # the library's default
    sealed = IB()
    _detach_resubscribe(sealed)
    assert asyncio.run(emit_restored(sealed)) == []


def history_gateway(fake: FakeIB) -> tuple[IbkrMarketData, CountingLimiter]:
    historical = CountingLimiter()
    cfg = GatewayConfig("127.0.0.1", 4002, 7, request_timeout_s=60.0)
    gw = IbkrMarketData(cfg, historical=historical, ib_factory=lambda: fake, clock=fake.clock)
    gw.connect()
    return gw, historical


@pytest.mark.parametrize(
    ("fault", "why"),
    [
        ("timeout", "no answer within the 60 s request timeout"),
        ("pacing", "IB error 162: .*pacing violation"),
        ("1100", "IB error 1100 while the request was in flight"),
    ],
)
def test_an_unanswered_history_request_is_a_transient_error_not_empty(fault: str, why: str) -> None:
    """ib_async returns [] on a timeout and on IB errors; the facade tells them apart."""
    fake = FakeIB(bars={"AAPL": BARS}, iv={"AAPL": BARS}, faults={"AAPL": [fault]})
    gw, _ = history_gateway(fake)
    with pytest.raises(TransientFetchError, match=why):
        gw.volatility_history("AAPL", date(2026, 10, 1), SESSION, conid=1004)
    assert gw.volatility_history("AAPL", date(2026, 10, 1), SESSION, conid=1004)[
        "OPTION_IMPLIED_VOLATILITY"
    ]  # the next request is answered
    assert not set(FORBIDDEN) & set(fake.calls)


def test_an_error_a_retry_cannot_fix_is_not_transient_and_not_empty() -> None:
    fake = FakeIB(iv={"AAPL": BARS}, faults={"AAPL": ["denied"]})
    gw, _ = history_gateway(fake)
    with pytest.raises(LookupError, match="No market data permissions") as raised:
        gw.volatility_history("AAPL", date(2026, 10, 1), SESSION, conid=1004)
    assert not isinstance(raised.value, TransientFetchError)


@pytest.mark.parametrize("fault", ["no-data", None])
def test_a_genuine_empty_history_is_empty(fault: str | None) -> None:
    fake = FakeIB(bars={"AAPL": BARS}, faults={"AAPL": [fault]} if fault else {})
    gw, _ = history_gateway(fake)
    assert gw.volatility_history("AAPL", date(2026, 10, 1), SESSION, conid=1004) == {
        "OPTION_IMPLIED_VOLATILITY": []
    }


def test_a_connection_flap_with_bars_is_answered() -> None:
    fake = FakeIB(iv={"AAPL": BARS}, faults={"AAPL": ["flap"]})
    gw, _ = history_gateway(fake)
    hist = gw.volatility_history("AAPL", date(2026, 10, 1), SESSION, conid=1004)
    assert len(hist["OPTION_IMPLIED_VOLATILITY"]) == 2


def test_unanswered_reads_only_this_requests_errors_and_real_failures() -> None:
    lost, pacing = (-1, 1100, "lost"), (7, 162, "pacing violation")
    assert unanswered([], 7, 0.1, 60.0) is None
    assert unanswered([(8, 162, "pacing violation")], 7, 0.1, 60.0) is None  # another request
    assert unanswered([(7, 2174, "warning"), (-1, 2104, "farm OK")], 7, 0.1, 60.0) is None
    assert unanswered([(7, 162, "HMDS query returned no data")], 7, 0.1, 60.0) is None
    assert unanswered([pacing], 7, 0.1, 60.0) == "IB error 162: pacing violation"
    assert unanswered([pacing], None, 0.1, 60.0) is not None  # request id unknown: any counts
    assert unanswered([lost], 7, 0.1, 60.0) == "IB error 1100 while the request was in flight: lost"
    assert unanswered([], 7, 59.5, 60.0) is not None and unanswered([], 7, 1.0, 0.0) is None
    assert (
        refused([(7, 200, "No security definition")], 7) == "IB error 200: No security definition"
    )
    assert refused([(8, 200, "x"), pacing, lost], 7) is None


def test_cool_down_holds_the_historical_limiter_and_close_stops_listening() -> None:
    fake = FakeIB(iv={"AAPL": BARS})
    gw, historical = history_gateway(fake)
    assert len(fake.errorEvent.handlers) == 1
    gw.cool_down(30.0)
    assert historical.held == 30.0
    fake.errorEvent.emit(-1, 1100, "lost", None)  # outside a request: not recorded
    assert gw._errors is None
    gw.close()
    assert fake.errorEvent.handlers == []


def test_the_error_listener_works_on_ib_asyncs_own_event() -> None:
    """The real ``IB.errorEvent`` (no connection): IB's errors reach the facade only while a
    history request is in flight, and closing detaches the listener."""
    raw = IB()
    gw = IbkrMarketData(GatewayConfig("127.0.0.1", 4002, 7))
    gw._listen(raw)
    seen: list[tuple[int, int, str]] = []
    gw._errors = seen
    raw.errorEvent.emit(5, 162, "pacing violation", None)
    assert seen == [(5, 162, "pacing violation")]
    gw._errors = None
    gw.close()
    raw.errorEvent.emit(5, 162, "again", None)
    assert seen == [(5, 162, "pacing violation")] and gw._events is None
