"""``Query``: the root of the graph. Each top-level field takes the session as its ``date``
argument (default: the latest with bars), opens the request's read context for it once
(``info.context.read``) and hands it to the objects it returns (ADR 0036: every value below
is for exactly that session)."""

import datetime as dt
from typing import Annotated

import strawberry
from strawberry.types import Info

from algotrade.services.read.instruments import identity
from algotrade.services.read.instruments import table as tables
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.limits import MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.instrument import Instrument
from algotrade_api.graphql.types.session import Session
from algotrade_api.graphql.types.table import FeatureTable

Day = Annotated[
    dt.date | None,
    strawberry.argument(
        description="the session to read (default: the latest with bars); every value "
        "below is for exactly this date"
    ),
]
Ctx = Info[RequestContext, None]


@strawberry.type(description="Reads for the web app, each for one session (ADR 0036)")
class Query:
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session `date` resolves to; null: nothing stored"
    )
    def session(self, info: Ctx, date: Day = None) -> Session | None:
        ctx = info.context.read(date)
        return Session.of(ctx.session) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The instrument `key` (an instrument id or a ticker) names in the "
        "session's reference snapshot; null: no such instrument"
    )
    def instrument(self, info: Ctx, key: str, date: Day = None) -> Instrument | None:
        ctx = info.context.read(date)
        # Sync on purpose: sibling fields resolve in one tick, so their `features` loads batch
        # into one read (the read itself runs off the event loop in the dataloader).
        found = identity.load_instrument(ctx, key) if ctx is not None else None
        return Instrument.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Instruments x `columns` (catalogue fields, in order) for the session: "
        "the universe, or the instruments `keys` (ids or tickers) name in that order; "
        "filtered (security type, sector, liquidity class, leveraged, optionable: "
        "case-insensitive; `q`: the symbol or name contains it), sorted by `sort` (`symbol` "
        "or a catalogue field, `-` prefix: descending, missing values last) and paged "
        "(`page` from 1, `size` rows). Null: nothing stored",
        extensions=[
            MaxItems("columns", MAX_NAMES),
            MaxItems("keys", MAX_PAGE),
            MaxItems("size", MAX_PAGE),
        ],
    )
    def table(
        self,
        info: Ctx,
        columns: list[FeatureName],
        keys: list[str] | None = None,
        security_type: str | None = None,
        sector: str | None = None,
        liquidity_class: str | None = None,
        leveraged: bool | None = None,
        optionable: bool | None = None,
        q: str | None = None,
        sort: str | None = None,
        page: int = 1,
        size: int = tables.DEFAULT_SIZE,
        date: Day = None,
    ) -> FeatureTable | None:
        ctx = info.context.read(date)
        filters = tables.UniverseFilter(
            security_type, leveraged, sector, liquidity_class, q, optionable
        )
        found = (
            tables.load_table(ctx, columns, filters, sort, page, size, keys)
            if ctx is not None
            else None
        )
        return FeatureTable.of(found, ctx) if found is not None and ctx is not None else None
