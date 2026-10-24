"""``FilterInput`` in, ``FilterFacets`` out: the one contract of every filtered list (ADR 0082
decision 2). Thin mirrors of ``services/read/filtering``; the counts are computed there."""

from typing import Self

import strawberry

from algotrade.services.read.filtering import facets as domain
from algotrade.services.read.filtering import masks

strawberry.enum(masks.WindowUnit)
strawberry.input(
    masks.Within, description="A window filter's amount and unit: within `amount` days or sessions"
)
strawberry.input(
    masks.FilterInput,
    description="One filter as the viewer set it: `id` names a filter of the surface's "
    "`filterSet`; `values` is for a pick, select or toggle (yes / no), `min` and `max` for a "
    "range, `within` for a window; `active` false keeps it echoed in the facets and in no mask",
)


@strawberry.type(description="One value of a pick, select or toggle and how many rows have it")
class OptionCount:
    value: str
    count: int

    @classmethod
    def of(cls, d: domain.OptionCount) -> Self:
        return cls(value=d.value, count=d.count)


@strawberry.type(
    description="One bin of a range's histogram: rows from `lo` up to (not including) `hi`, "
    "the last bin including `hi`"
)
class BinCount:
    lo: float
    hi: float
    count: int

    @classmethod
    def of(cls, d: domain.BinCount) -> Self:
        return cls(lo=d.lo, hi=d.hi, count=d.count)


@strawberry.type(
    description="What one filter tells over the rows passing the OTHER active filters: "
    "`removes` the rows it removes (null: not applied), `unknown` the rows whose value it "
    "cannot judge (never passing), `options` / `bins` the counts to choose from"
)
class FilterFacet:
    id: str
    active: bool
    removes: int | None
    unknown: int
    options: list[OptionCount]
    bins: list[BinCount]

    @classmethod
    def of(cls, d: domain.FilterFacet) -> Self:
        return cls(
            id=d.id,
            active=d.active,
            removes=d.removes,
            unknown=d.unknown,
            options=[OptionCount.of(o) for o in d.options],
            bins=[BinCount.of(b) for b in d.bins],
        )


@strawberry.type(
    description="The counts of one filtered list, from one masked pass over every row (not "
    "the loaded page): `total` rows before the filters, `matched` after them, `items` one "
    "entry per offered filter"
)
class FilterFacets:
    total: int
    matched: int
    items: list[FilterFacet]

    @classmethod
    def of(cls, d: domain.Facets) -> Self:
        return cls(total=d.total, matched=d.matched, items=[FilterFacet.of(f) for f in d.items])
