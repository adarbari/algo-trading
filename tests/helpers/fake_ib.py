"""A fake ``ib_async.IB`` for IBKR tests: canned market data, every call recorded, no network.

It also has order and account methods (``placeOrder``, ``reqPositions``, ...) that record a
call if ever reached: tests assert they never are (the facade's guard blocks them first).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import Any

Bar = tuple[date, float, float, float, float, float]  # date, open, high, low, close, volume


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
    """Canned answers by symbol: ``bars`` / ``iv`` (daily bars), ``dividends`` (past 12
    months, close), ``expirations`` / ``strikes`` and ``quotes`` ((expiry, strike, right) ->
    (bid, ask)). Unknown symbols do not qualify."""

    bars: Mapping[str, Sequence[Bar]] = field(default_factory=dict)
    iv: Mapping[str, Sequence[Bar]] = field(default_factory=dict)
    dividends: Mapping[str, tuple[float | None, float]] = field(default_factory=dict)
    expirations: Sequence[str] = ()
    strikes: Sequence[float] = ()
    quotes: Mapping[tuple[str, float, str], tuple[float, float]] = field(default_factory=dict)
    connect_error: Exception | None = None
    calls: list[str] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.client = FakeClient(self.calls, self.connect_error)
        self._streams: list[SimpleNamespace] = []

    # ---------------------------------------------------------------- market data

    def reqMarketDataType(self, kind: int) -> None:  # noqa: N802
        self.calls.append(f"reqMarketDataType {kind}")

    def qualifyContracts(self, *contracts: Any) -> list[Any]:  # noqa: N802
        self.calls.append("qualifyContracts")
        out = []
        for c in contracts:
            known = c.symbol in self.bars or c.symbol in self.dividends
            if getattr(c, "secType", "") == "OPT":
                key = (c.lastTradeDateOrContractMonth, float(c.strike), c.right)
                known = key in self.quotes
            if known:
                c.conId = 1000 + len(c.symbol)
            out.append(c if known else None)
        return out

    def reqHistoricalData(self, contract: Any, **kwargs: Any) -> list[Any]:  # noqa: N802
        self.calls.append("reqHistoricalData")
        self.requests.append({"symbol": contract.symbol, **kwargs})
        table = self.iv if kwargs["whatToShow"] == "OPTION_IMPLIED_VOLATILITY" else self.bars
        return [
            SimpleNamespace(date=d, open=o, high=h, low=lo, close=c, volume=v)
            for d, o, h, lo, c, v in table.get(contract.symbol, ())
        ]

    def reqMktData(self, contract: Any, ticks: str, snapshot: bool, regulatory: bool) -> Any:  # noqa: N802
        self.calls.append(f"reqMktData {ticks}")
        past, close = self.dividends.get(contract.symbol, (None, float("nan")))
        ticker = SimpleNamespace(dividends=None, close=close, _past=past)
        self._streams.append(ticker)
        return ticker

    def waitOnUpdate(self, timeout: float = 0) -> bool:  # noqa: N802
        self.calls.append("waitOnUpdate")
        for t in self._streams:
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
