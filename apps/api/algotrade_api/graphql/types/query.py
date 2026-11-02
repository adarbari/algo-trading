"""``Query``: the root of the graph. Each top-level field takes the session as its ``date``
argument (default: the latest with bars), opens the request's read context for it once
(``info.context.read``) and hands it to the objects it returns (ADR 0036: every value below
is for exactly that session). Fields over configs and run records (the catalogue, configs,
backtests, the user's screens, the nightly runs and run records) are not session data: they
take no ``date`` and read the request's session-free context (``info.context.stores()``), so
they answer on a store with no market data yet. The Admin reads about a session (quality checks,
verification, the completeness window and cell, the review lists) take ``date`` like any other.
Every Admin field is ``AdminOnly`` (ADR 0040: a trader gets ``FORBIDDEN``); more: ``AdminReads``."""

import datetime as dt
from functools import partial
from typing import Annotated

import strawberry

from algotrade.services.read.coverage import known_values
from algotrade.services.read.edge_desk import desk as edge_desk
from algotrade.services.read.edge_desk import live as edge_live
from algotrade.services.read.edge_ledger import trades as edge_trade_reads
from algotrade.services.read.edge_ledger import variants as edge_variant_reads
from algotrade.services.read.evaluation import edges as edge_reads
from algotrade.services.read.evaluation import runs as edge_runs
from algotrade.services.read.evaluation import versions
from algotrade.services.read.events import event_calendar
from algotrade.services.read.events.instrument_events import DEFAULT_DAYS
from algotrade.services.read.filtering import served
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.formulas import accepted as accepted_formulas
from algotrade.services.read.guide import entries as entries_page
from algotrade.services.read.guide import field as field_page
from algotrade.services.read.guide import index as guide_contents
from algotrade.services.read.guide import regime as regime_page
from algotrade.services.read.guide import search as guide_search
from algotrade.services.read.guide import situation as situation_page
from algotrade.services.read.guide import written as written_page
from algotrade.services.read.guide.edges import edge as edge_page
from algotrade.services.read.guide.edges import index as edge_index_page
from algotrade.services.read.guide.edges import mechanism as mechanism_page
from algotrade.services.read.guide.screeners import category as screener_category_page
from algotrade.services.read.guide.screeners import index as screener_index_page
from algotrade.services.read.guide.screeners import screener as screener_page
from algotrade.services.read.instruments import catalogue, distribution, identity
from algotrade.services.read.instruments import table as tables
from algotrade.services.read.lists import edges as list_edges
from algotrade.services.read.lists import screeners as list_screeners
from algotrade.services.read.market import market
from algotrade.services.read.ops import (
    backtests,
    configs,
    feature_requests,
    ingestion,
    quality,
    review,
    runs,
    usage,
)
from algotrade.services.read.ops.admin_runs import harness_runs, screener_runs
from algotrade.services.read.ops.admin_runs.screener_runs import RunStatus
from algotrade.services.read.regime import regime
from algotrade.services.read.screens import documents, screeners, views
from algotrade.services.read.users.appearance import load_appearance
from algotrade.services.read.users.viewer import load_viewer
from algotrade_api.graphql.context import selects
from algotrade_api.graphql.limits import (
    MAX_DAYS,
    MAX_FILTERS,
    MAX_NAMES,
    MAX_PAGE,
    MaxItems,
)
from algotrade_api.graphql.offload import INLINE, off_loop
from algotrade_api.graphql.permissions import AdminOnly
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.admin_query import AdminReads
from algotrade_api.graphql.types.coverage.known_values import KnownCoverage
from algotrade_api.graphql.types.evaluation.edge import Edge, EdgeProblem, EdgeRun
from algotrade_api.graphql.types.evaluation.evidence import (
    EdgeTradePage,
    EdgeVariants,
)
from algotrade_api.graphql.types.evaluation.paper import EdgeDesk, EdgePaper
from algotrade_api.graphql.types.evaluation.result import EdgeResult
from algotrade_api.graphql.types.events.calendar import EventCalendar
from algotrade_api.graphql.types.filtering.filter_set import FilterableFeature, FilterSet
from algotrade_api.graphql.types.guide.edges.edge import GuideEdgeEntry
from algotrade_api.graphql.types.guide.edges.index import GuideEdgeIndex
from algotrade_api.graphql.types.guide.edges.mechanism import GuideMechanism
from algotrade_api.graphql.types.guide.entries import GuideEntries
from algotrade_api.graphql.types.guide.episode import GuideEpisodeDetail
from algotrade_api.graphql.types.guide.field import GuideField
from algotrade_api.graphql.types.guide.index import GuideIndex
from algotrade_api.graphql.types.guide.indicator import GuideIndicatorDetail
from algotrade_api.graphql.types.guide.screeners.category import GuideScreenerCategory
from algotrade_api.graphql.types.guide.screeners.index import GuideScreenerIndex
from algotrade_api.graphql.types.guide.screeners.screener import GuideScreenerDetail
from algotrade_api.graphql.types.guide.search import GuideSearch
from algotrade_api.graphql.types.guide.situation import GuideSituationDetail
from algotrade_api.graphql.types.guide.written import GuideStartPage, GuideTerm
from algotrade_api.graphql.types.ideas_query import IdeasQuery
from algotrade_api.graphql.types.instruments.distribution import FeatureDistribution
from algotrade_api.graphql.types.instruments.feature import FeatureInfo
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.instruments.table import FeatureTable
from algotrade_api.graphql.types.lists.edge_list import EdgeList
from algotrade_api.graphql.types.lists.screener_list import ScreenerList
from algotrade_api.graphql.types.market.market import Market
from algotrade_api.graphql.types.market.regime import MarketRegime
from algotrade_api.graphql.types.ops.accepted_formulas import AcceptedFormulaList
from algotrade_api.graphql.types.ops.admin_runs.harness import HarnessRun
from algotrade_api.graphql.types.ops.admin_runs.screener_run import ScreenerRunEntry
from algotrade_api.graphql.types.ops.backtest import Backtest, BacktestDetail
from algotrade_api.graphql.types.ops.config import Config
from algotrade_api.graphql.types.ops.feature_requests import FeatureRequestList
from algotrade_api.graphql.types.ops.ingestion import CellDetail, ChainCoverage, Completeness
from algotrade_api.graphql.types.ops.quality import QualityReport, Verification
from algotrade_api.graphql.types.ops.review import ReviewList
from algotrade_api.graphql.types.ops.run import NightlyRun, RunDetail, RunItem
from algotrade_api.graphql.types.ops.usage import LlmUsage
from algotrade_api.graphql.types.query_args import Ctx, Day
from algotrade_api.graphql.types.screens.document import ScreenDetail, ScreenListing, ScreenVersion
from algotrade_api.graphql.types.screens.screener import Screener
from algotrade_api.graphql.types.screens.view import TableView
from algotrade_api.graphql.types.session import Session
from algotrade_api.graphql.types.users.appearance import Appearance
from algotrade_api.graphql.types.users.feature_requests import MyFeatureRequest
from algotrade_api.graphql.types.users.viewer import Viewer

