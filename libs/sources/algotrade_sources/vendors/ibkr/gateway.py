"""The IB Gateway facade, READ-ONLY: the only module that imports ``ib_async`` (ADR 0026).

``IbkrMarketData`` exposes market data and nothing else: stock contract lookup (conid,
primary exchange), daily bars, the implied- and historical-volatility history of an underlying,
a streamed snapshot of the underlying's option implied vol and historical vol (generic ticks
106 and 104), IB dividends (generic tick 456), option chain parameters and option quote
snapshots. Each returns plain JSON-able values; no ``ib_async`` object leaves this module.

Read-only by construction (ADR 0026), three layers:

1. **This facade.** The ``ib_async.IB`` object is wrapped in ``_Guarded`` the moment it is
   built: only the calls in ``MARKET_DATA_CALLS`` / ``CLIENT_CALLS`` pass, anything else
   (orders, account values, positions, executions) raises ``ReadOnlyViolationError`` before a
   message is sent. ``IB.connect`` is never called: even with ``readonly=True`` it requests
   positions (and by default account updates, open orders and executions) to synchronise.
   The facade performs only the API handshake (``IB.client.connect``) and refuses to connect
   unless its config says ``readonly`` (it always does; the flag exists so the refusal is
   tested). Every call made is logged (``calls``) so tests prove which ones were made.
2. **Fitness test + import-linter.** ``test_read_only_guard.py`` (next to this vendor's
   tests) fails on any reference to an order or account API of ``ib_async`` anywhere in
   ``src/`` and ``apps/``, and on any import of ``ib_async`` outside this module (also an
   import-linter contract).
3. **The gateway itself.** The owner ticks "Read-Only API" in IB Gateway's API settings, so
   the gateway rejects order messages even if the two layers above were bypassed.

Pacing: every message waits on ``general`` (IBKR: <= 50 messages/s); every historical-data
request also waits on ``historical`` (<= 60 per 10 minutes, >= 10 s between identical ones).
Both are the registry's shared limiters (``sources/framework/limiter.py``).
"""

import math
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ib_async import IB, Option, Stock

from algotrade_sources.framework.base import SessionUnavailableError
from algotrade_sources.framework.http import Pacer

# The ib_async.IB methods this facade may call: market data, contract lookup, the event loop.
MARKET_DATA_CALLS = frozenset(
    {
        "reqMarketDataType",
        "qualifyContracts",
        "reqHistoricalData",
        "reqMktData",
        "cancelMktData",  # ends a market-data subscription (not an order)
        "reqTickers",
        "reqSecDefOptParams",
        "waitOnUpdate",
        "disconnect",
    }
)
CLIENT_CALLS = frozenset({"connect", "isReady"})  # the API handshake only
DIVIDEND_TICKS = "456"  # IB dividends: past 12 months, next 12 months, next date and amount
VOL_TICKS = "104,106"  # the underlying's historical vol (104) and option implied vol (106)
VOL_HISTORIES = ("OPTION_IMPLIED_VOLATILITY", "HISTORICAL_VOLATILITY")
EASTERN = "US/Eastern"  # IB's time zone name for an end date's 23:59:59


class ReadOnlyViolationError(PermissionError):
    """Something asked the IBKR facade for a call that is not market data."""


class _Guarded:
    """Lets through only ``allowed`` attributes of ``target``; logs each one used."""

    def __init__(self, target: Any, allowed: frozenset[str], log: list[str]) -> None:
        self._target, self._allowed, self._log = target, allowed, log

    def __getattr__(self, name: str) -> Any:
        if name not in self._allowed:
            raise ReadOnlyViolationError(
                f"{name!r} is not a market-data call: the facade is read-only"
            )
        self._log.append(name)
        return getattr(self._target, name)


@dataclass(frozen=True)
class GatewayConfig:
    host: str
    port: int
    client_id: int
    market_data_type: int = 3  # 1 live, 3 delayed
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0
    stream_wait_s: float = 4.0
    readonly: bool = True  # never False: the facade refuses to connect otherwise

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class _NoPacing:
    def wait(self) -> float:
        return 0.0

    def hold(self, seconds: float) -> None:
        return None


def ib_symbol(symbol: str) -> str:
    """Our ACT-style ticker -> IB's (``BRK.B`` -> ``BRK B``)."""
    return symbol.replace(".", " ").replace("/", " ")


def _price(value: Any) -> float | None:
    """A finite, non-negative number, else ``None`` (IB sends -1 or NaN for "no quote")."""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


