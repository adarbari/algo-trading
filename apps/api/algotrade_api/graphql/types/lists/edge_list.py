"""``EdgeList``: the Edges list narrowed by a search and the shared filters, with the filter bar's
counts (``Query.edgeList``, ADR 0082)."""

from typing import Self

import strawberry

from algotrade.services.read.context import ReadContext
from algotrade.services.read.lists import edges as list_reads
from algotrade_api.graphql.types.evaluation.edge import Edge
from algotrade_api.graphql.types.filtering.facets import FilterFacets


@strawberry.type(
    description="The edges the user sees that pass the search `q` (id, name or thesis) and the "
    "`filters` (the surface `edges` of `filterSet`), by id: `total` counts them, `facets` the "
    "counts of the filter bar over the search's matches (`facets.total` before the filters). A "
    "figure an edge's verdict does not hold never passes a filter on it. Views: Mine is the "
    "filter `mine`, Following `followed`, Rejected the status `rejected`"
)
class EdgeList:
    total: int
    items: list[Edge]
    facets: FilterFacets

    @classmethod
    def of(cls, d: list_reads.EdgeList, ctx: ReadContext) -> Self:
        return cls(
            total=d.total,
            items=[Edge.of(r.edge, ctx) for r in d.items],
            facets=FilterFacets.of(d.facets),
        )
