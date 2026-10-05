"""The IB Gateway facade, READ-ONLY: the only module that imports ``ib_async`` (ADR 0026).

``IbkrMarketData`` exposes market data and nothing else: stock contract lookup (conid,
primary exchange), daily bars, the implied- and historical-volatility history of an underlying,
a streamed snapshot of the underlying's option implied vol and historical vol (generic ticks
106 and 104), IB dividends (generic tick 456), option chain parameters and option quote
snapshots (one contract; or, streamed, the calls and puts of an expiry at given strikes: the
API's live quotes, ADR 0028). Each returns plain JSON-able values; no ``ib_async`` object
leaves this module.

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
request also waits on ``historical`` (``[ibkr] historical_min_interval_s``, 10 s by default).
Both are the registry's shared limiters (``sources/framework/limiter.py``); ``cool_down``
holds ``historical`` for every process (a task's back-off before a retry).

Unanswered is not empty: ``ib_async`` returns an empty bar list on a request timeout and on
an IB error (``RaiseRequestErrors`` is off), the same as a genuine "no data". The facade
watches IB's error events while a historical request is in flight and times it, and raises
``TransientFetchError`` (retryable) for a timeout, an error of that request (error 162
pacing violation, a cancelled query, ...) or a lost connection (error 1100, HMDS farm down),
and a plain ``LookupError`` (not retried; still not "no data") for an error a retry cannot
fix (``refused``: no security definition, no market data permissions). Only an empty answer
without any of these, or IB's own error 162 "query returned no data", is an empty result.
"""

import math
import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ib_async import IB, Option, Stock

from algotrade_sources.framework.base import SessionUnavailableError, TransientFetchError
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
VOL_HISTORIES = ("OPTION_IMPLIED_VOLATILITY", "HISTORICAL_VOLATILITY")  # what a payload may hold
BACKFILL_HISTORIES = VOL_HISTORIES[:1]  # what ``volatility_history`` fetches: the IV only
# Errors without a request id that mean a request in flight may never be answered: the
# gateway lost IB (1100), the socket was reset (1300), the HMDS farm (2105) or the
# TWS-server link (2110) is broken.
CONNECTIVITY_ERRORS = frozenset({1100, 1300, 2105, 2110})
NO_DATA_ERROR = 162  # "Historical Market Data Service error": no data, or pacing / other
NO_DATA_TEXT = "no data"  # in 162's message when IB answered "query returned no data"
TIMEOUT_SLACK_S = 1.0  # an empty answer this close to the request timeout is the timeout
# Request errors a retry cannot fix: no security definition (200), market data not
# subscribed (354, 10090); and 162 naming missing permissions. Not transient: no retry.
REFUSED_ERRORS = frozenset({200, 354, 10090})
REFUSED_TEXT = "permission"
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


def _informational(code: int) -> bool:
    """IB's warnings and notices (``ib_async`` logs them, nothing failed): 165, 2100-2199."""
    return code == 165 or 2100 <= code < 2200


def _mine(rid: int, req_id: int | None) -> bool:
    return rid != -1 and (req_id is None or rid == req_id)


def refused(errors: Sequence[tuple[int, int, str]], req_id: int | None) -> str | None:
    """A request error retrying cannot fix (``REFUSED_ERRORS``, a 162 about permissions)."""
    for rid, code, message in errors:
        if _mine(rid, req_id) and (
            code in REFUSED_ERRORS or (code == NO_DATA_ERROR and REFUSED_TEXT in message.lower())
        ):
            return f"IB error {code}: {message}"
    return None


def unanswered(
    errors: Sequence[tuple[int, int, str]], req_id: int | None, elapsed: float, timeout: float
) -> str | None:
    """Why an EMPTY historical answer is not IB saying "no data" (``None``: it is).

    ``errors``: ``(request id, code, message)`` IB sent while the request was in flight;
    ``req_id``: the request's id (``None``: unknown, any request-scoped error counts);
    ``elapsed``: how long it took, against ``timeout`` (``ib_async`` gives up silently)."""
    for rid, code, message in errors:
        if rid == -1:
            if code in CONNECTIVITY_ERRORS:
                return f"IB error {code} while the request was in flight: {message}"
            continue
        if not _mine(rid, req_id) or _informational(code):
            continue
        if code == NO_DATA_ERROR and NO_DATA_TEXT in message.lower():
            continue  # IB's own "query returned no data": a genuine empty answer
        return f"IB error {code}: {message}"
    if timeout > 0 and elapsed >= timeout - TIMEOUT_SLACK_S:
        return f"no answer within the {timeout:g} s request timeout"
    return None


def _detach_resubscribe(raw: Any) -> None:
    """Remove ``IB``'s own reaction to "connectivity restored" (error 1102).

    ``ib_async.IB`` subscribes ``_onError`` to its ``errorEvent``; on 1102 it re-requests the
    account summary by itself, outside ``_Guarded``. Seen on a long backfill (a gateway
    connectivity blip): an account request the facade never made. Detached, a reconnect sends
    nothing; market-data subscriptions are re-established by the gateway ("data maintained").
    """
    event, handler = getattr(raw, "errorEvent", None), getattr(raw, "_onError", None)
    if event is not None and handler is not None:
        event -= handler


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


