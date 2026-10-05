"""``Instrument``: who an instrument is for the session (typed identity, ADR 0038) and its
values by catalogue name (``features(names)``, through the request's ``features``
dataloader)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments import identity
from algotrade_api.graphql.limits import MAX_NAMES, MaxItems
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.instruments.feature import FeatureValue


@strawberry.type(
    description="An instrument as the session's reference snapshot has it. Per-session "
    "values (prices, earnings dates, flags, ...) are catalogue features: `features(names)`"
)
class Instrument:
    instrument_id: str
    symbol: str
    name: str
    security_type: str | None
    asset_class: str
    exchange: str | None
    is_etf: bool
    description: str | None
    reference_snapshot: dt.date
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: identity.Instrument, ctx: ReadContext) -> Self:
        return cls(
            instrument_id=d.instrument_id,
            symbol=d.symbol,
            name=d.name,
            security_type=d.security_type,
            asset_class=d.asset_class,
            exchange=d.exchange,
            is_etf=d.is_etf,
            description=d.description,
            reference_snapshot=d.reference_snapshot,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The values of `names` (catalogue fields, in the order asked) for the "
        "session; a name outside the caller's catalogue is an UNKNOWN_FEATURE error",
        extensions=[MaxItems("names", MAX_NAMES)],
    )
    async def features(self, info: Info, names: list[FeatureName]) -> list[FeatureValue]:
        found = await self.ctx.loaders.features.load((self.instrument_id, tuple(names)))
        return [FeatureValue.of(v) for v in found]
