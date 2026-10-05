"""Live option quotes for one underlying and expiry (ADR 0028): from a quote feed (IB Gateway,
read-only) when it answers, else the stored delayed chain with a status. Never an error page.

The stored chain (the read model's chain for the latest session, ADR 0036) names the contracts:
their ids, strikes and the underlying's symbol and price; no chain stored for that session (the
chain step late or failed) is a 404, as the Options pane shows no chain. The feed is asked for
the calls and puts at the strikes the caller names, or the ``live_strikes`` nearest the
underlying. An answer is cached for ``live_cache_s`` per (underlying, expiry, strikes) and
handed to the recorder, which writes it to ``live/option_quotes`` in the background. When the
feed is disabled, down, busy, slow or fails, the answer is the stored chain's quotes for the
same strikes, with ``source = "stored"`` and a status saying why.

Statuses: ``LIVE`` (just read), ``CACHED`` (read within the cache window), ``DISABLED`` (no
feed configured), ``UNAVAILABLE`` (the gateway is down, busy or too slow), ``ERROR`` (the feed
failed otherwise; logged).
"""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from statistics import median
from typing import Any, Protocol

import pandas as pd

from algotrade.config.site.settings import IbkrSettings
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError
from algotrade.data.chains import underlying_quotes
from algotrade.services.live.recorder import Recorder
from algotrade.services.read.context import NotFoundError, ReadContext
from algotrade.services.read.instruments.chains import load_chains, load_quotes
from algotrade.services.read.instruments.identity import resolve_id
from algotrade.services.read.values import records

log = logging.getLogger(__name__)

LIVE, CACHED, DISABLED, UNAVAILABLE, ERROR = "LIVE", "CACHED", "DISABLED", "UNAVAILABLE", "ERROR"
LIVE_TYPE = 1  # IB market data type 1 is real time; 2-4 are frozen or delayed
QUOTE_COLUMNS = ("instrument_id", "expiry", "right", "strike", "listed", "bid", "ask", "last",
                 "close", "volume", "iv", "delta")  # fmt: skip


class FeedUnavailableError(AlgoTradeError):
    """The feed cannot answer now: ``status`` is DISABLED or UNAVAILABLE, ``detail`` why."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


class QuoteFeed(Protocol):
    """Live option quotes: ``quotes`` -> one row per (strike, right) with ``strike``,
    ``right``, ``listed``, ``conid``, ``bid``, ``ask``, ``last``, ``close``, ``volume``,
    ``iv``, ``delta``; raises ``FeedUnavailableError`` when it cannot answer now."""

    @property
    def market_data_type(self) -> int:
        """IB's market data type: 1 real time, 2-4 frozen or delayed."""
        ...

    def quotes(self, symbol: str, expiry: date, strikes: Sequence[float]) -> pd.DataFrame: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class DisabledFeed:
    """No live feed (``[ibkr]`` disabled, the gateway not configured, or a test app)."""

    reason: str
    market_data_type: int = 3

    def quotes(self, symbol: str, expiry: date, strikes: Sequence[float]) -> pd.DataFrame:
        raise FeedUnavailableError(DISABLED, self.reason)

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class LiveOptionChain:
    underlying_id: str
    symbol: str | None
    expiry: date
    source: str  # "ibkr": read live from IB Gateway; "stored": the stored chain of ``session``
    status: str  # LIVE, CACHED, DISABLED, UNAVAILABLE, ERROR
    detail: str | None  # why the stored chain was served
    as_of: datetime | None  # when the quotes were taken
    delayed: bool  # IB's delayed (or frozen) data, or the stored chain
    session: date  # the stored chain the contracts come from
    underlying_price: float | None
    strikes: list[float]
    quotes: list[dict[str, Any]]  # QUOTE_COLUMNS, sorted by strike then right


@dataclass(frozen=True)
class _Stored:
    underlying_id: str
    symbol: str | None
    session: date
    price: float | None
    taken: datetime | None  # when the stored chain was captured
    frame: pd.DataFrame  # the expiry's stored quotes


