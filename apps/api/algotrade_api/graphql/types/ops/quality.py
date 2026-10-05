"""``QualityReport`` (the session's nightly data-quality checks) and ``Verification`` (the
session's live verification of our values vs IBKR's), each UNKNOWN when it did not run for the
session."""

import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.ops import quality
from algotrade_api.graphql.types.instruments.feature import Unknown


@strawberry.type(
    description="One data-quality check: `status` PASS, WARN or FAIL; `detail` what was "
    "measured, against which rule"
)
class QualityCheck:
    name: str
    status: str
    detail: str

    @classmethod
    def of(cls, d: quality.QualityCheck) -> Self:
        return cls(name=d.name, status=d.status, detail=d.detail)


@strawberry.type(
    description="The data-quality checks of the session's `data_quality` run (the latest, "
    "when it ran twice): `status` the run's (complete, partial, failed); `unknown` NOT_RUN "
    "when the session has none"
)
class QualityReport:
    session: dt.date
    run_id: str | None
    status: str | None
    finished_at: dt.datetime | None
    checks: list[QualityCheck]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: quality.QualityReport) -> Self:
        return cls(
            session=d.session,
            run_id=d.run_id,
            status=d.status,
            finished_at=d.finished_at,
            checks=[QualityCheck.of(c) for c in d.checks],
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )


@strawberry.type(description="Rows per status (PASS / WARN / FAIL / NA) of one check")
class CheckCounts:
    check: str
    counts: JSON

    @classmethod
    def of(cls, d: quality.CheckCounts) -> Self:
        return cls(check=d.check, counts=JSON(d.counts))


@strawberry.type(
    description="The session's live verification vs IBKR (verification/ibkr): `counts` rows "
    "per status (PASS / WARN / FAIL / NA), `byCheck` most failures first, `failing` FAIL then "
    "WARN rows (at most 50: instrument_id, symbol, check, status, ours, theirs, diff, "
    "tolerance, note), largest diff first; `unknown` NO_PARTITION when it did not run for "
    "the session"
)
class Verification:
    session: dt.date
    run_ids: list[str]
    instruments: int
    counts: JSON
    by_check: list[CheckCounts]
    failing: list[JSON]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: quality.Verification) -> Self:
        return cls(
            session=d.session,
            run_ids=list(d.run_ids),
            instruments=d.instruments,
            counts=JSON(d.counts),
            by_check=[CheckCounts.of(c) for c in d.by_check],
            failing=[JSON(r) for r in d.failing],
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )
