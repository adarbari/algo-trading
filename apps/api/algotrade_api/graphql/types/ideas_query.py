"""The Ideas reads of the root ``Query`` (a part of it, to keep ``query.py`` under the file cap):
``ideas`` (the Unproven pool of a tab) and ``setupIdeas`` (a tab's list from the picks of
setups, ADR 0083)."""

import strawberry

from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.ideas import picks as setup_picks
from algotrade.services.read.screens import ideas
from algotrade.services.read.screens.ideas import FIRST_PAGE as IDEAS_FIRST_PAGE
from algotrade_api.graphql.limits import MAX_FILTERS, MAX_IDEAS_PAGE, MaxItems
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.query_args import Ctx, Day
from algotrade_api.graphql.types.screens.ideas import Ideas
from algotrade_api.graphql.types.screens.setup_ideas import IdeaTab, SetupIdeas


@strawberry.type
class IdeasQuery:
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The tickers the user's screeners picked in the session, ranked by the "
        "Ideas rule (a screener's first picks, weighted by position and by whose screener it "
        "is; each idea is served from its best pick) (`first` of them from the `after` "
        "cursor, `nextCursor` the next page's); a screener with no run for the session is "
        "listed NOT_RUN. `filters` (the surface `ideas` of `filterSet`) narrow the whole list "
        "before it is paged: `total` then counts the ideas that pass, `facets` the counts "
        "(ADR 0082); a cursor is only good for the filters it was issued under. `tab` keeps "
        "the screeners of that tab (the Unproven section of `setupIdeas`, ADR 0083); none: "
        "every screener. Null: nothing stored",
        extensions=[MaxItems("first", MAX_IDEAS_PAGE), MaxItems("filters", MAX_FILTERS)],
    )
    async def ideas(
        self,
        info: Ctx,
        first: int = IDEAS_FIRST_PAGE,
        after: str | None = None,
        filters: list[FilterInput] | None = None,
        tab: IdeaTab | None = None,
        date: Day = None,
    ) -> Ideas | None:
        ctx = await info.context.aread(date)
        given = tuple(filters or ())
        # Off the event loop (a whole-run read); the items' `features` loads still batch.
        load = ideas.load_ideas
        kind = tab.value if tab is not None else None
        found = await off_loop(load, ctx, first, after, given, kind) if ctx is not None else None
        return Ideas.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="One Ideas tab (Stocks or Premium) for the session, built from the picks of "
        "the setups whose stored verdict is works or promising, one ranking rule, at most 15 "
        "(ADR 0083 decision 2): the setups with what each picked, the ideas, and the setups "
        "and picks left out by kind. `state` unproven: no setup of the tab qualifies, the page "
        "shows `ideas(tab)` as Unproven. Null: nothing stored"
    )
    async def setup_ideas(self, info: Ctx, tab: IdeaTab, date: Day = None) -> SetupIdeas | None:
        ctx = await info.context.aread(date)
        found = (
            await off_loop(setup_picks.load_setup_picks, ctx, tab.value)
            if ctx is not None
            else None
        )
        return SetupIdeas.of(found, ctx) if found is not None and ctx is not None else None
