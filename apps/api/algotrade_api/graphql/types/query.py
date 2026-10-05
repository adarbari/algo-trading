"""``Query``: the root of the graph. Each top-level field takes the session as its ``date``
argument (default: the latest with bars), opens the request's read context for it once
(``info.context.read``) and hands it to the objects it returns (ADR 0036: every value below
is for exactly that session)."""

import datetime as dt
from typing import Annotated

import strawberry
from anyio import to_thread
from strawberry.types import Info

from algotrade.services.read.instruments import identity
from algotrade.services.read.screens import ideas, screeners, views
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.limits import MAX_PAGE, MaxItems
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.screens.ideas import Ideas
from algotrade_api.graphql.types.screens.screener import Screener
from algotrade_api.graphql.types.screens.view import TableView
from algotrade_api.graphql.types.session import Session

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
        description="The tickers the user's screeners picked in the session, ranked by their "
        "screener priority then score (the first `limit`); a screener with no run for the "
        "session is listed NOT_RUN. Null: nothing stored",
        extensions=[MaxItems("limit", MAX_PAGE)],
    )
    async def ideas(self, info: Ctx, limit: int = 50, date: Day = None) -> Ideas | None:
        ctx = info.context.read(date)
        # Off the event loop (a whole-run read); the items' `features` loads still batch.
        found = await to_thread.run_sync(ideas.load_ideas, ctx, limit) if ctx is not None else None
        return Ideas.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every rule screen the user sees (their own config, else the site "
        "preset), by id; each with its run for the session"
    )
    def screeners(self, info: Ctx, date: Day = None) -> list[Screener]:
        ctx = info.context.read(date)
        found = screeners.load_screeners(ctx) if ctx is not None else ()
        return [Screener.of(s, ctx) for s in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's saved view of the screener `scope`'s results (the default "
        "view, or the one called `name`); null: a screener the user does not see, or nothing "
        "stored yet"
    )
    def view(self, info: Ctx, scope: str, name: str | None = None) -> TableView | None:
        ctx = info.context.read(None)
        found = views.load_view(ctx, scope, name) if ctx is not None else None
        return TableView.of(found) if found is not None else None
