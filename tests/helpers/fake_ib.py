"""A fake ``ib_async.IB`` for IBKR tests: canned market data, every call recorded, no network.

It also has order and account methods (``placeOrder``, ``reqPositions``, ...) that record a
call if ever reached: tests assert they never are (the facade's guard blocks them first).

Historical requests can be scripted to go wrong like ``ib_async`` does (``faults``: per
symbol, one fault per request in order): every fault returns an EMPTY bar list, as
``ib_async`` does with ``RaiseRequestErrors`` off. ``"timeout"`` takes the request timeout
(on ``clock``, which the facade reads); ``"pacing"`` emits error 162 pacing violation for the
request, ``"no-data"`` IB's error 162 "query returned no data", ``"denied"`` error 162 "No
market data permissions" (a retry cannot fix it), ``"1100"`` the connectivity
loss (request id -1, then 1102 restored); ``"flap"`` the same loss but the bars still come.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import Any

Bar = tuple[date, float, float, float, float, float]  # date, open, high, low, close, volume
PACING = "Historical Market Data Service error message:Historical data request pacing violation"
NO_DATA = "Historical Market Data Service error message:HMDS query returned no data: X@SMART"
DENIED = "Historical Market Data Service error message:No market data permissions for X"
ERROR_162 = {"pacing": PACING, "no-data": NO_DATA, "denied": DENIED}


class FakeEvent:
    """``ib_async``'s ``Event`` as far as the facade uses it: ``+=``, ``-=``, ``emit``."""

    def __init__(self) -> None:
        self.handlers: list[Callable[..., Any]] = []

    def __iadd__(self, handler: Callable[..., Any]) -> "FakeEvent":
        self.handlers.append(handler)
        return self

    def __isub__(self, handler: Callable[..., Any]) -> "FakeEvent":
        self.handlers = [h for h in self.handlers if h != handler]
        return self

    def emit(self, *args: Any) -> None:
        for handler in list(self.handlers):
            handler(*args)


class FakeBars(list[Any]):
    """``ib_async.BarDataList``: a list of bars that knows its request id."""

    reqId: int = 0  # noqa: N815


@dataclass
class FakeClient:
    calls: list[str]
    fail: Exception | None = None
    ready: bool = True

    def connect(self, host: str, port: int, clientId: int, timeout: float | None = 2.0) -> None:  # noqa: N803
        self.calls.append(f"client.connect {host}:{port} id={clientId}")
        if self.fail is not None:
            raise self.fail

    def isReady(self) -> bool:  # noqa: N802
        self.calls.append("client.isReady")
        return self.ready

    def placeOrder(self, *args: Any) -> None:  # noqa: N802
        self.calls.append("client.placeOrder")


