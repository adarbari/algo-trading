"""``Screener`` and ``ScreenerRun``: a rule screen the user sees (typed identity, config
bookkeeping, its criteria and display columns) and its run for the session, resolved through
the request's ``screener_latest_run`` dataloader (THE latest-run rule; none for the session is
``notRun``: ``NOT_RUN``, ADR 0036); a run's comparison with the previous run (``changes``,
``previousSession``) and its rows as a review table (``results``: filtered, sorted and paged on
the server)."""

import datetime as dt
from typing import Self

import strawberry
from anyio import to_thread
from strawberry.scalars import JSON
from strawberry.types import Info

from algotrade.services.read.availability.cause import public_audit
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.table import DEFAULT_SIZE
from algotrade.services.read.screens import results, runs, screeners
from algotrade_api.graphql.limits import MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.permissions import AdminCause
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.availability import Unavailable
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.screens.result import ChangeCount, ScreenResultPage


@strawberry.type(description="How many rows of a run got one decision")
class DecisionCount:
    decision: str
    count: int

    @classmethod
    def of(cls, d: runs.DecisionCount) -> Self:
        return cls(decision=d.decision, count=d.count)


@strawberry.type(
    description="A screener's run for the session: whose, which version ran, its run record's "
    "status and `audit` (coverage, the selection's audit), and every decision with its count "
    "over the whole run (`picked`: the tickers it picked, `paused`: the picks the regime gate "
    "held back, never counted as picked; `regime`: the label the run stamped, null when the "
    "gate was off or the label unknown); `coverage`: the run record's own coverage (COMPLETE, "
    "PARTIAL; null: not recorded); `unavailable`: what the tables that had no rows when it "
    "ran leave out, not the session's as read now"
)
class ScreenerRun:
    run_id: str
    config_id: str
    owner: str
    session: dt.date
    status: str | None
    knowledge_ts: dt.datetime
    config_version: int | None
    decisions: list[DecisionCount]
    picked: int
    paused: int
    regime: str | None
    coverage: str | None
    unavailable: list[Unavailable]
    run: strawberry.Private[runs.ScreenerRun]
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: runs.ScreenerRun, ctx: ReadContext) -> Self:
        return cls(
            run_id=d.run_id,
            config_id=d.config_id,
            owner=d.owner,
            session=d.session,
            status=d.status,
            knowledge_ts=d.knowledge_ts,
            config_version=d.config_version,
            decisions=[DecisionCount.of(c) for c in d.decisions],
            picked=d.picked,
            paused=d.paused,
            regime=d.regime,
            coverage=d.coverage,
            unavailable=[Unavailable.of(u) for u in d.unavailable],
            run=d,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The run record's audit (coverage, the selection's audit); without the "
        "tables the run went without unless the caller is an admin",
        extensions=[AdminCause(public=lambda _, audit: JSON(public_audit(audit)))],
    )
    def audit(self) -> JSON:
        return JSON(dict(self.run.audit))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session of the previous run it is compared with; null: none (nothing "
        "is new or dropped)"
    )
    async def previous_session(self, info: Info) -> dt.date | None:
        # Off the event loop: the previous run's rows are read and compared (about 11k).
        found = await to_thread.run_sync(results.load_run_changes, self.ctx, self.run)
        return found.previous_session

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="How many tickers are `new` / `dropped` since the previous run, over the "
        "whole run; empty: no previous run"
    )
    async def changes(self, info: Info) -> list[ChangeCount]:
        found = await to_thread.run_sync(results.load_run_changes, self.ctx, self.run)
        return [ChangeCount.of(c) for c in found.counts]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its rows as a review table: `decisions` (none: all; any case), `change` "
        "(`new` / `dropped`) and `q` (the symbol or name contains it) filtered, sorted by "
        "`sort` (`rank`, `score`, `symbol`, `decision`, `change`, `criterion:<id>`, "
        "`column:<name>` or a catalogue name; `-` prefix: descending; missing values last; "
        "default: rank) and paged (`page` from 1, `size` rows), with the catalogue `columns` "
        "for the page's rows",
        extensions=[MaxItems("columns", MAX_NAMES), MaxItems("size", MAX_PAGE)],
    )
    async def results(
        self,
        info: Info,
        decisions: list[str] | None = None,
        change: str | None = None,
        q: str | None = None,
        sort: str | None = None,
        columns: list[FeatureName] | None = None,
        page: int = 1,
        size: int = DEFAULT_SIZE,
    ) -> ScreenResultPage:
        query = results.ResultQuery(tuple(decisions or ()), change, q, sort)
        # Off the event loop: the whole run is filtered and sorted (about 11k rows).
        found = await to_thread.run_sync(
            results.load_result_page, self.ctx, self.run, query, columns or [], page, size
        )
        return ScreenResultPage.of(found, self.ctx)


@strawberry.type(description="A criterion of a screen, in funnel order: the field it judges")
class ScreenCriterion:
    id: str
    field: str
    mode: str

    @classmethod
    def of(cls, d: screeners.ScreenCriterion) -> Self:
        return cls(id=d.id, field=d.field, mode=d.mode)


@strawberry.type(description="A display column of a screen: its name and catalogue field")
class ScreenColumn:
    name: str
    field: str

    @classmethod
    def of(cls, d: screeners.ScreenColumn) -> Self:
        return cls(name=d.name, field=d.field)


@strawberry.type(
    description="A rule screen as the user sees it (their own config, else the site preset): "
    "`owner` is whose runs are its; `criteria` and `displayColumns` the current config's; "
    "`latestRun` its run for the session, else `notRun` says why (NOT_RUN)"
)
class Screener:
    id: str
    owner: str
    scope: str
    name: str
    version: int | None
    hash: str
    criteria: list[ScreenCriterion]
    display_columns: list[ScreenColumn]
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: screeners.Screener, ctx: ReadContext) -> Self:
        return cls(
            id=d.id,
            owner=d.owner,
            scope=d.scope,
            name=d.name,
            version=d.version,
            hash=d.hash,
            criteria=[ScreenCriterion.of(c) for c in d.criteria],
            display_columns=[ScreenColumn.of(c) for c in d.display_columns],
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its run for the session; null: not run for it (see `notRun`)"
    )
    async def latest_run(self, info: Info) -> ScreenerRun | None:
        found = await self.ctx.loaders.screener_latest_run.load((self.owner, self.id))
        return ScreenerRun.of(found.run, self.ctx) if found.run is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Why it has no run for the session (NOT_RUN); null: it has one"
    )
    async def not_run(self, info: Info) -> Unknown | None:
        found = await self.ctx.loaders.screener_latest_run.load((self.owner, self.id))
        return Unknown.of(found.not_run) if found.not_run is not None else None
