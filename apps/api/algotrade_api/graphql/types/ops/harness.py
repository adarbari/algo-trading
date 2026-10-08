"""``HarnessRun`` (one edge evaluation run for the Admin tab: whose, when, what it measured and
what it left out) and its rows (the Edges page's ``EdgeRow``, read by run)."""

import datetime as dt
from typing import Self

import strawberry
from anyio import to_thread
from strawberry.types import Info

from algotrade.services.read.context import Stores
from algotrade.services.read.ops import harness_runs
from algotrade_api.graphql.types.evaluation.edge import EdgeRow


@strawberry.type(
    description="One edge evaluation run of any status: `user` whose run (`site`: the shared "
    "one), `splitFrom` and `exploratory`, `variants` and `horizons` measured, `sessions` the "
    "most any variant measured, the left-out counts `unclosed`, `excludedCoverage` (no screen "
    "run or input tables), `scoreCoverage` (lowest share of eligible names scored) and "
    "`noEntryBar`, `trials` counted and `knowledgeTs` (null counts: not recorded)"
)
class HarnessRun:
    run_id: str
    edge_id: str
    user: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    range_from: dt.date | None
    range_to: dt.date
    split_from: dt.date | None
    exploratory: bool
    variants: list[str]
    horizons: list[int]
    sessions: int | None
    unclosed: int | None
    excluded_coverage: int | None
    score_coverage: float | None
    no_entry_bar: int | None
    trials: int | None
    knowledge_ts: dt.datetime
    as_of: str | None
    ctx: strawberry.Private[Stores]

    @classmethod
    def of(cls, d: harness_runs.HarnessRun, ctx: Stores) -> Self:
        return cls(
            run_id=d.run_id,
            edge_id=d.edge_id,
            user=d.user,
            status=d.status,
            started_at=d.started_at,
            finished_at=d.finished_at,
            range_from=d.range_from,
            range_to=d.range_to,
            split_from=d.split_from,
            exploratory=d.exploratory,
            variants=list(d.variants),
            horizons=list(d.horizons),
            sessions=d.sessions,
            unclosed=d.unclosed,
            excluded_coverage=d.excluded_coverage,
            score_coverage=d.score_coverage,
            no_entry_bar=d.no_entry_bar,
            trials=d.trials,
            knowledge_ts=d.knowledge_ts,
            as_of=d.as_of,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The rows the run wrote, one per variant, horizon and slice; empty: the "
        "run's partition holds none"
    )
    async def rows(self, info: Info) -> list[EdgeRow]:
        found = await to_thread.run_sync(harness_runs.load_harness_run_rows, self.ctx, self.run_id)
        return [EdgeRow.of(r) for r in found or ()]
