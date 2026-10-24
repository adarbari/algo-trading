"""``ScreenerList``: the Screeners list narrowed by a search and the shared filters, with the
filter bar's counts (``Query.screenerList``, ADR 0082)."""

from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.lists import screeners as list_reads
from algotrade_api.graphql.types.filtering.facets import FilterFacets
from algotrade_api.graphql.types.screens.screener import Screener


@strawberry.type(
    description="The screeners the user sees that pass the search `q` (id, name or description) "
    "and the `filters` (the surface `screeners` of `filterSet`), by id: `total` counts them, "
    "`facets` the counts of the filter bar over the search's matches (`facets.total` before "
    "the filters). A screener with no run has no `runStatus` / `picked`: it never passes a "
    "filter on them"
)
class ScreenerList:
    total: int
    items: list[Screener]
    facets: FilterFacets

    @classmethod
    def of(cls, d: list_reads.ScreenerList, ctx: ReadContext) -> Self:
        return cls(
            total=d.total,
            items=[Screener.of(r.screener, ctx) for r in d.items],
            facets=FilterFacets.of(d.facets),
        )
