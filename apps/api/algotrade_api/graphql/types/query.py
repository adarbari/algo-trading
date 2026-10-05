"""``Query``: the root of the graph. Each top-level field takes the session as its ``date``
argument (default: the latest with bars), opens the request's read context for it once
(``info.context.read``) and hands it to the objects it returns (ADR 0036: every value below
is for exactly that session). Fields over configs and run records (the catalogue, configs,
backtests, the user's screens, the nightly runs and run records) are not session data: they
take no ``date`` and read the request's session-free context (``info.context.stores()``), so
they answer on a store with no market data yet. The Admin reads about a session (its quality
checks and verification, the completeness window ending at it, one completeness cell, the
review lists over its reference snapshot) take ``date`` like any other."""

import datetime as dt
from typing import Annotated

import strawberry
from anyio import to_thread
from strawberry.types import Info

from algotrade.services.read.instruments import catalogue, distribution, identity
from algotrade.services.read.instruments import table as tables
from algotrade.services.read.ops import backtests, configs, ingestion, quality, review, runs
from algotrade.services.read.screens import documents, ideas, screeners, views
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.limits import MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.instruments.distribution import FeatureDistribution
from algotrade_api.graphql.types.instruments.feature import FeatureInfo
from algotrade_api.graphql.types.instruments.instrument import Instrument
from algotrade_api.graphql.types.instruments.table import FeatureTable
from algotrade_api.graphql.types.ops.backtest import Backtest, BacktestDetail
from algotrade_api.graphql.types.ops.config import Config
from algotrade_api.graphql.types.ops.ingestion import CellDetail, Completeness
from algotrade_api.graphql.types.ops.quality import QualityReport, Verification
from algotrade_api.graphql.types.ops.review import ReviewList
from algotrade_api.graphql.types.ops.run import NightlyRun, RunDetail, RunItem
from algotrade_api.graphql.types.screens.document import ScreenDetail, ScreenListing, ScreenVersion
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
MAX_RUNS = 100  # nightlyRuns(limit)
MAX_SESSIONS = 60  # completeness(sessions)


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
        ctx = info.context.read(date)
        # Off the event loop: every instrument's value (a whole-population read).
        found = (
            await to_thread.run_sync(distribution.load_distribution, ctx, name)
            if ctx is not None
            else None
        )
        return FeatureDistribution.of(found) if found is not None else None

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
        description="The saved backtest run `runId`; null: no such backtest run"
    )
    async def backtest(self, info: Ctx, run_id: str) -> BacktestDetail | None:
        ctx = info.context.stores()
        # Off the event loop: the run's equity and fills are parquet reads.
        found = (
            await to_thread.run_sync(backtests.load_backtest, ctx, run_id)
            if ctx is not None
            else None
        )
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
        extensions=[MaxItems("limit", MAX_RUNS)],
    )
    def nightly_runs(self, info: Ctx, limit: int = 10) -> list[NightlyRun]:
        ctx = info.context.stores()
        found = runs.load_nightly_runs(ctx, limit) if ctx is not None else ()
        return [NightlyRun.of(r) for r in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The run record `runId` (any job): items summarised, failures grouped by "
        "reason; null: no such run"
    )
    def run(self, info: Ctx, run_id: str) -> RunDetail | None:
        ctx = info.context.stores()
        found = runs.load_run(ctx, run_id) if ctx is not None else None
        return RunDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every item of the run `runId` with its status, by key; null: no such run"
    )
    def run_items(self, info: Ctx, run_id: str) -> list[RunItem] | None:
        ctx = info.context.stores()
        found = runs.load_run_items(ctx, run_id) if ctx is not None else None
        return [RunItem.of(i) for i in found] if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session's data-quality checks (NOT_RUN when it has no data-quality "
        "run); null: nothing stored"
    )
    def quality(self, info: Ctx, date: Day = None) -> QualityReport | None:
        ctx = info.context.read(date)
        found = quality.load_quality(ctx) if ctx is not None else None
        return QualityReport.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session's live verification vs IBKR (NO_PARTITION when it did not "
        "run for the session); null: nothing stored"
    )
    async def verification(self, info: Ctx, date: Day = None) -> Verification | None:
        ctx = info.context.read(date)
        # Off the event loop: a parquet read and a group-by.
        found = (
            await to_thread.run_sync(quality.load_verification, ctx) if ctx is not None else None
        )
        return Verification.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Ingestion completeness: every dataset x the last `sessions` exchange "
        "sessions ending at the session; null: nothing stored",
        extensions=[MaxItems("sessions", MAX_SESSIONS)],
    )
    async def completeness(
        self, info: Ctx, sessions: int = 10, date: Day = None
    ) -> Completeness | None:
        ctx = info.context.read(date)
        # Off the event loop: one partition read per dataset and session of the window.
        found = (
            await to_thread.run_sync(ingestion.load_completeness, ctx, sessions)
            if ctx is not None
            else None
        )
        return Completeness.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="One completeness cell, `dataset` on the session `date`, with the reasons "
        "behind it; null: a dataset the grid does not list"
    )
    async def ingestion_cell(self, info: Ctx, dataset: str, date: dt.date) -> CellDetail | None:
        ctx = info.context.read(date)
        found = (
            await to_thread.run_sync(ingestion.load_cell_detail, ctx, dataset)
            if ctx is not None
            else None
        )
        return CellDetail.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Listings marked for FIGI review (the universe build's list on or before "
        "the session, else its reference snapshot); null: nothing stored"
    )
    def figi_review(self, info: Ctx, date: Day = None) -> ReviewList | None:
        ctx = info.context.read(date)
        found = review.load_figi_review(ctx) if ctx is not None else None
        return ReviewList.of(found) if found is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Active ETFs in the session's reference snapshot whose leverage the rules "
        "could not classify; null: nothing stored"
    )
    def leverage_review(self, info: Ctx, date: Day = None) -> ReviewList | None:
        ctx = info.context.read(date)
        found = review.load_leverage_review(ctx) if ctx is not None else None
        return ReviewList.of(found) if found is not None else None
