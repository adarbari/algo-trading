"""``KnownCoverage``: the fundamentals share count known against the rows stored, by security
type, with the causes of an operating company's gap (Admin Ingestion). Admin only at the field
(ADR 0056: the causes name where a gap came from)."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.coverage import known_values as domain
from algotrade_api.graphql.types.instruments.feature import Unknown

strawberry.enum(domain.KnownGap, description="Why an operating company has no value")


@strawberry.type(
    description="One security type: `names` of the universe, `rows` stored of them and the "
    "`known` values among those rows; `share` is `known` of `names` (0 to 1)"
)
class KnownByType:
    security_type: str
    names: int
    rows: int
    known: int
    share: float | None

    @classmethod
    def of(cls, d: domain.KnownByType) -> Self:
        return cls(
            security_type=d.security_type, names=d.names, rows=d.rows, known=d.known, share=d.share
        )


@strawberry.type(description="`names` operating companies without a value for the one `gap`")
class KnownGapCount:
    gap: domain.KnownGap
    names: int

    @classmethod
    def of(cls, d: domain.KnownGapCount) -> Self:
        return cls(gap=d.gap, names=d.names)


@strawberry.type(
    description="The fundamentals share count of the session by security type (`byType`, "
    "largest first) and the `gaps` of its operating companies, from the nightly's coverage "
    "check; `unknown` NOT_RUN when no record of the session holds it"
)
class KnownCoverage:
    session: dt.date
    run_id: str | None
    by_type: list[KnownByType]
    gaps: list[KnownGapCount]
    unknown: Unknown | None

    @classmethod
    def of(cls, d: domain.KnownCoverage) -> Self:
        return cls(
            session=d.session,
            run_id=d.run_id,
            by_type=[KnownByType.of(t) for t in d.by_type],
            gaps=[KnownGapCount.of(g) for g in d.gaps],
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
        )
