"""``/chains/{id}/live``: live quotes of one expiry, from IB Gateway or the stored chain
(ADR 0028)."""

from datetime import date, datetime

from pydantic import Field

from algotrade.services.read.availability.cause import ADMIN_CAUSE, GENERIC
from algotrade_api.schemas.health import Schema


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
    detail: str | None = Field(
        description="why the stored chain was served (admins; anyone else: generic words)",
        json_schema_extra={ADMIN_CAUSE: GENERIC},
    )
    as_of: datetime | None = Field(description="when the quotes were taken (UTC)")
    delayed: bool = Field(description="IB's delayed data, or the stored end-of-day chain")
    session: date = Field(description="the stored chain the contracts come from")
    underlying_price: float | None
    strikes: list[float]
    quotes: list[LiveOptionQuote] = Field(description="sorted by strike, then right")
