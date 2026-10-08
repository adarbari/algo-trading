"""``Edge`` (an edge document with its status), ``EdgeRun`` (one committed evaluation run, read
by run: its id, range, split, ``knowledgeTs`` and ``asOf`` disclosed) and ``EdgeRow`` (one
stored row of it). ``Edge.canonicalRun`` is the latest site run at the edge's frozen period, else
``canonicalNotRun`` says why (NOT_RUN, ADR 0036)."""

import datetime as dt
from typing import Self

import strawberry
from anyio import to_thread
from strawberry.types import Info

from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import edges, runs
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
    "record), `knowledgeTs` when it committed, `asOf` the data version it read"
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
            run=d,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The rows the run wrote, one per variant, horizon and slice; empty: the "
        "run's partition holds none"
    )
    async def rows(self, info: Info) -> list[EdgeRow]:
        found = await to_thread.run_sync(runs.load_run_rows, self.ctx, self.run)
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
    "implement it, its `frozenFrom` (null: no frozen period) and the run it cites"
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
    edge: strawberry.Private[edges.Edge]
    ctx: strawberry.Private[Stores]

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
            edge=d,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The latest committed site run whose split is `frozenFrom`; null: none "
        "(see `canonicalNotRun`). An exploratory or older split is never shown here"
    )
    def canonical_run(self, info: Info) -> EdgeRun | None:
        found = runs.load_canonical_run(self.ctx, self.edge)
        return EdgeRun.of(found.run, self.ctx) if found.run is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Why it has no canonical run (NOT_RUN); null: it has one"
    )
    def canonical_not_run(self, info: Info) -> Unknown | None:
        found = runs.load_canonical_run(self.ctx, self.edge)
        return Unknown.of(found.not_run) if found.not_run is not None else None

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every committed run of the edge the user sees (theirs, then the site's), "
        "newest first, exploratory ones flagged"
    )
    def runs(self, info: Info) -> list[EdgeRun]:
        return [EdgeRun.of(r, self.ctx) for r in runs.load_edge_runs(self.ctx, self.edge)]
