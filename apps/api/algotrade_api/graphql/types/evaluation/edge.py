"""``Edge`` (an edge document with its status), ``EdgeRun`` (one committed evaluation run, read
by run: its id, range, split, ``knowledgeTs`` and ``asOf`` disclosed) and ``EdgeRow`` (one
stored row of it). ``Edge.canonicalRun`` is the latest site run at the edge's frozen period, else
``canonicalNotRun`` says why (NOT_RUN, ADR 0036); ``Edge.verdict`` judges it (ED8)."""

import asyncio
import datetime as dt
from typing import Any, Self

import strawberry
from strawberry.types import Info

from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import edges, runs, verdict
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.evaluation.verdict import EdgeDefinition, EdgeSource, EdgeVerdict
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="One stored row of a run: a screener or baseline (`variant`, its `role`) of an "
    "edge variant (`main`: the edge itself) over a horizon, for one slice (all, year, regime, "
    "frozen, split), with its measures (null: not stored); `exploratory`: the run's split is "
    "not the edge's frozen_from"
)
class EdgeRow:
    edge_variant: str
    variant: str
    role: str
    horizon_sessions: int
    slice_kind: str
    slice_value: str
    sessions: int | None
    picks: int | None
    hits: int | None
    trials: int | None
    pre_snapshot_sessions: int | None
    hit_rate: float | None
    base_rate: float | None
    lift: float | None
    mean_excess_picks: float | None
    decile_spread: float | None
    decile_t: float | None
    effect_size: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    pbo: float | None
    exploratory: bool

    @classmethod
    def of(cls, d: runs.EdgeRow) -> Self:
        return cls(
            edge_variant=d.edge_variant,
            variant=d.variant,
            role=d.role,
            horizon_sessions=d.horizon_sessions,
            slice_kind=d.slice_kind,
            slice_value=d.slice_value,
            sessions=d.sessions,
            picks=d.picks,
            hits=d.hits,
            trials=d.trials,
            pre_snapshot_sessions=d.pre_snapshot_sessions,
            hit_rate=d.hit_rate,
            base_rate=d.base_rate,
            lift=d.lift,
            mean_excess_picks=d.mean_excess_picks,
            decile_spread=d.decile_spread,
            decile_t=d.decile_t,
            effect_size=d.effect_size,
            sharpe=d.sharpe,
            deflated_sharpe=d.deflated_sharpe,
            pbo=d.pbo,
            exploratory=d.exploratory,
        )


@strawberry.type(
    description="A committed evaluation run of an edge, read as the run left it: `owner` whose "
    "run, `rangeFrom` / `rangeTo` the sessions covered, `splitFrom` the split its frozen slice "
    "was measured at, `exploratory` (its split is not the edge's frozenFrom: never a track "
    "record), `knowledgeTs` when it committed, `asOf` the data version it read, "
    "`afterSession` it committed "
    "after the request's session (false without one), `lostInputs` what the run could not read "
    "(a screener's missing table and the sessions lost)"
)
class EdgeRun:
    run_id: str
    edge_id: str
    owner: str
    status: str
    range_from: dt.date | None
    range_to: dt.date
    split_from: dt.date | None
    exploratory: bool
    knowledge_ts: dt.datetime
    as_of: str | None
    trials_counted: int | None
    after_session: bool
    lost_inputs: list[str]
    run: strawberry.Private[runs.EdgeRun]
    ctx: strawberry.Private[Stores]

    @classmethod
    def of(cls, d: runs.EdgeRun, ctx: Stores) -> Self:
        return cls(
            run_id=d.run_id,
            edge_id=d.edge_id,
            owner=d.owner,
            status=d.status,
            range_from=d.range_from,
            range_to=d.range_to,
            split_from=d.split_from,
            exploratory=d.exploratory,
            knowledge_ts=d.knowledge_ts,
            as_of=d.as_of,
            trials_counted=d.trials_counted,
            after_session=d.after_session,
            lost_inputs=list(d.lost_inputs),
            run=d,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The rows the run wrote, one per variant, horizon and slice; empty: the "
        "run's partition holds none"
    )
    async def rows(self, info: Info) -> list[EdgeRow]:
        found = await off_loop(runs.load_run_rows, self.ctx, self.run)
        return [EdgeRow.of(r) for r in found]