class LiveQuotes:
    """Live quotes with a cache, the stored-chain fallback and background recording."""

    def __init__(
        self,
        feed: QuoteFeed,
        recorder: Recorder | None,
        options: IbkrSettings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.feed, self._recorder, self._options, self._clock = feed, recorder, options, clock
        self._cache: dict[tuple[str, date, tuple[float, ...]], LiveOptionChain] = {}
        self._lock = threading.Lock()

    def chain(
        self, ctx: ReadContext, key: str, expiry: date, strikes: Sequence[float] | None = None
    ) -> LiveOptionChain:
        """The quotes of ``key``'s calls and puts expiring ``expiry`` at ``strikes`` (default:
        the ``live_strikes`` nearest the underlying). ``NotFoundError`` when the stored chain
        has no such underlying or expiry; ``ConfigurationError`` for strikes it does not list."""
        stored = _stored(ctx, key, expiry)
        wanted = self._strikes(stored, strikes)
        cache_key = (stored.underlying_id, expiry, tuple(wanted))
        now = self._clock()
        with self._lock:
            hit = self._cache.get(cache_key)
        if hit is not None and _fresh(hit, now, self._options):
            return replace(hit, status=CACHED)
        if stored.symbol is None:
            return _fallback(stored, expiry, wanted, ERROR, "the stored chain has no symbol")
        try:
            found = self.feed.quotes(stored.symbol, expiry, wanted)
        except FeedUnavailableError as exc:
            return _fallback(stored, expiry, wanted, exc.status, exc.detail)
        except Exception as exc:
            log.warning("live quotes for %s %s failed", stored.symbol, expiry, exc_info=True)
            return _fallback(stored, expiry, wanted, ERROR, f"{type(exc).__name__}: {exc}")
        taken = self._clock()
        frame = _with_ids(found, stored.frame, stored.underlying_id, expiry)
        answer = LiveOptionChain(
            underlying_id=stored.underlying_id,
            symbol=stored.symbol,
            expiry=expiry,
            source="ibkr",
            status=LIVE,
            detail=None,
            as_of=taken,
            delayed=self.feed.market_data_type != LIVE_TYPE,
            session=stored.session,
            underlying_price=stored.price,
            strikes=wanted,
            quotes=records(frame.reindex(columns=list(QUOTE_COLUMNS))),
        )
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if _fresh(v, taken, self._options)}
            self._cache[cache_key] = answer
        if self._recorder is not None:
            self._recorder.submit(_snapshot(frame, stored, taken, self.feed.market_data_type))
        return answer

    def close(self) -> None:
        """Stop the feed's session and flush the recorder (app shutdown)."""
        self.feed.close()
        if self._recorder is not None:
            self._recorder.close()

    def _strikes(self, stored: _Stored, asked: Sequence[float] | None) -> list[float]:
        listed = sorted({float(k) for k in stored.frame["strike"]})
        if asked:
            wanted = sorted({float(k) for k in asked})
            unknown = [k for k in wanted if k not in set(listed)]
            if unknown:
                raise ConfigurationError(
                    f"strikes {unknown} are not in the stored chain for {stored.underlying_id} "
                    f"{stored.frame['expiry'].iloc[0]} ({stored.session})"
                )
            most = self._options.live_max_strikes
            if len(wanted) > most:
                raise ConfigurationError(f"at most {most} strikes per request, got {len(wanted)}")
            return wanted
        centre = stored.price if stored.price is not None else median(listed)
        nearest = sorted(listed, key=lambda k: (abs(k - centre), k))
        return sorted(nearest[: self._options.live_strikes])


def _fresh(answer: LiveOptionChain, now: datetime, options: IbkrSettings) -> bool:
    if answer.as_of is None:
        return False
    return (now - answer.as_of).total_seconds() < options.live_cache_s


def _stored(ctx: ReadContext, key: str, expiry: date) -> _Stored:
    """The stored chain's quotes for ``expiry`` for the latest session: the read model's
    chain, exactly what the Options pane shows (``Instrument.chain``), with the underlying's
    quote captured with it. ``NotFoundError`` for an unknown instrument, no chain stored for
    the session, or an expiry it does not list."""
    iid = resolve_id(ctx, key)
    if iid is None:
        raise NotFoundError(f"no instrument {key!r} in the reference snapshot")
    chain = load_chains(ctx, [iid])[iid]
    if chain is None:
        raise NotFoundError(f"no option chain for {iid} on {ctx.session.date}")
    if expiry not in {e.date for e in chain.expiries}:
        raise NotFoundError(f"no {expiry} expiry in the chain of {iid} on {chain.session}")
    rows = underlying_quotes(ctx.reader, chain.session, [iid])
    under: dict[str, Any] = records(rows)[0] if rows is not None and len(rows) else {}
    price = next((float(under[c]) for c in ("price", "close") if under.get(c) is not None), None)
    taken = datetime.fromisoformat(under["ts"]) if under.get("ts") else None
    symbol = str(under["symbol"]) if under.get("symbol") else None
    frame = pd.DataFrame([asdict(q) for q in load_quotes(ctx, [iid], expiry)[iid]])
    return _Stored(iid, symbol, chain.session, price, taken, frame)


def _with_ids(
    found: pd.DataFrame, stored: pd.DataFrame, underlying_id: str, expiry: date
) -> pd.DataFrame:
    """The feed's rows with the stored contract ids, the underlying and the expiry."""
    ids = stored[["right", "strike", "instrument_id"]].drop_duplicates(["right", "strike"])
    frame = found.assign(strike=found["strike"].astype(float)).merge(
        ids.assign(strike=ids["strike"].astype(float)), on=["right", "strike"], how="left"
    )
    frame = frame.assign(underlying_id=underlying_id, expiry=expiry)
    return frame.sort_values(["strike", "right"], kind="stable").reset_index(drop=True)


def _fallback(
    stored: _Stored, expiry: date, strikes: list[float], status: str, detail: str
) -> LiveOptionChain:
    frame = stored.frame[stored.frame["strike"].astype(float).isin(strikes)]
    frame = frame.assign(listed=True, close=None).sort_values(["strike", "right"], kind="stable")
    return LiveOptionChain(
        underlying_id=stored.underlying_id,
        symbol=stored.symbol,
        expiry=expiry,
        source="stored",
        status=status,
        detail=detail,
        as_of=stored.taken,
        delayed=True,
        session=stored.session,
        underlying_price=stored.price,
        strikes=strikes,
        quotes=records(frame.reindex(columns=list(QUOTE_COLUMNS))),
    )


def _snapshot(frame: pd.DataFrame, stored: _Stored, at: datetime, kind: int) -> pd.DataFrame:
    """The rows to record: listed contracts the stored chain names, taken at ``at``."""
    listed = frame[frame["listed"].astype(bool) & frame["instrument_id"].notna()]
    columns = ["instrument_id", "underlying_id", "expiry", "right", "strike", "bid", "ask",
               "last", "close", "volume", "iv", "delta", "conid"]  # fmt: skip
    return listed.reindex(columns=columns).assign(
        ts=pd.Timestamp(at), symbol=stored.symbol, market_data_type=kind
    )
