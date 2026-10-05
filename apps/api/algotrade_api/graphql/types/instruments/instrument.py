"""``Instrument``: who an instrument is for the session (typed identity, ADR 0038), its
values by catalogue name (``features(names)``) and the objects of its detail pane: events,
option chain, ETF holdings, price and feature series, the user's screeners that picked it
(ADR 0037), each through the request's dataloader for it (a list of instruments reads each
once, not once per instrument)."""

import datetime as dt
from typing import TYPE_CHECKING, Annotated, Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments import identity
from algotrade.services.read.instruments.prices import Adjustment
from algotrade_api.graphql.limits import MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.instruments.chain import OptionChain
from algotrade_api.graphql.types.instruments.event import Event
from algotrade_api.graphql.types.instruments.feature import FeatureValue
from algotrade_api.graphql.types.instruments.holdings import Holdings
from algotrade_api.graphql.types.instruments.series import FeatureSeries, PriceSeries

if TYPE_CHECKING:  # the screens' types name Instrument: resolved lazily (no import cycle)
    from algotrade_api.graphql.types.screens.hit import ScreenerHit


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

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Stored events (earnings, dividends, splits, reference changes) with "
        "their event date in `start..end` (null: unbounded), oldest first"
    )
    async def events(
        self, info: Info, start: dt.date | None = None, end: dt.date | None = None
    ) -> list[Event]:
        found = await self.ctx.loaders.events.load((self.instrument_id, start, end))
        return [Event.of(e) for e in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The option chain stored for the session (null: none stored for it)"
    )
    async def chain(self, info: Info) -> OptionChain | None:
        found = await self.ctx.loaders.chains.load((self.instrument_id,))
        return OptionChain.of(found, self.ctx) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="An ETF's `top` largest holdings as of the issuer's date the session "
        "sees (null: not an ETF)",
        extensions=[MaxItems("top", MAX_PAGE)],
    )
    async def holdings(self, info: Info, top: int = 10) -> Holdings | None:
        found = await self.ctx.loaders.holdings.load((self.instrument_id, top))
        return Holdings.of(found, self.ctx) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Daily bars of `start..end` (`end` null: the session's date), adjusted"
    )
    async def prices(
        self,
        info: Info,
        start: dt.date,
        end: dt.date | None = None,
        adjustment: Adjustment = Adjustment.SPLITS,
    ) -> PriceSeries:
        found = await self.ctx.loaders.prices.load((self.instrument_id, start, end, adjustment))
        return PriceSeries.of(found)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="`names` (catalogue features with a history: not instrument.*) per "
        "stored session of `start..end` (`end` null: the session's date)",
        extensions=[MaxItems("names", MAX_NAMES)],
    )
    async def series(
        self, info: Info, names: list[FeatureName], start: dt.date, end: dt.date | None = None
    ) -> FeatureSeries:
        found = await self.ctx.loaders.series.load((self.instrument_id, tuple(names), start, end))
        return FeatureSeries.of(found)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's screeners that picked it in the session (each one's run for "
        "exactly the session), by screener id; empty: none did, or none ran"
    )
    async def screener_hits(
        self, info: Info
    ) -> list[Annotated["ScreenerHit", strawberry.lazy("algotrade_api.graphql.types.screens.hit")]]:
        from algotrade_api.graphql.types.screens.hit import ScreenerHit  # noqa: PLC0415

        found = await self.ctx.loaders.screener_hits.load((self.instrument_id,))
        return [ScreenerHit.of(h, self.ctx) for h in found]