def _number(value: Any) -> float | None:
    """A finite number (a delta may be negative), else ``None``."""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


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
    _events: Any = None  # the raw IB's errorEvent while connected (our listener on it)
    _errors: list[tuple[int, int, str]] | None = None  # IB errors during a history request
    _contracts: dict[str, Any] = field(default_factory=dict)
    _options: dict[tuple[str, date, float, str], Any] = field(default_factory=dict)

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
        _detach_resubscribe(raw)
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
        self._listen(raw)
        self._ib = ib
        self.general.wait()
        ib.reqMarketDataType(self.config.market_data_type)

    def close(self) -> None:
        ib, self._ib = self._ib, None
        self._contracts.clear()
        self._options.clear()
        events, self._events = self._events, None
        if events is not None:
            events -= self._on_error
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:  # closing never fails the caller
                return

    def _listen(self, raw: Any) -> None:
        """Subscribe to the raw IB's error events (no message is sent: a local callback)."""
        events = getattr(raw, "errorEvent", None)
        if events is not None:
            events += self._on_error
            self._events = events

    def _on_error(self, req_id: int, code: int, message: str, *_: Any) -> None:
        if self._errors is not None:
            self._errors.append((int(req_id), int(code), str(message)))

    def cool_down(self, seconds: float) -> None:
        """Hold historical requests for ``seconds`` (every process): a back-off."""
        self.historical.hold(seconds)

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
        """Daily ``what`` bars; ``TransientFetchError`` when IB did not answer (``unanswered``)."""
        self.historical.wait()
        timeout = self.config.request_timeout_s
        errors: list[tuple[int, int, str]] = []
        self._errors = errors
        started = self.clock()
        try:
            bars = self._call(
                "reqHistoricalData",
                contract,
                endDateTime=f"{end:%Y%m%d} 23:59:59 {EASTERN}",
                durationStr=duration,
                barSizeSetting="1 day",
                whatToShow=what,
                useRTH=True,
                formatDate=1,
                timeout=timeout,
            )
        finally:
            self._errors = None
        if not bars:
            req_id, elapsed = getattr(bars, "reqId", None), self.clock() - started
            if (why := refused(errors, req_id)) is not None:
                raise LookupError(f"IBKR {what} {contract.symbol}: {why}")  # not retried
            if (why := unanswered(errors, req_id, elapsed, timeout)) is not None:
                raise TransientFetchError(f"IBKR {what} {contract.symbol}: {why}")
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
        """Daily OPTION_IMPLIED_VOLATILITY closes of the underlying (IB's annualised 30-day
        implied vol) from ``start`` to ``end``: ONE request (``BACKFILL_HISTORIES``; the HV
        comes from the nightly snapshot, tick 104). Keyed by kind, as ``VOL_HISTORIES``."""
        contract = self._stock(symbol, conid)
        days = (end - start).days + 1
        duration = f"{days} D" if days <= 365 else f"{math.ceil(days / 365)} Y"
        out: dict[str, list[dict[str, Any]]] = {}
        for what in BACKFILL_HISTORIES:
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

    def option_quotes(
        self, symbol: str, expiry: date, strikes: Sequence[float]
    ) -> list[dict[str, Any]]:
        """Quotes now of the calls and puts of ``symbol`` expiring ``expiry`` at ``strikes``
        (SMART), one row per (strike, right). Contracts are qualified once per session (one
        ``qualifyContracts`` for those not seen yet); every listed one is then streamed
        (``reqMktData``: IB serves delayed data to streams, not to snapshot requests), read
        once each has a bid and an ask or ``stream_wait_s`` passed (outside trading hours only
        the close comes), and cancelled. Each contract is paced as a message. A contract IB
        does not list is ``listed`` False. IB's model implied vol and delta come with a quote
        when IB sends them (``None`` otherwise)."""
        wanted = [(float(k), right) for k in strikes for right in ("C", "P")]
        new = [w for w in wanted if (symbol, expiry, *w) not in self._options]
        if new:
            contracts = [
                Option(ib_symbol(symbol), f"{expiry:%Y%m%d}", k, r, "SMART", "100", "USD")
                for k, r in new
            ]
            for _ in contracts[1:]:
                self.general.wait()
            found = self._call("qualifyContracts", *contracts)
            for w, c in zip(new, [*found, *[None] * len(new)], strict=False):
                listed = c is not None and bool(getattr(c, "conId", 0))
                self._options[(symbol, expiry, *w)] = c if listed else None
        rows = [(w, self._options[(symbol, expiry, *w)]) for w in wanted]
        tickers = iter(self._stream([c for _, c in rows if c is not None]))
        out: list[dict[str, Any]] = []
        for (strike, right), contract in rows:
            if contract is None:
                out.append({"strike": strike, "right": right, "listed": False})
                continue
            ticker = next(tickers, None)
            greeks = getattr(ticker, "modelGreeks", None)
            out.append(
                {
                    "strike": strike,
                    "right": right,
                    "listed": True,
                    "conid": int(contract.conId),
                    "bid": _price(getattr(ticker, "bid", None)),
                    "ask": _price(getattr(ticker, "ask", None)),
                    "last": _price(getattr(ticker, "last", None)),
                    "close": _price(getattr(ticker, "close", None)),
                    "volume": _price(getattr(ticker, "volume", None)),
                    "iv": _price(getattr(greeks, "impliedVol", None)),
                    "delta": _number(getattr(greeks, "delta", None)),
                }
            )
        return out

    def _stream(self, contracts: list[Any]) -> list[Any]:
        """Stream ``contracts`` together until each has a bid and an ask (at most
        ``stream_wait_s``), then cancel every stream: their tickers, in order."""
        streams: list[tuple[Any, Any]] = []
        try:
            for contract in contracts:
                streams.append((contract, self._call("reqMktData", contract, "", False, False)))
            deadline = self.clock() + self.config.stream_wait_s
            while (left := deadline - self.clock()) > 0 and any(
                _price(t.bid) is None or _price(t.ask) is None for _, t in streams
            ):
                self.ib.waitOnUpdate(timeout=left)
        finally:
            for contract, _ in streams:
                self._call("cancelMktData", contract)
        return [t for _, t in streams]
