"""``Screener`` and ``ScreenerRun``: a rule screen the user sees (typed identity, config
bookkeeping, its criteria and display columns) and its run for the session, resolved through
the request's ``screener_latest_run`` dataloader (THE latest-run rule; none for the session is
``notRun``: ``NOT_RUN``, ADR 0036); a run's comparison with the previous run (``changes``,
``previousSession``) and its rows as a review table (``results``: filtered, sorted and paged on
the server)."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON
from strawberry.types import Info

from algotrade.services.read.availability.cause import public_audit
from algotrade.services.read.context import ReadContext
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.instruments.table import DEFAULT_SIZE
from algotrade.services.read.screens import pick_history as picks
from algotrade.services.read.screens import recent_runs as recent
from algotrade.services.read.screens import results, runs, screeners
from algotrade_api.graphql.limits import MAX_FILTERS, MAX_NAMES, MAX_PAGE, MaxItems
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.permissions import AdminCause
from algotrade_api.graphql.scalars import FeatureName
from algotrade_api.graphql.types.availability import Unavailable
from algotrade_api.graphql.types.evaluation.track_record import TrackRecord
from algotrade_api.graphql.types.instruments.feature import Unknown
from algotrade_api.graphql.types.screens.result import ChangeCount, ScreenGroup, ScreenResultPage


@strawberry.type(description="How many rows of a run got one decision")
class DecisionCount:
    decision: str
    count: int

    @classmethod
    def of(cls, d: runs.DecisionCount) -> Self:
        return cls(decision=d.decision, count=d.count)


@strawberry.type(
    description="The tickers a run picked, in rank order, without the rows behind them: "
    "`instrumentIds` (at most `size`) and `total`, the picks in all (the picks and the ones the "
    "regime gate held back)"
)
class PickIds:
    instrument_ids: list[str]
    total: int

    @classmethod
    def of(cls, d: runs.PickIds) -> Self:
        return cls(instrument_ids=list(d.instrument_ids), total=d.total)


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
        return JSON(results.run_audit(self.ctx, self.run))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The session of the previous run it is compared with; null: none (nothing "
        "is new or dropped)"
    )
    async def previous_session(self, info: Info) -> dt.date | None:
        # Off the event loop: a run before the frozen table recounts from two runs' rows.
        found = await off_loop(results.load_change_summary, self.ctx, self.run)
        return found.previous_session

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="How many tickers are `new` / `dropped` since the previous run, over the "
        "whole run; empty: no previous run"
    )
    async def changes(self, info: Info) -> list[ChangeCount]:
        found = await off_loop(results.load_change_summary, self.ctx, self.run)
        return [ChangeCount.of(c) for c in found.counts]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Who the run picked, read from the run's rows alone (cheap: no criterion "
        "values); `size` ids at most, in rank order",
        extensions=[MaxItems("size", MAX_PAGE)],
    )
    async def pick_ids(self, info: Info, size: int = DEFAULT_SIZE) -> PickIds:
        return PickIds.of(await off_loop(runs.load_pick_ids, self.ctx, self.run, size))

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its rows as a review table: `filters` (the surface `screener_results` of "
        "`filterSet`) and `q` (the symbol or name contains it) filtered, `decisions` and "
        "`change` (deprecated: the `decision` and `change` filters; `new` / `dropped`) "
        "likewise, over the whole run, with the counts in `facets` (ADR 0082), sorted by "
        "`sort` (`rank`, `score`, `symbol`, `decision`, `change`, `criterion:<id>`, "
        "`column:<name>` or a catalogue name; `-` prefix: descending; missing values last; "
        "default: rank) and paged (`page` from 1, `size` rows), with the catalogue `columns` "
        "for the page's rows",
        extensions=[
            MaxItems("columns", MAX_NAMES),
            MaxItems("size", MAX_PAGE),
            MaxItems("filters", MAX_FILTERS),
        ],
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
        filters: list[FilterInput] | None = None,
    ) -> ScreenResultPage:
        query = results.ResultQuery(tuple(decisions or ()), change, q, sort)
        # Off the event loop: the whole run is filtered and sorted (about 11k rows).
        found = await off_loop(
            results.load_result_page,
            self.ctx,
            self.run,
            query,
            columns or [],
            page,
            size,
            tuple(filters or ()),
        )
        return ScreenResultPage.of(found, self.ctx)


@strawberry.type(
    description="A criterion of a screen, in funnel order: the field it judges, its `mode` and "
    "its rule as the config states it: the operator `op` and the threshold `value` in the "
    "field's stored unit (a number, a string or boolean, a list for `in` / `between`; null: "
    "the operator takes none); `group` is the id of the group it sits in (null: a gate, ADR 0071)"
)
class ScreenCriterion:
    id: str
    field: str
    mode: str
    op: str
    value: JSON | None
    group: str | None

    @classmethod
    def of(cls, d: screeners.ScreenCriterion) -> Self:
        value = list(d.value) if isinstance(d.value, tuple) else d.value
        return cls(id=d.id, field=d.field, mode=d.mode, op=d.op, value=JSON(value), group=d.group)


@strawberry.type(description="A display column of a screen: its name and catalogue field")
class ScreenColumn:
    name: str
    field: str

    @classmethod
    def of(cls, d: screeners.ScreenColumn) -> Self:
        return cls(name=d.name, field=d.field)


@strawberry.type(
    description="One session of a screener's pick history: how many tickers its latest run of "
    "the session picked and how many the regime gate held back (`paused`); both null when it "
    "has no run for the session, and `notRun` says why (NOT_RUN)"
)
class PickCount:
    session: dt.date
    picked: int | None
    paused: int | None
    not_run: Unknown | None

    @classmethod
    def of(cls, d: picks.PickCount) -> Self:
        return cls(
            session=d.session,
            picked=d.picked,
            paused=d.paused,
            not_run=Unknown.of(d.not_run) if d.not_run is not None else None,
        )


strawberry.enum(
    recent.RunState,
    description="What a screener's run was for a session: COMPLETE (ran to the end), PARTIAL "
    "(ran with a gap, or its record is gone) or NOT_RUN",
)


@strawberry.type(
    description="One session of a screener's recent runs (the run line and session strip of its "
    "results page): `state`, `served` (the page's own session: the one `latestRun` shows; the "
    "others are history, read as their run record left them), and for a run its `runId`, "
    "`configVersion`, `picked` and `paused` (whole run), `newPicks` / `dropped` against its "
    "previous run (null: none, or not stored; never 0), `leftOutShare` (0 to 1: the share of "
    "names it could not judge for want of a value; null: not counted) and `unavailable` (what "
    "the tables it went without leave out); a session with no run has `state` NOT_RUN and "
    "`notRun` says why"
)
class RecentRun:
    session: dt.date
    state: recent.RunState
    served: bool
    run_id: str | None
    config_version: int | None
    picked: int | None
    paused: int | None
    new_picks: int | None
    dropped: int | None
    left_out_share: float | None
    unavailable: list[Unavailable]
    not_run: Unknown | None

    @classmethod
    def of(cls, d: recent.RecentRun) -> Self:
        return cls(
            session=d.session,
            state=d.state,
            served=d.served,
            run_id=d.run_id,
            config_version=d.config_version,
            picked=d.picked,
            paused=d.paused,
            new_picks=d.new_picks,
            dropped=d.dropped,
            left_out_share=d.left_out_share,
            unavailable=[Unavailable.of(u) for u in d.unavailable],
            not_run=Unknown.of(d.not_run) if d.not_run is not None else None,
        )


@strawberry.type(
    description="A rule screen as the user sees it (their own config, else the site preset): "
    "`owner` is whose runs are its; `criteria`, `groups` and `displayColumns` the current "
    "config's; `description` the one line saying what it finds (null: not written; not part of "
    "`hash`); "
    "`latestRun` its run for the session, else `notRun` says why (NOT_RUN); `pickHistory` its "
    "picked count per session over a window ending at the session; `recentRuns` its last runs "
    "for the run line and strip"
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
    groups: list[ScreenGroup]
    description: str | None
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
            groups=[ScreenGroup.of(g) for g in d.groups],
            description=d.description,
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

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its record over the frozen period of each edge that lists it, by edge id, "
        "from that edge's canonical run (never an exploratory run); an edge without one has an "
        "entry whose `notRun` says why; empty: no edge lists it"
    )
    async def track_records(self, info: Info) -> list[TrackRecord]:
        found = await self.ctx.loaders.track_records.load((self.id,))
        return [TrackRecord.of(t) for t in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its picked count for each of the last `sessions` (default 30, at most 90) "
        "exchange sessions ending at the session, oldest first, one entry per session: a "
        "session it did not run in has `picked` null and `notRun` says why (never an older "
        "run); a session with several runs counts the latest; each entry is what `latestRun` "
        "says at that session"
    )
    async def pick_history(
        self, info: Info, sessions: int = picks.DEFAULT_SESSIONS
    ) -> list[PickCount]:
        found = await self.ctx.loaders.screener_pick_history.load((self.owner, self.id, sessions))
        return [PickCount.of(p) for p in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Its run for each of the last `limit` (default 10, at most 10) exchange "
        "sessions ending at the session, oldest first, one entry per session: the history "
        "behind the run line, each as its run record left it (never an older run carried "
        "into a later session); the entry of the session is what `latestRun` says",
        extensions=[MaxItems("limit", recent.MAX_LIMIT)],
    )
    async def recent_runs(self, info: Info, limit: int = recent.DEFAULT_LIMIT) -> list[RecentRun]:
        found = await self.ctx.loaders.screener_recent_runs.load((self.owner, self.id, limit))
        return [RecentRun.of(r) for r in found]
