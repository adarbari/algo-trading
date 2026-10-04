"""``/instruments`` and ``/chains``: one instrument's detail, bars, events, feature series and
option chain, stored or live."""

from datetime import date, datetime
from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Schema


class InstrumentDetail(Schema):
    instrument_id: str
    reference_snapshot: date
    reference: dict[str, Any]
    company: dict[str, Any] | None
    features: dict[str, Any]
    feature_sessions: dict[str, date]


class Bar(Schema):
    ts: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None


class BarSeries(Schema):
    instrument_id: str
    adjustment: str
    start: date
    end: date
    items: list[Bar]


class InstrumentEvent(Schema):
    table: str
    ts: str
    values: dict[str, Any]


class FeatureSeries(Schema):
    instrument_id: str
    names: list[str]
    start: date
    end: date
    items: list[dict[str, Any]]


class OptionQuote(Schema):
    instrument_id: str
    expiry: date | None
    right: str | None
    strike: float | None
    bid: float | None
    ask: float | None
    last: float | None
    volume: float | None
    open_interest: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None


class OptionChain(Schema):
    underlying_id: str
    session: date
    status: str | None = Field(description="the chain fetch status (OK, NO_CHAIN, STALE_DATA: ...)")
    underlying: dict[str, Any] | None = Field(
        description="the underlying quote with the chain (Cboe iv30 in percent)"
    )
    our_iv: dict[str, Any] | None = Field(
        description="our iv30 rollup row for the session (decimal)"
    )
    expiries: list[date]
    strikes: list[float]
    quotes: list[OptionQuote] = Field(description="sorted by expiry, strike, right")


class LiveOptionQuote(Schema):
    instrument_id: str | None = Field(description="the contract's id in the stored chain")
    expiry: date
    right: str = Field(description="C or P")
    strike: float
    listed: bool = Field(description="false: IB has no such contract")
    bid: float | None
    ask: float | None
    last: float | None
    close: float | None = Field(description="IB's previous close (live answers only)")
    volume: float | None
    iv: float | None = Field(description="implied vol, decimal (IB's model, or Cboe's stored)")
    delta: float | None = Field(description="IB's model delta, or the stored chain's")


class LiveOptionChain(Schema):
    underlying_id: str
    symbol: str | None
    expiry: date
    source: str = Field(description="ibkr: read live from IB Gateway; stored: the stored chain")
    status: str = Field(
        description="LIVE, CACHED (a live answer under live_cache_s old), DISABLED, "
        "UNAVAILABLE (gateway down, busy or slow), ERROR: the last three serve the stored chain"
    )
    detail: str | None = Field(description="why the stored chain was served")
    as_of: datetime | None = Field(description="when the quotes were taken (UTC)")
    delayed: bool = Field(description="IB's delayed data, or the stored end-of-day chain")
    session: date = Field(description="the stored chain the contracts come from")
    underlying_price: float | None
    strikes: list[float]
    quotes: list[LiveOptionQuote] = Field(description="sorted by strike, then right")
