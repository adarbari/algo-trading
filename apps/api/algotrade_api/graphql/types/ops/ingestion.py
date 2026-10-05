"""``Completeness`` (every dataset x a window of sessions: rows stored against rows expected)
and ``CellDetail`` (one dataset on one session with the reasons behind it)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.ops import ingestion
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
    cells: list[IngestionCell]
    last_closed: dt.date

    @classmethod
    def of(cls, d: ingestion.Completeness) -> Self:
        return cls(
            sessions=list(d.sessions),
            datasets=list(d.datasets),
            cells=[IngestionCell.of(c) for c in d.cells],
            last_closed=d.last_closed,
        )


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
