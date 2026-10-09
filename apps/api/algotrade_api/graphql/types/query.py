"""``Query``: the root of the graph. Each top-level field takes the session as its ``date``
argument (default: the latest with bars), opens the request's read context for it once
(``info.context.read``) and hands it to the objects it returns (ADR 0036: every value below
is for exactly that session). Fields over configs and run records (the catalogue, configs,
backtests, the user's screens, the nightly runs and run records) are not session data: they
take no ``date`` and read the request's session-free context (``info.context.stores()``), so
they answer on a store with no market data yet. The Admin reads about a session (its quality
checks and verification, the completeness window ending at it, one completeness cell, the
review lists over its reference snapshot) take ``date`` like any other. Every Admin field
is ``AdminOnly`` (ADR 0040: a trader gets ``FORBIDDEN``)."""

import datetime as dt
from typing import Annotated

import strawberry
from strawberry.types import Info

from algotrade.services.read.evaluation import edges as edge_reads
from algotrade.services.read.evaluation import runs as edge_runs
from algotrade.services.read.evaluation import split as split_reads
from algotrade.services.read.events import event_calendar
from algotrade.services.read.events.instrument_events import DEFAULT_DAYS
from algotrade.services.read.guide import entries as entries_page
from algotrade.services.read.guide import field as field_page
from algotrade.services.read.guide import index as guide_contents
from algotrade.services.read.guide import playbook as playbook_page
from algotrade.services.read.guide import regime as regime_page
from algotrade.services.read.guide import search as guide_search
from algotrade.services.read.guide import situation as situation_page
from algotrade.services.read.guide import written as written_page
from algotrade.services.read.instruments import catalogue, distribution, identity
from algotrade.services.read.instruments import table as tables
from algotrade.services.read.market import market
from algotrade.services.read.ops import (
    backtests,
    configs,
    harness_runs,
    ingestion,
    quality,
    review,
    runs,
    usage,
)
from algotrade.services.read.regime import regime
from algotrade.services.read.screens import documents, ideas, screeners, views
from algotrade.services.read.users.viewer import load_viewer
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.limits import MAX_DAYS, MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.offload import INLINE, off_loop
from algotrade_api.graphql.permissions import AdminOnly
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.evaluation.edge import Edge, EdgeRun
from algotrade_api.graphql.types.evaluation.split import EvaluationSplit
from algotrade_api.graphql.types.events.calendar import EventCalendar
from algotrade_api.graphql.types.guide.entries import GuideEntries
from algotrade_api.graphql.types.guide.episode import GuideEpisodeDetail
from algotrade_api.graphql.types.guide.field import GuideField
from algotrade_api.graphql.types.guide.index import GuideIndex
from algotrade_api.graphql.types.guide.indicator import GuideIndicatorDetail
from algotrade_api.graphql.types.guide.playbook import GuidePlaybookDetail
from algotrade_api.graphql.types.guide.search import GuideSearch
from algotrade_api.graphql.types.guide.situation import GuideSituationDetail
from algotrade_api.graphql.types.guide.written import GuideStartPage, GuideTerm
from algotrade_api.graphql.types.instruments.distribution import FeatureDistribution
from algotrade_api.graphql.types.instruments.feature import FeatureInfo
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.instruments.table import FeatureTable
from algotrade_api.graphql.types.market.market import Market
from algotrade_api.graphql.types.market.regime import MarketRegime
from algotrade_api.graphql.types.ops.backtest import Backtest, BacktestDetail
from algotrade_api.graphql.types.ops.config import Config
from algotrade_api.graphql.types.ops.harness import HarnessRun
from algotrade_api.graphql.types.ops.ingestion import CellDetail, Completeness
from algotrade_api.graphql.types.ops.quality import QualityReport, Verification
from algotrade_api.graphql.types.ops.review import ReviewList
from algotrade_api.graphql.types.ops.run import NightlyRun, RunDetail, RunItem
from algotrade_api.graphql.types.ops.usage import LlmUsage
from algotrade_api.graphql.types.screens.document import ScreenDetail, ScreenListing, ScreenVersion
from algotrade_api.graphql.types.screens.ideas import Ideas
from algotrade_api.graphql.types.screens.screener import Screener
from algotrade_api.graphql.types.screens.view import TableView
from algotrade_api.graphql.types.session import Session
from algotrade_api.graphql.types.users.viewer import Viewer

