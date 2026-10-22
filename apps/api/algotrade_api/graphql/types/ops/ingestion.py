"""``Completeness`` (every dataset x a window of sessions: rows stored against rows expected),
``CellDetail`` (one dataset on one session with the reasons behind it) and ``ChainCoverage``
(the option chains fetched OK, the names the feed keeps serving stale)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.ops import ingestion
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.ops.run import FailureGroup, RunDetail


@strawberry.type(
    description="One dataset on one session: `status` COMPLETE, PARTIAL, MISSING or CARRIED; "
    "`present` rows stored, `expected` rows expected and `basis` what that is; `runIds` the "
    "stored runs the rows came from"
)
class IngestionCell:
    dataset: str
    session: dt.date
    status: str
    present: int
    expected: int | None
    basis: str
    run_ids: list[str]

    @classmethod
    def of(cls, d: ingestion.Cell) -> Self:
        return cls(
            dataset=d.dataset,
            session=d.session,
            status=d.status,
            present=d.present,
            expected=d.expected,
            basis=d.basis,
            run_ids=list(d.run_ids),
        )


@strawberry.type(
    description="Ingestion completeness: every dataset x the window's `sessions` (oldest "
    "first, ending at the session read); `lastClosed` the exchange's last closed session "
    "(later than the last of `sessions`: the store is stale)"
)
class Completeness:
    sessions: list[dt.date]
    datasets: list[str]
    last_closed: dt.date
    ctx: strawberry.Private[ReadContext]

    @classmethod
    def of(cls, d: ingestion.CompletenessWindow, ctx: ReadContext) -> Self:
        return cls(
            sessions=list(d.sessions),
            datasets=list(d.datasets),
            last_closed=d.last_closed,
            ctx=ctx,
        )

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="Every dataset x `sessions`: built (the partition walk) only when the "
        "query selects it"
    )
    async def cells(self) -> list[IngestionCell]:
        found = await off_loop(ingestion.load_cells, self.ctx, self.sessions)
        return [IngestionCell.of(c) for c in found]


@strawberry.type(
    description="One completeness cell with the reasons behind it: `job` the ingestion task "
    "that writes the dataset, `groups` its items not OK grouped by reason (chains: per "
    "underlying), `runs` the runs that wrote the partition and the job's runs that session"
)
class CellDetail:
    cell: IngestionCell
    job: str
    groups: list[FailureGroup]
    runs: list[RunDetail]

    @classmethod
    def of(cls, d: ingestion.CellDetail) -> Self:
        return cls(
            cell=IngestionCell.of(d.cell),
            job=d.job,
            groups=[FailureGroup.of(g) for g in d.groups],
            runs=[RunDetail.of(r) for r in d.runs],
        )


@strawberry.type(description="A chain status code and how many underlyings had it")
class ChainStatusCount:
    code: str
    count: int

    @classmethod
    def of(cls, d: ingestion.StatusCount) -> Self:
        return cls(code=d.code, count=d.count)


@strawberry.type(
    description="The chains of one tier (`core` or `rest`) of the session: fetched OK and stale"
)
class ChainTier:
    tier: str
    total: int
    ok: int
    stale: int

    @classmethod
    def of(cls, d: ingestion.TierCoverage) -> Self:
        return cls(tier=d.tier, total=d.total, ok=d.ok, stale=d.stale)


@strawberry.type(
    description="Option-chain coverage of the session: `ok` of `total` optionable underlyings "
    "fetched OK (`share`), by status and tier; `chronic` the names stale in 3 of the last 5 "
    "sessions (`chronicNames` the most persistent); `medianShare` the median share of the five "
    "sessions before and `previousChronic` the count the session before (null: not enough "
    "history); `drift` what moved beyond the warning limits"
)
class ChainCoverage:
    session: dt.date
    total: int
    ok: int
    share: float
    statuses: list[ChainStatusCount]
    tiers: list[ChainTier]
    chronic: int
    chronic_names: list[str]
    median_share: float | None
    previous_chronic: int | None
    drift: list[str]

    @classmethod
    def of(cls, d: ingestion.ChainCoverageRead) -> Self:
        return cls(
            session=d.session,
            total=d.total,
            ok=d.ok,
            share=d.share,
            statuses=[ChainStatusCount.of(s) for s in d.statuses],
            tiers=[ChainTier.of(t) for t in d.tiers],
            chronic=d.chronic,
            chronic_names=list(d.chronic_names),
            median_share=d.median_share,
            previous_chronic=d.previous_chronic,
            drift=list(d.drift),
        )
