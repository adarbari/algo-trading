"""``Holdings``: what an ETF holds as of the issuer's date the session sees (ADR 0035): the
largest lines with their weights; a line in the universe links to its ``Instrument``
(through the request's ``instruments`` dataloader)."""

import datetime as dt
from typing import TYPE_CHECKING, Annotated, Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments import holdings

if TYPE_CHECKING:
    from algotrade_api.graphql.types.instrument import Instrument

LazyInstrument = Annotated["Instrument", strawberry.lazy("algotrade_api.graphql.types.instrument")]


@strawberry.type(
    description="One line of the fund: `symbol` the issuer's ticker, `weight` a fraction "
    "(negative: short); `instrument` when it is in the universe"
)
class Holding:
    rank: int
    name: str
    symbol: str | None
    instrument_id: str | None
    weight: float
    asset_class: str | None
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: holdings.Holding, ctx: ReadContext) -> Self:
        return cls(
            rank=d.rank,
            name=d.name,
            symbol=d.symbol,
            instrument_id=d.instrument_id,
            weight=d.weight,
            asset_class=d.asset_class,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The universe instrument the line is, for the session (null: not in "
        "the universe)"
    )
    async def instrument(self, info: Info) -> LazyInstrument | None:
        from algotrade_api.graphql.types.instrument import Instrument  # noqa: PLC0415

        found = await self.ctx.loaders.instruments.load((self.instrument_id or "",))
        return Instrument.of(found, self.ctx) if found is not None else None


@strawberry.type(
    description="An ETF's largest holdings as of the issuer's date `asOf` (null: none "
    "stored yet); `total` positions in the issuer's file, `source` who read it"
)
class Holdings:
    fund_id: str
    as_of: dt.date | None
    source: str | None
    total: int
    items: list[Holding]

    @classmethod
    def of(cls, d: holdings.Holdings, ctx: ReadContext) -> Self:
        return cls(
            fund_id=d.fund_id,
            as_of=d.as_of,
            source=d.source,
            total=d.total,
            items=[Holding.of(h, ctx) for h in d.items],
        )
