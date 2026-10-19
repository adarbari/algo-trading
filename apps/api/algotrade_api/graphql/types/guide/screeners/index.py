"""``GuideScreenerIndex``: the Screeners section's lead page (ADR 0051): what a screener is, how
it differs from an edge and a card per family with its screener count."""

from typing import Self

import strawberry

from algotrade.services.read.guide.screeners import index


@strawberry.type(
    description="A family's card: its `id` (`Query.guideScreenerCategory(id)`), title, one-line "
    "purpose and how many site screeners it holds"
)
class GuideScreenerCategoryCard:
    id: str
    title: str
    purpose: str
    count: int

    @classmethod
    def of(cls, d: index.GuideScreenerCategoryCard) -> Self:
        return cls(id=d.id, title=d.title, purpose=d.purpose, count=d.count)


@strawberry.type(
    description="The Screeners section's lead page (ADR 0051): `what` a screener is, "
    "`versusEdge` (how it differs from an edge), the family `categories` in order and the "
    "`count` of every site screener; no live number"
)
class GuideScreenerIndex:
    what: str
    versus_edge: str
    categories: list[GuideScreenerCategoryCard]
    count: int

    @classmethod
    def of(cls, d: index.GuideScreenerIndex) -> Self:
        return cls(
            what=d.what,
            versus_edge=d.versus_edge,
            categories=[GuideScreenerCategoryCard.of(c) for c in d.categories],
            count=d.count,
        )
