"""``OptionChain``: an underlying's stored chain for the session (expiries with their days to
expiry, strikes, the fetch status) and the quotes of one expiry (``quotes(expiry)``, through
the request's ``quotes`` dataloader). Facts about the chain per instrument (our IV30, the
underlying's price with the chain, the target expiry) are catalogue features
(``Instrument.features``), not chain fields."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments import chains


@strawberry.type(description="A listed expiry and its calendar days from the session")
class OptionExpiry:
    date: dt.date
    days: int

    @classmethod
    def of(cls, d: chains.OptionExpiry) -> Self:
        return cls(date=d.date, days=d.days)


@strawberry.type(
    description="One contract's stored quote; IV (a decimal) and Greeks as the feed computes them"
)
class OptionQuote:
    instrument_id: str
    expiry: dt.date
    right: str
    strike: float
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

    @classmethod
    def of(cls, d: chains.OptionQuote) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            expiry=d.expiry,
            right=d.right,
            strike=d.strike,
            bid=d.bid,
            ask=d.ask,
            last=d.last,
            volume=d.volume,
            open_interest=d.open_interest,
            iv=d.iv,
            delta=d.delta,
            gamma=d.gamma,
            theta=d.theta,
            vega=d.vega,
            rho=d.rho,
        )


@strawberry.type(
    description="An underlying's option chain as stored for the session (Cboe, delayed): "
    "`status` the chain run's"
)
class OptionChain:
    underlying_id: str
    session: dt.date
    status: str | None
    expiries: list[OptionExpiry]
    strikes: list[float]
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: chains.OptionChain, ctx: ReadContext) -> Self:
        return cls(
            underlying_id=d.underlying_id,
            session=d.session,
            status=d.status,
            expiries=[OptionExpiry.of(e) for e in d.expiries],
            strikes=list(d.strikes),
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The quotes of `expiry`, by strike then right (empty: not listed)"
    )
    async def quotes(self, info: Info, expiry: dt.date) -> list[OptionQuote]:
        found = await self.ctx.loaders.quotes.load((self.underlying_id, expiry))
        return [OptionQuote.of(q) for q in found]
