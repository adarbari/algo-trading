"""``Instrument``: who an instrument is for the session (typed identity, ADR 0038), its
values by catalogue name (``features(names)``) and the objects of its detail pane: events,
what is coming (``eventStudy``, ADR 0050), option chain, ETF holdings, price and feature
series, the user's screeners that picked it (ADR 0037), each through the request's dataloader
for it (a list of instruments reads each once, not once per instrument)."""

import datetime as dt
from typing import TYPE_CHECKING, Annotated, Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import ReadContext
from algotrade.services.read.events.instrument_events import DEFAULT_DAYS, DEFAULT_MONTHS
from algotrade.services.read.ideas import inverse
from algotrade.services.read.instruments import identity
from algotrade.services.read.instruments.prices import Adjustment
from algotrade.services.read.options.grid import load_option_grid
from algotrade_api.graphql.limits import MAX_DAYS, MAX_MONTHS, MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.events.event import Event
from algotrade_api.graphql.types.events.instrument_events import InstrumentEvents
from algotrade_api.graphql.types.instruments.chain import OptionChain
from algotrade_api.graphql.types.instruments.feature import FeatureValue
from algotrade_api.graphql.types.instruments.holdings import Holdings
from algotrade_api.graphql.types.instruments.series import FeatureSeries, PriceSeries
from algotrade_api.graphql.types.options.grid import OptionGridResult, result_of

if TYPE_CHECKING:  # the screens' types name Instrument: resolved lazily (no import cycle)
    from algotrade_api.graphql.types.screens.hit import ScreenerHit


@strawberry.type(
    description="A qualifying setup that picked the instrument: its `place` in the `tab`'s list "
    "and the `level` (verdict) it qualifies at"
)
class PickingSetup:
    edge_id: str
    edge_name: str
    tab: str
    level: str
    place: int

    @classmethod
    def of(cls, d: inverse.InstrumentSetup) -> Self:
        return cls(
            edge_id=d.edge_id, edge_name=d.edge_name, tab=d.tab, level=d.level, place=d.place
        )


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
        description="Stored events of `kinds` (default: the calendar kinds the page shows: "
        "earnings, dividends, splits, reference and index changes; a kind is a stored "
        "`events/<kind>` table, e.g. insider_transaction; "
        "an unknown kind is a BAD_REQUEST error) with "
        "their event date in `start..end` (null: unbounded), oldest first, among the rows "
        "known on or before the session (`known_from`, else the session that stored the row; "
        "ADR 0050); splits, dividends, reference and index changes unbounded (facts of record "
        "the adjusted prices use)",
        extensions=[MaxItems("kinds", MAX_NAMES)],
    )
    async def events(
        self,
        info: Info,
        start: dt.date | None = None,
        end: dt.date | None = None,
        kinds: list[str] | None = None,
    ) -> list[Event]:
        asked = None if kinds is None else tuple(kinds)
        found = await self.ctx.loaders.events.load((self.instrument_id, start, end, asked))
        return [Event.of(e) for e in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="What is coming for it as of the session (ADR 0050): the events of the "
        "next `days` calendar days (own and a fund's reference earnings, macro releases, "
        "market-structure days), its 8-Ks of the last `months`, the 7-90 day expiry ladder "
        "and a leveraged fund's reference, with the parts not known for the session",
        extensions=[MaxItems("days", MAX_DAYS), MaxItems("months", MAX_MONTHS)],
    )
    async def event_study(
        self, info: Info, days: int = DEFAULT_DAYS, months: int = DEFAULT_MONTHS
    ) -> InstrumentEvents | None:
        found = await self.ctx.loaders.instrument_events.load((self.instrument_id, days, months))
        return InstrumentEvents.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The option chain stored for the session (null: none stored for it)"
    )
    async def chain(self, info: Info) -> OptionChain | None:
        found = await self.ctx.loaders.chains.load((self.instrument_id,))
        return OptionChain.of(found, self.ctx) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The option grid for the session (ADR 0083 amendment 2026-11-01): puts and "
        "calls at our delta bands and expiry buckets, derived figures only (never a vendor "
        "bid, ask, last or size); or why there is none"
    )
    async def option_grid(self, info: Info) -> OptionGridResult:
        return result_of(await off_loop(load_option_grid, self.ctx, self.instrument_id))

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

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The setups with a stored verdict of Works or Promising that picked it in "
        "the session (ADR 0083 decision 2: the inverse of Ideas, same licence filter), "
        "strongest first; empty: none did"
    )
    async def picked_by(self, info: Info) -> list[PickingSetup]:
        return [
            PickingSetup.of(d)
            for d in inverse.load_setups_of_instrument(self.ctx, self.instrument_id)
        ]