Day = Annotated[
    dt.date | None,
    strawberry.argument(
        description="the session to read (default: the latest with bars); every value "
        "below is for exactly this date"
    ),
]
Ctx = Info[RequestContext, None]
MAX_RUNS = 100  # nightlyRuns(limit)
MAX_SESSIONS = 60  # completeness(sessions)
MAX_CALLS = 200  # llmUsage(recent)
MAX_SEARCH = 50  # guideSearch(limit): hits per kind
MAX_QUERY = 200  # guideSearch(q): characters
MAX_REFS = 100  # guideEntries(refs)


@strawberry.type(description="Reads for the web app, each for one session (ADR 0036)")
class Query:
    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Who this request is for: the signed-in registry user, their role and "
        "workspaces (ADR 0040; not session data)",
        metadata=INLINE,  # no I/O: never queues behind the page's reads
    )
    def viewer(self, info: Ctx) -> Viewer:
        return Viewer.of(load_viewer(info.context.viewer))

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
        description="The tickers the user's screeners picked in the session, ranked by their "
        "screener priority then score (the first `limit`); a screener with no run for the "
        "session is listed NOT_RUN. Null: nothing stored",
        extensions=[MaxItems("limit", MAX_PAGE)],
    )
    async def ideas(self, info: Ctx, limit: int = 50, date: Day = None) -> Ideas | None:
        ctx = await info.context.aread(date)
        # Off the event loop (a whole-run read); the items' `features` loads still batch.
        found = await off_loop(ideas.load_ideas, ctx, limit) if ctx is not None else None
        return Ideas.of(found, ctx) if found is not None and ctx is not None else None

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
        found = await off_loop(regime.load_regime, ctx) if ctx is not None else None
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
        "field theme groups, intents, situations, playbooks by family, regime indicators and "
        "episodes (not session data)"
    )
    def guide_index(self, info: Ctx) -> GuideIndex | None:
        ctx = info.context.stores()
        return GuideIndex.of(guide_contents.load_guide_index(ctx)) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the catalogue field `name` (ADR 0051): its info and "
        "guide entry, related fields, the playbooks that use it and the situations that fool "
        "it; a name outside the caller's catalogue is an UNKNOWN_FEATURE error"
    )
    def guide_field(self, info: Ctx, name: FeatureName) -> GuideField | None:
        ctx = info.context.stores()
        return GuideField.of(field_page.load_guide_field(ctx, name)) if ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the site playbook `id` (ADR 0051): its prose, the "
        "preset's latest version and criteria, related playbooks and the situations that fool "
        "its fields; null: no site rule-screen preset of that id"
    )
    def guide_playbook(self, info: Ctx, id: str) -> GuidePlaybookDetail | None:
        ctx = info.context.stores()
        found = playbook_page.load_guide_playbook(ctx, id) if ctx is not None else None
        return GuidePlaybookDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The Guide page of the situation `slug` (ADR 0051): its signs and what to "
        "do, the fields it fools and the site playbooks reading them; null: no such situation"
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
        "episodes, glossary terms and Start here pages named by `refs` (at most 100), so a "
        "page's help buttons cost one request; a ref with no entry is left out",
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
        "that implement it and its evaluation runs; not session data"
    )
    def edges(self, info: Ctx) -> list[Edge]:
        ctx = info.context.stores()
        found = edge_reads.load_edges(ctx) if ctx is not None else ()
        return [Edge.of(e, ctx) for e in found] if ctx is not None else []

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The edge `id`; null: the user has no such edge"
    )
    def edge(self, info: Ctx, id: str) -> Edge | None:
        ctx = info.context.stores()
        found = edge_reads.load_edge(ctx, id) if ctx is not None else None
        return Edge.of(found, ctx) if found is not None and ctx is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The user's train / test split (their evaluation.toml), the frozen periods "
        "of the edges they see and the latest session a split may name; null: nothing stored"
    )
    def evaluation_split(self, info: Ctx) -> EvaluationSplit | None:
        ctx = info.context.read(None)
        return (
            EvaluationSplit.of(split_reads.load_evaluation_split(ctx)) if ctx is not None else None
        )

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
        # Off the event loop: one partition read per dataset and session of the window.
        found = (
            await off_loop(ingestion.load_completeness, ctx, sessions) if ctx is not None else None
        )
        return Completeness.of(found) if found is not None else None

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