@strawberry.type(
    description="The run an evidenced or live edge cites and the split it was measured at"
)
class EdgeEvidence:
    run_id: str
    split_from: dt.date

    @classmethod
    def of(cls, d: edges.EdgeEvidence) -> Self:
        return cls(run_id=d.run_id, split_from=d.split_from)


@strawberry.type(
    description="An edge document (ADR 0053): status, thesis, the screeners and baselines that "
    "implement it, its `frozenFrom` (null: no frozen period) and the run it cites; `mine`: the "
    "user has a document of this id of their own, not only the site's"
)
class Edge:
    id: str
    name: str
    status: str
    thesis: str
    mechanism: str
    persistence: str
    schedule: str
    horizons: list[int]
    screeners: list[str]
    baselines: list[str]
    variants: list[str]
    frozen_from: dt.date | None
    evidence: EdgeEvidence | None
    rejection_reason: str
    sources: list[EdgeSource]
    definition: EdgeDefinition
    mine: bool
    edge: strawberry.Private[edges.Edge]
    ctx: strawberry.Private[Stores]
    cache: strawberry.Private[dict[str, Any]]

    @classmethod
    def of(cls, d: edges.Edge, ctx: Stores) -> Self:
        return cls(
            id=d.id,
            name=d.name,
            status=d.status,
            thesis=d.thesis,
            mechanism=d.mechanism,
            persistence=d.persistence,
            schedule=d.schedule,
            horizons=list(d.horizons),
            screeners=list(d.screeners),
            baselines=list(d.baselines),
            variants=list(d.variants),
            frozen_from=d.frozen_from,
            evidence=EdgeEvidence.of(d.evidence) if d.evidence else None,
            rejection_reason=d.rejection_reason,
            sources=[EdgeSource.of(x) for x in d.sources],
            definition=EdgeDefinition.of(d.definition),
            mine=d.mine,
            edge=d,
            ctx=ctx,
            cache={},
        )

    async def _canonical(self) -> runs.CanonicalRun:
        """The canonical run, read once per Edge object (off the event loop)."""
        if "canonical" not in self.cache:
            self.cache["canonical"] = asyncio.ensure_future(
                off_loop(runs.load_canonical_run, self.ctx, self.edge)
            )
        found: runs.CanonicalRun = await self.cache["canonical"]
        return found

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The latest committed site run whose split is `frozenFrom`; null: none "
        "(see `canonicalNotRun`). An exploratory or older split is never shown here"
    )
    async def canonical_run(self, info: Info) -> EdgeRun | None:
        found = await self._canonical()
        return EdgeRun.of(found.run, self.ctx) if found.run is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Why it has no canonical run (NOT_RUN); null: it has one"
    )
    async def canonical_not_run(self, info: Info) -> Unknown | None:
        found = await self._canonical()
        return Unknown.of(found.not_run) if found.not_run is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every committed run of the edge the user sees (theirs, then the site's), "
        "newest first, exploratory ones flagged"
    )
    async def runs(self, info: Info) -> list[EdgeRun]:
        found = await off_loop(runs.load_edge_runs, self.ctx, self.edge)
        return [EdgeRun.of(r, self.ctx) for r in found]

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The verdict on the official result (the canonical run): Works, Promising, "
        "Not working, Not enough data or Waiting on data, with the reason, the figures it rests "
        "on and its criteria (ED8)"
    )
    async def verdict(self, info: Info) -> EdgeVerdict:
        found = await off_loop(verdict.load_edge_verdict, self.ctx, self.edge)
        return EdgeVerdict.of(found)