@dataclass
class FakeIB:
    """Canned answers by symbol: ``bars`` / ``iv`` / ``hv`` (daily bars), ``dividends`` (past
    12 months, close), ``vols`` (the streamed implied and historical vol), ``expirations`` /
    ``strikes`` and ``quotes`` ((expiry, strike, right) -> (bid, ask)). Unknown symbols do not
    qualify."""

    bars: Mapping[str, Sequence[Bar]] = field(default_factory=dict)
    iv: Mapping[str, Sequence[Bar]] = field(default_factory=dict)
    dividends: Mapping[str, tuple[float | None, float]] = field(default_factory=dict)
    expirations: Sequence[str] = ()
    strikes: Sequence[float] = ()
    quotes: Mapping[tuple[str, float, str], tuple[float, float]] = field(default_factory=dict)
    hv: Mapping[str, Sequence[Bar]] = field(default_factory=dict)  # HISTORICAL_VOLATILITY
    vols: Mapping[str, tuple[float, float]] = field(default_factory=dict)  # ticks 106, 104
    connect_error: Exception | None = None
    faults: Mapping[str, list[str]] = field(default_factory=dict)  # symbol -> faults, in order
    calls: list[str] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.client = FakeClient(self.calls, self.connect_error)
        self._streams: list[SimpleNamespace] = []
        self.errorEvent = FakeEvent()
        self.skew = 0.0  # seconds a scripted timeout added to ``clock``

    def clock(self) -> float:
        """The monotonic clock plus the time scripted timeouts took (the facade's clock)."""
        return time.monotonic() + self.skew

    # ---------------------------------------------------------------- market data

    def reqMarketDataType(self, kind: int) -> None:  # noqa: N802
        self.calls.append(f"reqMarketDataType {kind}")

    def qualifyContracts(self, *contracts: Any) -> list[Any]:  # noqa: N802
        self.calls.append("qualifyContracts")
        out = []
        for c in contracts:
            known = c.symbol in self.bars or c.symbol in self.dividends or c.symbol in self.vols
            if getattr(c, "secType", "") == "OPT":
                key = (c.lastTradeDateOrContractMonth, float(c.strike), c.right)
                known = key in self.quotes
            if known:
                c.conId = 1000 + len(c.symbol)
                c.primaryExchange = "NASDAQ"
            out.append(c if known else None)
        return out

    def reqHistoricalData(self, contract: Any, **kwargs: Any) -> list[Any]:  # noqa: N802
        self.calls.append("reqHistoricalData")
        self.requests.append({"symbol": contract.symbol, **kwargs})
        req_id = len(self.requests)
        table = {"OPTION_IMPLIED_VOLATILITY": self.iv, "HISTORICAL_VOLATILITY": self.hv}.get(
            kwargs["whatToShow"], self.bars
        )
        bars = FakeBars(
            SimpleNamespace(date=d, open=o, high=h, low=lo, close=c, volume=v)
            for d, o, h, lo, c, v in table.get(contract.symbol, ())
        )
        bars.reqId = req_id
        queue = self.faults.get(contract.symbol)
        fault = queue.pop(0) if queue else None
        if fault in ("1100", "flap"):
            self.errorEvent.emit(-1, 1100, "Connectivity between IB and TWS has been lost.", None)
            self.errorEvent.emit(-1, 1102, "Connectivity ... restored - data maintained.", None)
            if fault == "flap":
                return bars
        elif fault == "timeout":
            self.skew += float(kwargs.get("timeout") or 60.0)
        elif fault in ERROR_162:
            self.errorEvent.emit(req_id, 162, ERROR_162[fault], contract)
        if fault is not None:
            bars.clear()
        return bars

    def reqMktData(self, contract: Any, ticks: str, snapshot: bool, regulatory: bool) -> Any:  # noqa: N802
        self.calls.append(f"reqMktData {ticks}")
        past, close = self.dividends.get(contract.symbol, (None, float("nan")))
        nan = float("nan")
        quote = None
        if getattr(contract, "secType", "") == "OPT":
            key = (contract.lastTradeDateOrContractMonth, float(contract.strike), contract.right)
            quote = self.quotes.get(key)
        ticker = SimpleNamespace(
            dividends=None, close=close, _past=past, impliedVolatility=nan, histVolatility=nan,
            _vols=self.vols.get(contract.symbol), bid=nan, ask=nan, last=nan, _quote=quote,
        )  # fmt: skip
        self._streams.append(ticker)
        return ticker

    def waitOnUpdate(self, timeout: float = 0) -> bool:  # noqa: N802
        self.calls.append("waitOnUpdate")
        for t in self._streams:
            if t._vols is not None:
                t.impliedVolatility, t.histVolatility = t._vols
            if t._quote is not None:
                t.bid, t.ask = t._quote
            if t._past is not None:
                t.dividends = SimpleNamespace(
                    past12Months=t._past, next12Months=t._past, nextDate=None, nextAmount=None
                )
        return True

    def cancelMktData(self, contract: Any) -> bool:  # noqa: N802
        self.calls.append("cancelMktData")
        return True

    def reqSecDefOptParams(self, symbol: str, exchange: str, sec_type: str, con_id: int) -> Any:  # noqa: N802
        self.calls.append("reqSecDefOptParams")
        smart = SimpleNamespace(
            exchange="SMART", tradingClass=symbol, multiplier="100",
            expirations=list(self.expirations), strikes=list(self.strikes),
        )  # fmt: skip
        other = SimpleNamespace(
            exchange="CBOE", tradingClass=symbol, multiplier="100",
            expirations=["20990101"], strikes=[1.0],
        )  # fmt: skip
        return [smart, other]

    def reqTickers(self, *contracts: Any) -> list[Any]:  # noqa: N802
        self.calls.append("reqTickers")
        out = []
        for c in contracts:
            bid, ask = self.quotes[(c.lastTradeDateOrContractMonth, float(c.strike), c.right)]
            out.append(SimpleNamespace(bid=bid, ask=ask, last=float("nan"), close=-1.0))
        return out

    def disconnect(self) -> None:
        self.calls.append("disconnect")

    # ---------------------------------------------------------------- never to be reached

    def connect(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append("IB.connect")  # syncs positions / account: the facade must not use it

    def placeOrder(self, *args: Any) -> None:  # noqa: N802
        self.calls.append("placeOrder")

    def reqPositions(self) -> None:  # noqa: N802
        self.calls.append("reqPositions")

    def accountValues(self) -> list[Any]:  # noqa: N802
        self.calls.append("accountValues")
        return []