@dataclass
class IbkrMarketData:
    """Read-only market data over one IB Gateway API session (``connect`` ... ``close``)."""

    config: GatewayConfig
    general: Pacer = field(default_factory=_NoPacing)
    historical: Pacer = field(default_factory=_NoPacing)
    ib_factory: Callable[[], Any] = IB
    clock: Callable[[], float] = time.monotonic
    calls: list[str] = field(default_factory=list)  # every guarded call made, in order
    _ib: _Guarded | None = None
    _contracts: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ lifecycle

    def reachable(self) -> str | None:
        """``None`` when something accepts TCP connections on the gateway port, else why."""
        try:
            with socket.create_connection((self.config.host, self.config.port), timeout=2.0):
                return None
        except OSError as exc:
            return f"IB Gateway not reachable on {self.config.address} ({exc})"

    def connect(self) -> None:
        if not self.config.readonly:
            raise ReadOnlyViolationError("refusing to connect: the IBKR facade only runs read-only")
        raw = self.ib_factory()
        ib = _Guarded(raw, MARKET_DATA_CALLS, self.calls)
        client = _Guarded(raw.client, CLIENT_CALLS, self.calls)
        self.general.wait()
        try:
            client.connect(
                self.config.host,
                self.config.port,
                self.config.client_id,
                timeout=self.config.connect_timeout_s,
            )
        except (OSError, TimeoutError) as exc:
            raise SessionUnavailableError(
                f"IB Gateway not reachable on {self.config.address}: {exc}"
            ) from exc
        if not client.isReady():
            raise SessionUnavailableError(f"IB Gateway on {self.config.address}: API not ready")
        self._ib = ib
        self.general.wait()
        ib.reqMarketDataType(self.config.market_data_type)

    def close(self) -> None:
        ib, self._ib = self._ib, None
        self._contracts.clear()
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:  # closing never fails the caller
                return

    @property
    def ib(self) -> _Guarded:
        if self._ib is None:
            raise SessionUnavailableError("the IB Gateway session is not open")
        return self._ib

    # ------------------------------------------------------------------ contracts

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        self.general.wait()
        return getattr(self.ib, name)(*args, **kwargs)

    def _stock(self, symbol: str, conid: int | None = None) -> Any:
        """The SMART stock contract of ``symbol``: built from a known ``conid`` (no lookup),
        else qualified once per session."""
        if symbol not in self._contracts and conid:
            self._contracts[symbol] = Stock(ib_symbol(symbol), "SMART", "USD", conId=conid)
        if symbol not in self._contracts:
            found = self._call("qualifyContracts", Stock(ib_symbol(symbol), "SMART", "USD"))
            if not found or found[0] is None:
                raise LookupError(f"IBKR has no stock contract for {symbol}")
            self._contracts[symbol] = found[0]
        return self._contracts[symbol]

    def stock_contracts(self, symbols: list[str]) -> dict[str, dict[str, Any] | None]:
        """IB's SMART stock contract per symbol (``None``: IB has none), qualified together in
        one ``qualifyContracts`` call (paced one ``general`` slot per contract)."""
        wanted = [Stock(ib_symbol(s), "SMART", "USD") for s in symbols]
        for _ in wanted[1:]:
            self.general.wait()
        found = self._call("qualifyContracts", *wanted) if wanted else []
        out: dict[str, dict[str, Any] | None] = {}
        for symbol, c in zip(symbols, [*found, *[None] * len(symbols)], strict=False):
            if c is None or not getattr(c, "conId", 0):
                out[symbol] = None
                continue
            self._contracts[symbol] = c
            out[symbol] = {
                "conid": int(c.conId),
                "primary_exchange": str(c.primaryExchange or "") or None,
                "sec_type": str(c.secType or "STK"),
                "currency": str(c.currency or "USD"),
            }
        return out

    # ------------------------------------------------------------------ market data

    def _history(self, contract: Any, end: date, duration: str, what: str) -> list[dict[str, Any]]:
        self.historical.wait()
        bars = self._call(
            "reqHistoricalData",
            contract,
            endDateTime=f"{end:%Y%m%d} 23:59:59 {EASTERN}",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow=what,
            useRTH=True,
            formatDate=1,
            timeout=self.config.request_timeout_s,
        )
        return [
            {
                "date": str(b.date)[:10],
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars or []
        ]

    def historical_bars(self, symbol: str, end: date, sessions: int) -> list[dict[str, Any]]:
        """The last ``sessions`` daily TRADES bars up to ``end`` (IB adjusts them for splits)."""
        years = math.ceil((sessions + 10) / 250)
        return self._history(self._stock(symbol), end, f"{years} Y", "TRADES")[-sessions:]

    def implied_volatility(self, symbol: str, end: date) -> list[dict[str, Any]]:
        """Daily OPTION_IMPLIED_VOLATILITY bars of the underlying (30-day IV) up to ``end``."""
        return self._history(self._stock(symbol), end, "10 D", "OPTION_IMPLIED_VOLATILITY")

    def volatility_history(
        self, symbol: str, start: date, end: date, conid: int | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Daily OPTION_IMPLIED_VOLATILITY and HISTORICAL_VOLATILITY closes of the underlying
        (annualised 30-day vols, IB's) from ``start`` to ``end``: one request per kind."""
        contract = self._stock(symbol, conid)
        days = (end - start).days + 1
        duration = f"{days} D" if days <= 365 else f"{math.ceil(days / 365)} Y"
        out: dict[str, list[dict[str, Any]]] = {}
        for what in VOL_HISTORIES:
            bars = self._history(contract, end, duration, what)
            out[what] = [
                {"date": b["date"], "close": b["close"]}
                for b in bars
                if b["date"] >= start.isoformat()
            ]
        return out

    def underlying_vols(self, symbols: dict[str, int | None]) -> dict[str, dict[str, Any]]:
        """The underlyings' option implied vol (tick 106) and historical vol (tick 104) now:
        one stream each (``symbol -> conid``, ``None``: look it up), all open together, read
        once every one has both vols or ``stream_wait_s`` passed, then cancelled."""
        streams: dict[str, tuple[Any, Any]] = {}
        out: dict[str, dict[str, Any]] = {}
        try:
            for symbol, conid in symbols.items():
                try:
                    contract = self._stock(symbol, conid)
                except LookupError:
                    out[symbol] = {"listed": False, "iv": None, "hv": None}
                    continue
                ticker = self._call("reqMktData", contract, VOL_TICKS, False, False)
                streams[symbol] = (contract, ticker)
            deadline = self.clock() + self.config.stream_wait_s
            while (left := deadline - self.clock()) > 0 and any(
                _price(t.impliedVolatility) is None or _price(t.histVolatility) is None
                for _, t in streams.values()
            ):
                self.ib.waitOnUpdate(timeout=left)
        finally:
            for contract, _ in streams.values():
                self._call("cancelMktData", contract)
        for symbol, (_, ticker) in streams.items():
            iv, hv = _price(ticker.impliedVolatility), _price(ticker.histVolatility)
            out[symbol] = {"listed": True, "iv": iv, "hv": hv}
        return out

    def dividends(self, symbol: str) -> dict[str, Any]:
        """IB dividends (tick 456) and the last close, streamed for at most ``stream_wait_s``."""
        contract = self._stock(symbol)
        ticker = self._call("reqMktData", contract, DIVIDEND_TICKS, False, False)
        deadline = self.clock() + self.config.stream_wait_s
        try:
            while ticker.dividends is None and (left := deadline - self.clock()) > 0:
                self.ib.waitOnUpdate(timeout=left)
        finally:
            self._call("cancelMktData", contract)
        found = ticker.dividends
        return {
            "past12Months": _price(found.past12Months) if found else None,
            "next12Months": _price(found.next12Months) if found else None,
            "nextDate": str(found.nextDate) if found and found.nextDate else None,
            "nextAmount": _price(found.nextAmount) if found else None,
            "close": _price(ticker.close),
        }

    def option_params(self, symbol: str) -> list[dict[str, Any]]:
        """Listed expirations and strikes (SMART), from ``reqSecDefOptParams``."""
        contract = self._stock(symbol)
        chains = self._call("reqSecDefOptParams", contract.symbol, "", "STK", contract.conId)
        return [
            {
                "trading_class": c.tradingClass,
                "multiplier": str(c.multiplier),
                "expirations": sorted(c.expirations),
                "strikes": sorted(float(s) for s in c.strikes),
            }
            for c in chains or []
            if c.exchange == "SMART"
        ]

    def option_quote(self, symbol: str, expiry: date, strike: float, right: str) -> dict[str, Any]:
        """A snapshot quote of one option (``right``: C or P); ``listed`` False if IB has none."""
        wanted = Option(ib_symbol(symbol), f"{expiry:%Y%m%d}", strike, right, "SMART", "100", "USD")
        found = self._call("qualifyContracts", wanted)
        if not found or found[0] is None:
            return {"listed": False}
        tickers = self._call("reqTickers", found[0])
        ticker = tickers[0] if tickers else None
        return {
            "listed": True,
            "bid": _price(ticker.bid) if ticker else None,
            "ask": _price(ticker.ask) if ticker else None,
            "last": _price(ticker.last) if ticker else None,
            "close": _price(ticker.close) if ticker else None,
        }
