"""``FeatureDistribution``: one catalogue feature across instruments for the session (counts,
quantiles and a histogram for a number, the most frequent values otherwise), or UNKNOWN when
the feature is not stored for the session."""

import datetime as dt
from typing import Self

import strawberry

from algotrade.services.read.instruments import distribution
from algotrade_api.graphql.types.instruments.feature import FeatureInfo, Unknown


@strawberry.type(description="A quantile of the values: `q` 0.5 is the median")
class Quantile:
    q: float
    value: float

    @classmethod
    def of(cls, d: distribution.Quantile) -> Self:
        return cls(q=d.q, value=d.value)


@strawberry.type(description="One equal-width histogram bin, `lo` to `hi`")
class Bin:
    lo: float
    hi: float
    count: int

    @classmethod
    def of(cls, d: distribution.Bin) -> Self:
        return cls(lo=d.lo, hi=d.hi, count=d.count)


@strawberry.type(description="A value of a non-numeric feature and how many instruments have it")
class Category:
    value: str
    count: int

    @classmethod
    def of(cls, d: distribution.Category) -> Self:
        return cls(value=d.value, count=d.count)


@strawberry.type(
    description="How many instruments pass one use of the field guide's entry (`intent`, in "
    "the guide's order), as the hard rule it states (a soft use's tolerance is not counted): "
    "`count` of the values counted and `bins` the passing count of each histogram bin (empty "
    "for a non-numeric feature)"
)
class UsePass:
    intent: str
    count: int
    bins: list[int]

    @classmethod
    def of(cls, d: distribution.UsePass) -> Self:
        return cls(intent=d.intent, count=d.count, bins=list(d.bins))


@strawberry.type(
    description="A catalogue feature across instruments for `session`: `count` instruments "
    "with a row (a value or a stored null), `nulls` stored nulls; `quantiles` and 20-bin "
    "`histogram` for a number, `categories` (the most frequent values) otherwise; `unknown`: "
    "why nothing is counted (not stored for the session); `passing`: per guide use how many "
    "pass its criterion"
)
class FeatureDistribution:
    name: str
    session: dt.date
    info: FeatureInfo
    count: int
    nulls: int
    quantiles: list[Quantile]
    histogram: list[Bin]
    categories: list[Category]
    unknown: Unknown | None
    passing: list[UsePass]

    @classmethod
    def of(cls, d: distribution.FeatureDistribution) -> Self:
        return cls(
            name=d.name,
            session=d.session,
            info=FeatureInfo.of(d.info),
            count=d.count,
            nulls=d.nulls,
            quantiles=[Quantile.of(q) for q in d.quantiles],
            histogram=[Bin.of(b) for b in d.histogram],
            categories=[Category.of(c) for c in d.categories],
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            passing=[UsePass.of(p) for p in d.passing],
        )
