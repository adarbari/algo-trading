"""``/instruments`` and ``/chains``: one instrument's detail, bars, events, feature series and
option chain."""

from datetime import date
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