MAX_RUNS = 100  # nightlyRuns(limit)
MAX_SESSIONS = 60  # completeness(sessions)
MAX_CALLS = 200  # llmUsage(recent)
MAX_SEARCH = 50  # guideSearch(limit): hits per kind
MAX_QUERY = 200  # guideSearch(q): characters
MAX_REFS = 100  # guideEntries(refs)


@strawberry.type(description="Reads for the web app, each for one session (ADR 0036)")
class Query(IdeasQuery, AdminReads):
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Who this request is for: the signed-in registry user, their role and "
        "workspaces (ADR 0040; not session data)",
        metadata=INLINE,  # no I/O: never queues behind the page's reads
    )
    def viewer(self, info: Ctx) -> Viewer:
        return Viewer.of(load_viewer(info.context.viewer))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The theme the user chose (`light`, `dark` or `system`; ADR 0085): "
        "`system` when nothing valid is stored. Per user, not session data; not part of `viewer`, "
        "which has no I/O"
    )
    def appearance(self, info: Ctx) -> Appearance:
        ctx = info.context.stores()
        return (
            Appearance.of(load_appearance(ctx)) if ctx is not None else Appearance(theme="system")
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session `date` resolves to; null: nothing stored"
    )
    def session(self, info: Ctx, date: Day = None) -> Session | None:
        ctx = info.context.read(date)
        return Session.of(ctx.session, ctx) if ctx is not None else None

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
        "filtered (`filters`: the surface `universe` of `filterSet`, over the whole list, "
        "with the counts in the result's `facets`; `securityType`, `sector`, `liquidityClass`, "
        "`leveraged` and `optionable` are deprecated, they are those filters, text "
        "case-insensitive; `q`: the symbol or name contains it), sorted by `sort` (`symbol` "
        "or a catalogue field, `-` prefix: descending, missing values last) and paged "
        "(`page` from 1, `size` rows). Null: nothing stored",
        extensions=[
            MaxItems("columns", MAX_NAMES),
            MaxItems("keys", MAX_PAGE),
            MaxItems("size", MAX_PAGE),
            MaxItems("filters", MAX_FILTERS),
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
        filters: list[FilterInput] | None = None,
        date: Day = None,
    ) -> FeatureTable | None:
        ctx = info.context.read(date)
        old = tables.UniverseFilter(
            security_type, leveraged, sector, liquidity_class, q, optionable
        )
        found = (
            tables.load_table(ctx, columns, old, sort, page, size, keys, tuple(filters or ()))
            if ctx is not None
            else None
        )
        return FeatureTable.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The events ahead of a set of names over the next `days` calendar days, "
        "one entry per day (ADR 0050): the names `instrumentIds` give (a screen's results, a "
        "list) plus, with `scope`, the site's scope list config/site/events/scope.toml only (no "
        "tier A / B names); the names' own and reference "
        "earnings on their rows, macro releases and market-structure days once. Null: nothing "
        "stored",
        extensions=[MaxItems("instrument_ids", MAX_PAGE), MaxItems("days", MAX_DAYS)],
    )
    async def event_calendar(
        self,
        info: Ctx,
        instrument_ids: list[str],
        scope: bool = False,
        days: int = DEFAULT_DAYS,
        date: Day = None,
    ) -> EventCalendar | None:
        ctx = await info.context.aread(date)
        load = event_calendar.load_event_calendar  # off the event loop: one read per source
        found = await off_loop(load, ctx, instrument_ids, days, scope) if ctx is not None else None
        return EventCalendar.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The US market for the session: the market-entity features by catalogue "
        "name (ADR 0047). Null: nothing stored"
    )
    def market(self, info: Ctx, date: Day = None) -> Market | None:
        ctx = info.context.read(date)
        return Market.of(market.load_market(ctx), ctx) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The market regime for the session as weather (Clear, Clouds building, "
        "Storm, Severe storm), with its scores, indicator cards and sizing rule; UNKNOWN with "
        "its reason when not computed for the session (ADR 0047). Null: nothing stored"
    )
    async def regime(self, info: Ctx, date: Day = None) -> MarketRegime | None:
        ctx = await info.context.aread(date)
        # Off the event loop: the market rows and the cards file.
        found = (
            await off_loop(partial(regime.load_regime, provenance=False), ctx)
            if ctx is not None
            else None
        )
        return MarketRegime.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every rule screen the user sees (their own config, else the site "
        "preset), by id; each with its run for the session"
    )
    def screeners(self, info: Ctx, date: Day = None) -> list[Screener]:
        ctx = info.context.read(date)
        found = screeners.load_screeners(ctx) if ctx is not None else ()
        return [Screener.of(s, ctx) for s in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Screeners list: the screeners the user sees whose id, name or "
        "description contains `q` (any case) and that pass `filters` (the surface `screeners` "
        "of `filterSet`), by id, with the counts of the filter bar (ADR 0082)",
        extensions=[MaxItems("filters", MAX_FILTERS), MaxItems("q", MAX_QUERY)],
    )
    async def screener_list(
        self,
        info: Ctx,
        filters: list[FilterInput] | None = None,
        q: str | None = None,
        date: Day = None,
    ) -> ScreenerList | None:
        ctx = await info.context.aread(date)
        found = (
            await off_loop(list_screeners.load_screener_list, ctx, tuple(filters or ()), q)
            if ctx is not None
            else None
        )
        return ScreenerList.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The rule screen `id` as the user sees it (their own config, else the site "
        "preset), with its run for the session; null: no such screener, or nothing stored"
    )
    def screener(self, info: Ctx, id: str, date: Day = None) -> Screener | None:
        ctx = info.context.read(date)
        found = screeners.load_screener(ctx, id) if ctx is not None else None
        return Screener.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's saved view of the table `scope` (`screener:<id>`: a "
        "screener's results; the default view, or the one called `name`); null: a scope of "
        "no known kind, a screener the user does not see, or nothing stored yet"
    )
    def view(self, info: Ctx, scope: str, name: str | None = None) -> TableView | None:
        ctx = info.context.read(None)
        found = views.load_view(ctx, scope, name) if ctx is not None else None
        return TableView.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The filters of `surface` (ideas, screener_results, universe) for the "
        "caller: the ones they may use with their options and bins, and the ones a data "
        "licence withholds (ADR 0082). `withFeatures`: catalogue fields (`rollup.<group>@v<N>."
        "<column>`, `feature.<name>`) the caller made filters of (the id `feature:<field>`): each "
        "is served too, in the group `more`, when the surface takes features. A filter whose "
        "field has no known value for the session is in `withheld` (NOT_STORED) until it has "
        "data. Not found: no such surface",
        extensions=[MaxItems("withFeatures", MAX_FILTERS)],
    )
    def filter_set(
        self, info: Ctx, surface: str, with_features: list[str] | None = None, date: Day = None
    ) -> FilterSet | None:
        ctx = info.context.read(date) or info.context.stores()
        found = (
            served.load_filter_set_with(ctx, surface, with_features) if ctx is not None else None
        )
        return FilterSet.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The catalogue fields the caller may filter `surface` on by search (More "
        "filters): each with the control it gets, its Guide entry and the words a trader uses "
        "for it (the phrasebook); a field a data licence does not cover is not listed. Empty: "
        "the surface takes no features. Not found: no such surface"
    )
    def filter_features(self, info: Ctx, surface: str) -> list[FilterableFeature]:
        ctx = info.context.stores()
        found = served.load_filterable_features(ctx, surface) if ctx is not None else ()
        return [FilterableFeature.of(f) for f in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The caller's feature catalogue (the site's fields plus their own "
        "expression features), in catalogue order"
    )
    def catalogue(self, info: Ctx) -> list[FeatureInfo]:
        ctx = info.context.stores()
        found = catalogue.load_catalogue(ctx) if ctx is not None else ()
        return [FeatureInfo.of(f) for f in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The catalogue field `name` across instruments for the session; a name "
        "outside the caller's catalogue is an UNKNOWN_FEATURE error. Null: nothing stored"
    )
    async def distribution(
        self, info: Ctx, name: FeatureName, date: Day = None
    ) -> FeatureDistribution | None:
        ctx = await info.context.aread(date)
        # Off the event loop: every instrument's value (a whole-population read).
        found = (
            await off_loop(distribution.load_distribution, ctx, name) if ctx is not None else None
        )
        return FeatureDistribution.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="What the Guide holds, in its order (ADR 0051): sections with entry counts, "
        "field theme groups, intents, situations, screeners by family, regime indicators and "
        "episodes (not session data)"
    )
    def guide_index(self, info: Ctx) -> GuideIndex | None:
        ctx = info.context.stores()
        return GuideIndex.of(guide_contents.load_guide_index(ctx)) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the catalogue field `name` (ADR 0051): its info and "
        "guide entry, related fields, the screeners that use it and the situations that fool "
        "it; a name outside the caller's catalogue is an UNKNOWN_FEATURE error"
    )
    def guide_field(self, info: Ctx, name: FeatureName) -> GuideField | None:
        ctx = info.context.stores()
        return GuideField.of(field_page.load_guide_field(ctx, name)) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the site screener `id` (ADR 0051): its prose, the "
        "preset's latest version and criteria, related screeners and the situations that fool "
        "its fields; null: no site rule-screen preset of that id"
    )
    def guide_screener(self, info: Ctx, id: str) -> GuideScreenerDetail | None:
        ctx = info.context.stores()
        found = screener_page.load_guide_screener(ctx, id) if ctx is not None else None
        return GuideScreenerDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Screeners section's lead page (ADR 0051): what a screener is, how it "
        "differs from an edge and a card per family with its screener count; no live number"
    )
    def guide_screener_index(self, info: Ctx) -> GuideScreenerIndex | None:
        ctx = info.context.stores()
        found = screener_index_page.load_guide_screener_index(ctx) if ctx is not None else None
        return GuideScreenerIndex.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the screener family `id` (ADR 0051): its purpose and "
        "intro and its site screeners as rows (what each asks, the edges that use it); null: "
        "no such family"
    )
    def guide_screener_category(self, info: Ctx, id: str) -> GuideScreenerCategory | None:
        ctx = info.context.stores()
        found = (
            screener_category_page.load_guide_screener_category(ctx, id)
            if ctx is not None
            else None
        )
        return GuideScreenerCategory.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the situation `slug` (ADR 0051): its signs and what to "
        "do, the fields it fools and the site screeners reading them; null: no such situation"
    )
    def guide_situation(self, info: Ctx, slug: str) -> GuideSituationDetail | None:
        ctx = info.context.stores()
        found = situation_page.load_guide_situation(ctx, slug) if ctx is not None else None
        return GuideSituationDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the regime indicator `key` (ADR 0051): its card's "
        "explanation without a session value, how it is computed, the field it reads and its "
        "reading list; null: no such card"
    )
    def guide_indicator(self, info: Ctx, key: str) -> GuideIndicatorDetail | None:
        ctx = info.context.stores()
        found = regime_page.load_guide_indicator(ctx, key) if ctx is not None else None
        return GuideIndicatorDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the reference episode `slug` (its key, ADR 0051): the "
        "episode as its config holds it and the indicators whose before-line is about it; "
        "null: no such episode"
    )
    def guide_episode(self, info: Ctx, slug: str) -> GuideEpisodeDetail | None:
        ctx = info.context.stores()
        found = regime_page.load_guide_episode(ctx, slug) if ctx is not None else None
        return GuideEpisodeDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Edges section's top page (ADR 0051): the mechanism cards in order with "
        "their edges as rows, the filters with counts and the edges set aside with their "
        "reasons; site edges only, no live number"
    )
    def guide_edge_index(self, info: Ctx) -> GuideEdgeIndex | None:
        ctx = info.context.stores()
        found = edge_index_page.load_guide_edge_index(ctx) if ctx is not None else None
        return GuideEdgeIndex.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the mechanism `id` (ADR 0051): why an edge should work, "
        "the research, real against decoy, the sources and the site edges that rest on it; "
        "null: no such mechanism"
    )
    def guide_mechanism(self, info: Ctx, id: str) -> GuideMechanism | None:
        ctx = info.context.stores()
        found = mechanism_page.load_guide_mechanism(ctx, id) if ctx is not None else None
        return GuideMechanism.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the site edge `id` (ADR 0051), from its document alone: "
        "thesis, the other side of the trade, why it lasts, the published figure with a planning "
        "haircut, how it is tested and built, what fools it, sources and related edges; a "
        "user's own edge is never served; null: no such site edge"
    )
    def guide_edge(self, info: Ctx, id: str) -> GuideEdgeEntry | None:
        ctx = info.context.stores()
        found = edge_page.load_guide_edge(ctx, id) if ctx is not None else None
        return GuideEdgeEntry.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The glossary term `id` (ADR 0051): its entry, the body linked and the "
        "terms it refers to; null: no such term"
    )
    def guide_term(self, info: Ctx, id: str) -> GuideTerm | None:
        ctx = info.context.stores()
        found = written_page.load_guide_term(ctx, id) if ctx is not None else None
        return GuideTerm.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Start here page `id` (ADR 0051): its entry, the sections linked and "
        "the Guide entries it links to; null: no such page"
    )
    def guide_start_page(self, info: Ctx, id: str) -> GuideStartPage | None:
        ctx = info.context.stores()
        found = written_page.load_guide_start_page(ctx, id) if ctx is not None else None
        return GuideStartPage.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Many Guide entries in one read (ADR 0051): the regime indicators, "
        "episodes, mechanisms, edges, glossary terms and Start here pages named by `refs` (at "
        "most 100), so a page's help buttons cost one request; a ref with no entry is left out",
        extensions=[MaxItems("refs", MAX_REFS)],
    )
    def guide_entries(self, info: Ctx, refs: list[entries_page.GuideRef]) -> GuideEntries | None:
        ctx = info.context.stores()
        found = entries_page.load_guide_entries(ctx, refs) if ctx is not None else None
        return GuideEntries.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Search every Guide entry for `q` (ADR 0051): at most `limit` results per "
        "kind, grouped by kind, ranked exact name, then name or title, then intent or theme, "
        "then prose (case-insensitive); not session data",
        extensions=[MaxItems("q", MAX_QUERY), MaxItems("limit", MAX_SEARCH)],
    )
    def guide_search(self, info: Ctx, q: str, limit: int = 5) -> GuideSearch | None:
        ctx = info.context.stores()
        found = guide_search.load_guide_search(ctx, q, limit) if ctx is not None else None
        return GuideSearch.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every strategy and screener config the user sees: site presets, then "
        "their own (`kind`: only `strategy` or `screener`)"
    )
    def configs(self, info: Ctx, kind: str | None = None) -> list[Config]:
        ctx = info.context.stores()
        found = configs.load_configs(ctx, kind) if ctx is not None else ()
        return [Config.of(c) for c in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every saved backtest run of the strategy configs the user sees, newest first"
    )
    def backtests(self, info: Ctx) -> list[Backtest]:
        ctx = info.context.stores()
        found = backtests.load_backtests(ctx) if ctx is not None else ()
        return [Backtest.of(b) for b in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every edge the user sees (ADR 0053), by id: status, thesis, the screeners "
        "that implement it and its evaluation runs; not session data. `ids`: only those edges"
    )
    def edges(self, info: Ctx, ids: list[str] | None = None) -> list[Edge]:
        ctx = info.context.stores()
        found = edge_reads.load_edges(ctx, ids) if ctx is not None else ()
        return [Edge.of(e, ctx) for e in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Edges list: the edges the user sees whose id, name or thesis contains "
        "`q` (any case) and that pass `filters` (the surface `edges` of `filterSet`: the old "
        "views are the filters `mine`, `followed` and the status `rejected`), by id, with the "
        "counts of the filter bar (ADR 0082). A session is read for the live state; null: "
        "nothing stored",
        extensions=[MaxItems("filters", MAX_FILTERS), MaxItems("q", MAX_QUERY)],
    )
    async def edge_list(
        self,
        info: Ctx,
        filters: list[FilterInput] | None = None,
        q: str | None = None,
        date: Day = None,
    ) -> EdgeList | None:
        ctx = await info.context.aread(date)
        found = (
            await off_loop(list_edges.load_edge_list, ctx, tuple(filters or ()), q)
            if ctx is not None
            else None
        )
        return EdgeList.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's own edge files `edges` leaves out (or reads only in part), by id, "
        "with the reason; empty: every file of theirs loads"
    )
    def edge_problems(self, info: Ctx) -> list[EdgeProblem]:
        ctx = info.context.stores()
        found = edge_reads.load_edge_problems(ctx) if ctx is not None else ()
        return [EdgeProblem.of(p) for p in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Ideas signals of the edges the user follows or owns for the session: what "
        "to buy (the paper trades signalled on it), what to sell next session and each edge's "
        "live record. Paper trades follow the edge's owner: a followed site edge shows the one "
        "site record every follower sees, an own edge the user's own. Null: nothing stored"
    )
    async def edge_desk(self, info: Ctx, date: Day = None) -> EdgeDesk | None:
        ctx = await info.context.aread(date)
        found = await off_loop(edge_desk.load_edge_desk, ctx) if ctx is not None else None
        return EdgeDesk.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The paper record of the edge `id` as the session knew it, the owner's: the "
        "site's for a site edge (the same for every follower), the user's for their own edge. "
        "The live record against the backtest's usual range, the trades and, for a trial, the "
        "forward test; null: no such edge or nothing stored"
    )
    async def edge_paper(self, info: Ctx, id: str, date: Day = None) -> EdgePaper | None:
        ctx = await info.context.aread(date)
        found = await off_loop(edge_live.load_edge_paper, ctx, id) if ctx is not None else None
        return EdgePaper.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The trades of the verdict's basis of the edge `edgeId` (the screen and "
        "holding "
        "period its verdict rests on: never chosen here), one `page` (from 1) of the trades that "
        "pass `filters` (the surface `edge_trades` of `filterSet`, applied to the whole ledger "
        "before it is sorted and paged: `total` counts the matches, `facets` the counts, ADR "
        "0082), sorted by the server (`descending`). `period` (deprecated: the filters "
        "`record` and `in_sample`) adds the filters it stands for unless they are set: `ALL` "
        "(the default) is the backtest's trades, `LIVE` the paper record as the session knew "
        "it; null reads backtest and live together. A per-name value under a licence the viewer "
        "lacks is Unknown(LICENCE) and never passes a filter on it; a copy's out-of-sample "
        "trades are withheld; null: no such edge",
        extensions=[MaxItems("filters", MAX_FILTERS)],
    )
    async def edge_trades(
        self,
        info: Ctx,
        edge_id: str,
        period: Annotated[
            edge_trade_reads.Period | None,
            strawberry.argument(deprecation_reason="use the filters record and in_sample"),
        ] = edge_trade_reads.Period.ALL,
        page: int = 1,
        sort: edge_trade_reads.Sort = edge_trade_reads.Sort.DECISION,
        descending: bool = False,
        filters: list[FilterInput] | None = None,
        date: Day = None,
    ) -> EdgeTradePage | None:
        ctx = await info.context.aread(date)
        found = (
            await off_loop(
                edge_trade_reads.load_trades_page,
                ctx,
                edge_id,
                period,
                page,
                sort.value,
                descending,
                tuple(filters or ()),
                selects(info, "facets"),
            )
            if ctx is not None
            else None
        )
        return EdgeTradePage.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The variant grid of the edge `edgeId`: every screen and holding period its "
        "official run tried, the verdict's basis marked official and every other out-of-sample "
        "figure flagged as not the pre-chosen test; null: no such edge"
    )
    async def edge_variants(self, info: Ctx, edge_id: str) -> EdgeVariants | None:
        ctx = await info.context.astores()
        found = (
            await off_loop(edge_variant_reads.load_trials_of, ctx, edge_id)
            if ctx is not None
            else None
        )
        return EdgeVariants.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The sections of the result of the edge `id` (the evidence curve, drawdown, "
        "rolling starts, monthly map and decay), each about the verdict's own run and basis and "
        "read only when selected. `date` resolves the session of the live stroke and bar only; "
        "null: the user has no such edge"
    )
    async def edge_result(self, info: Ctx, id: str, date: Day = None) -> EdgeResult | None:
        ctx = await info.context.aread(date)
        found = await off_loop(edge_reads.load_edge, ctx, id) if ctx is not None else None
        return EdgeResult.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The edge `id`; null: the user has no such edge"
    )
    def edge(self, info: Ctx, id: str) -> Edge | None:
        ctx = info.context.stores()
        found = edge_reads.load_edge(ctx, id) if ctx is not None else None
        return Edge.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The edge `id` as one whole TOML document (extends resolved, the user's "
        "state left out): what an admin lands in config/site/edges/ by pull request to publish "
        "it site-wide (the site's config changes only by PR); null: no such edge. `user`: "
        "whose copy (an admin may publish any user's; default: their own)",
        extensions=[AdminOnly()],
    )
    def published_edge_document(self, info: Ctx, id: str, user: str | None = None) -> str | None:
        ctx = info.context.stores_for(user)
        return versions.load_published_document(ctx, id) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every committed evaluation run of the edge `edgeId` the user sees (theirs, "
        "then the site's), newest first; empty: no such edge or no run. Read by run, as the "
        "run left it (never by session)"
    )
    def edge_runs(self, info: Ctx, edge_id: str) -> list[EdgeRun]:
        ctx = info.context.stores()
        found = edge_runs.load_runs_of(ctx, edge_id) if ctx is not None else ()
        return [EdgeRun.of(r, ctx) for r in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The saved backtest run `runId`; null: no such backtest run"
    )
    async def backtest(self, info: Ctx, run_id: str) -> BacktestDetail | None:
        ctx = await info.context.astores()
        # Off the event loop: the run's equity and fills are parquet reads.
        found = await off_loop(backtests.load_backtest, ctx, run_id) if ctx is not None else None
        return BacktestDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's own rule screens: finalised ones and draft-only ones (status "
        "DRAFT), by id"
    )
    def my_screens(self, info: Ctx) -> list[ScreenListing]:
        ctx = info.context.stores()
        found = documents.load_screen_listings(ctx) if ctx is not None else ()
        return [ScreenListing.of(s) for s in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The features the viewer's own Describe-it drafts listed as missing over the "
        "last year, one per feature, most recently asked first: their own history only, for every "
        "role (never another user's asks, counts or spans). A date range, not one session"
    )
    async def my_feature_requests(self, info: Ctx) -> list[MyFeatureRequest]:
        ctx = await info.context.astores()
        viewer = load_viewer(info.context.viewer)
        found = (
            await off_loop(feature_requests.load_my_requests, ctx, viewer)
            if ctx is not None
            else ()
        )
        return [MyFeatureRequest.of(r) for r in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's screen `screenerId` (or the site preset of that id they have "
        "not copied yet): draft, versions, preset pin, working copy. Null: no such screen"
    )
    def screen_detail(self, info: Ctx, screener_id: str) -> ScreenDetail | None:
        ctx = info.context.stores()
        found = documents.load_screen_detail(ctx, screener_id) if ctx is not None else None
        return ScreenDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The finalised versions of the user's screen `screenerId`, oldest first"
    )
    def screen_versions(self, info: Ctx, screener_id: str) -> list[ScreenVersion]:
        ctx = info.context.stores()
        found = documents.load_screen_versions(ctx, screener_id) if ctx is not None else ()
        return [ScreenVersion.of(v) for v in found]

    # ---------------------------------------------------------------- Admin (read-model PR 10)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The `limit` most recent nightly session runs, newest first",
        extensions=[AdminOnly(), MaxItems("limit", MAX_RUNS)],
    )
    def nightly_runs(self, info: Ctx, limit: int = 10) -> list[NightlyRun]:
        ctx = info.context.stores()
        found = runs.load_nightly_runs(ctx, limit) if ctx is not None else ()
        return [NightlyRun.of(r) for r in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The run record `runId` (any job): items summarised, failures grouped by "
        "reason; null: no such run",
        extensions=[AdminOnly()],
    )
    def run(self, info: Ctx, run_id: str) -> RunDetail | None:
        ctx = info.context.stores()
        found = runs.load_run(ctx, run_id) if ctx is not None else None
        return RunDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every item of the run `runId` with its status, by key; null: no such run",
        extensions=[AdminOnly()],
    )
    def run_items(self, info: Ctx, run_id: str) -> list[RunItem] | None:
        ctx = info.context.stores()
        found = runs.load_run_items(ctx, run_id) if ctx is not None else None
        return [RunItem.of(i) for i in found] if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session's data-quality checks (NOT_RUN when it has no data-quality "
        "run); null: nothing stored",
        extensions=[AdminOnly()],
    )
    def quality(self, info: Ctx, date: Day = None) -> QualityReport | None:
        ctx = info.context.read(date)
        found = quality.load_quality(ctx) if ctx is not None else None
        return QualityReport.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session's fundamentals share count known against the rows stored, by "
        "security type, with the causes of an operating company's gap (NOT_RUN when no "
        "nightly record of the session holds it); null: nothing stored",
        extensions=[AdminOnly()],
    )
    def known_coverage(self, info: Ctx, date: Day = None) -> KnownCoverage | None:
        ctx = info.context.read(date)
        found = known_values.load_known_coverage(ctx) if ctx is not None else None
        return KnownCoverage.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session's live verification vs IBKR (NO_PARTITION when it did not "
        "run for the session); null: nothing stored",
        extensions=[AdminOnly()],
    )
    async def verification(self, info: Ctx, date: Day = None) -> Verification | None:
        ctx = await info.context.aread(date)
        # Off the event loop: a parquet read and a group-by.
        found = await off_loop(quality.load_verification, ctx) if ctx is not None else None
        return Verification.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Ingestion completeness: every dataset x the last `sessions` exchange "
        "sessions ending at the session; null: nothing stored",
        extensions=[AdminOnly(), MaxItems("sessions", MAX_SESSIONS)],
    )
    async def completeness(
        self, info: Ctx, sessions: int = 10, date: Day = None
    ) -> Completeness | None:
        ctx = await info.context.aread(date)
        # The window only; `cells` (one partition read per dataset and session) resolves
        # lazily, so the status strip's selection never walks them.
        found = ingestion.load_completeness_window(ctx, sessions) if ctx is not None else None
        return Completeness.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="One completeness cell, `dataset` on the session `date`, with the reasons "
        "behind it; null: a dataset the grid does not list",
        extensions=[AdminOnly()],
    )
    async def ingestion_cell(self, info: Ctx, dataset: str, date: dt.date) -> CellDetail | None:
        ctx = await info.context.aread(date)
        found = (
            await off_loop(ingestion.load_cell_detail, ctx, dataset) if ctx is not None else None
        )
        return CellDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Option-chain coverage of the session (OK share of the optionable "
        "underlyings, by status and tier, the chronically stale names, drift); null: the "
        "session has no chains run",
        extensions=[AdminOnly()],
    )
    async def chain_coverage(self, info: Ctx, date: Day = None) -> ChainCoverage | None:
        ctx = await info.context.aread(date)
        # Off the event loop: six sessions of run records and one partition read.
        found = await off_loop(ingestion.load_chain_coverage, ctx) if ctx is not None else None
        return ChainCoverage.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Listings marked for FIGI review (the universe build's list on or before "
        "the session, else its reference snapshot); null: nothing stored",
        extensions=[AdminOnly()],
    )
    def figi_review(self, info: Ctx, date: Day = None) -> ReviewList | None:
        ctx = info.context.read(date)
        found = review.load_figi_review(ctx) if ctx is not None else None
        return ReviewList.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Active ETFs in the session's reference snapshot whose leverage the rules "
        "could not classify; null: nothing stored",
        extensions=[AdminOnly()],
    )
    def leverage_review(self, info: Ctx, date: Day = None) -> ReviewList | None:
        ctx = info.context.read(date)
        found = review.load_leverage_review(ctx) if ctx is not None else None
        return ReviewList.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="What the text model spent: tokens and cost against the budget, by model, "
        "use case and user, a 30-day series and the `recent` latest calls (newest first). A "
        "date range ending today, not one session (ADR 0058)",
        extensions=[AdminOnly(), MaxItems("recent", MAX_CALLS)],
    )
    async def llm_usage(self, info: Ctx, recent: int = 50) -> LlmUsage | None:
        ctx = await info.context.astores()
        found = await off_loop(usage.load_llm_usage, ctx, None, recent) if ctx is not None else None
        return LlmUsage.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The features traders asked for that the catalogue lacks, ranked (decayed "
        "distinct users x feasibility), over the last year up to today: a date range, not one "
        "session. Counts only, never a user or a span (ADR 0066)",
        extensions=[AdminOnly()],
    )
    async def feature_requests(self, info: Ctx) -> FeatureRequestList | None:
        ctx = await info.context.astores()
        viewer = load_viewer(info.context.viewer)
        found = (
            await off_loop(feature_requests.load_feature_requests, ctx, viewer)
            if ctx is not None
            else None
        )
        return FeatureRequestList.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The formulas traders accepted in Describe it, grouped by fingerprint, over "
        "the last year up to today: a date range, not one session. Most users first; each says "
        "the site feature it duplicates and the backlog item it exactly matches. Counts only, "
        "never a user (ADR 0066)",
        extensions=[AdminOnly()],
    )
    async def accepted_formulas(self, info: Ctx) -> AcceptedFormulaList | None:
        ctx = await info.context.astores()
        viewer = load_viewer(info.context.viewer)
        found = (
            await off_loop(accepted_formulas.load_accepted_formula_list, ctx, viewer)
            if ctx is not None
            else None
        )
        return AcceptedFormulaList.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The `limit` most recent edge evaluation runs of any status, newest first: "
        "every edge the user sees, for the site and every declared user",
        extensions=[AdminOnly(), MaxItems("limit", MAX_RUNS)],
    )
    def harness_runs(self, info: Ctx, limit: int = 50) -> list[HarnessRun]:
        ctx = info.context.stores()
        found = harness_runs.load_harness_runs(ctx, limit) if ctx is not None else ()
        return [HarnessRun.of(r, ctx) for r in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The edge evaluation run `runId`, with its rows; null: no such run",
        extensions=[AdminOnly()],
    )
    def harness_run(self, info: Ctx, run_id: str) -> HarnessRun | None:
        ctx = info.context.stores()
        found = harness_runs.load_harness_run(ctx, run_id) if ctx is not None else None
        return HarnessRun.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The `limit` most recent screener runs of any status, newest first: every "
        "screener of the site and every declared user, narrowed by `user` (whose), `screener` "
        "(config id) and `status` (the run record's). Ordered by the session a run screened (then "
        "its start), not by when it started: a backfill started today for an old session sorts "
        "below newer sessions and falls outside `limit` once that many newer runs match. Only the "
        f"latest {screener_runs.HISTORY_DAYS} days of sessions are searched: an older run is not "
        "returned, however few match",
        extensions=[AdminOnly(), MaxItems("limit", MAX_RUNS)],
    )
    def screener_runs(
        self,
        info: Ctx,
        limit: int = 50,
        user: str | None = None,
        screener: str | None = None,
        status: RunStatus | None = None,
    ) -> list[ScreenerRunEntry]:
        ctx = info.context.stores()
        found = (
            screener_runs.load_screener_runs(ctx, limit, user, screener, status)
            if ctx is not None
            else ()
        )
        return [ScreenerRunEntry.of(r, ctx) for r in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The screener run `runId`; null: no such run",
        extensions=[AdminOnly()],
    )
    def screener_run(self, info: Ctx, run_id: str) -> ScreenerRunEntry | None:
        ctx = info.context.stores()
        found = screener_runs.load_screener_run(ctx, run_id) if ctx is not None else None
        return ScreenerRunEntry.of(found, ctx) if found is not None and ctx is not None else None
