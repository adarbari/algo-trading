"""``GuideEdgeIndex``: the Edges section's top page (ADR 0051): the mechanism cards, the
filters with their counts and the edges set aside; and ``GuideMechanismEntry``, the rail's row."""

from typing import Self

import strawberry

from algotrade.services.read.guide.edges import index
from algotrade_api.graphql.types.guide.edges.edge import GuideEdgeRow
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description="A mechanism in the Guide index: its id (`Query.guideMechanism(id)`), title "
    "and how many edges rest on it"
)
class GuideMechanismEntry:
    id: str
    title: str
    count: int

    @classmethod
    def of(cls, d: index.GuideMechanismEntry) -> Self:
        return cls(id=d.id, title=d.title, count=d.count)


@strawberry.type(description="How many of a mechanism's edges have `status` (none with zero)")
class GuideStatusCount:
    status: str
    count: int

    @classmethod
    def of(cls, d: index.GuideStatusCount) -> Self:
        return cls(status=d.status, count=d.count)


@strawberry.type(
    description="A mechanism's card: its question, one-line hero, examples, how many edges "
    "rest on it, the count by status and the edges as rows"
)
class GuideMechanismCard:
    id: str
    title: str
    question: str
    short: str
    examples: str
    count: int
    statuses: list[GuideStatusCount]
    edges: list[GuideEdgeRow]

    @classmethod
    def of(cls, d: index.GuideMechanismCard) -> Self:
        return cls(
            id=d.id,
            title=d.title,
            question=d.question,
            short=d.short,
            examples=d.examples,
            count=d.count,
            statuses=[GuideStatusCount.of(s) for s in d.statuses],
            edges=[GuideEdgeRow.of(e) for e in d.edges],
        )


@strawberry.type(description="A filter value: the `id` an edge row carries, its `text`, its count")
class GuideFilterOption:
    id: str
    text: str
    count: int

    @classmethod
    def of(cls, d: index.GuideFilterOption) -> Self:
        return cls(id=d.id, text=d.text, count=d.count)


@strawberry.type(
    description="The filters of the edge list with their counts: asset class, side and holding "
    "band, each over every site edge"
)
class GuideEdgeFilters:
    assets: list[GuideFilterOption]
    sides: list[GuideFilterOption]
    holdings: list[GuideFilterOption]

    @classmethod
    def of(cls, d: index.GuideEdgeFilters) -> Self:
        return cls(
            assets=[GuideFilterOption.of(o) for o in d.assets],
            sides=[GuideFilterOption.of(o) for o in d.sides],
            holdings=[GuideFilterOption.of(o) for o in d.holdings],
        )


@strawberry.type(description="An edge set aside (rejected or blocked): its row and the reason")
class GuideSetAsideEdge:
    edge: GuideEdgeRow
    why: GuideProse

    @classmethod
    def of(cls, d: index.GuideSetAsideEdge) -> Self:
        return cls(edge=GuideEdgeRow.of(d.edge), why=GuideProse.of(d.why))


@strawberry.type(
    description="The Edges section's top page (ADR 0051): the mechanism cards in order, the "
    "filters with counts and the edges set aside with their reasons; no live number"
)
class GuideEdgeIndex:
    mechanisms: list[GuideMechanismCard]
    filters: GuideEdgeFilters
    set_aside_title: str
    set_aside_purpose: str
    set_aside: list[GuideSetAsideEdge]

    @classmethod
    def of(cls, d: index.GuideEdgeIndex) -> Self:
        return cls(
            mechanisms=[GuideMechanismCard.of(m) for m in d.mechanisms],
            filters=GuideEdgeFilters.of(d.filters),
            set_aside_title=d.set_aside_title,
            set_aside_purpose=d.set_aside_purpose,
            set_aside=[GuideSetAsideEdge.of(e) for e in d.set_aside],
        )
