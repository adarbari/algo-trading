"""``GuideScreenerCategory``: one screener family's Guide page (ADR 0051): its purpose and intro
and its screeners as rows with what each asks and the edges that use it."""

from typing import Self

import strawberry

from algotrade.services.read.guide.screeners import category
from algotrade_api.graphql.types.guide.edges.edge import GuideEdgeRow


@strawberry.type(
    description="A screener row of a family page: its `id` and name, `line` (what it asks, in "
    "one line; empty without prose) and the site edges that use it, as rows"
)
class GuideCategoryScreener:
    id: str
    name: str
    line: str
    edges: list[GuideEdgeRow]

    @classmethod
    def of(cls, d: category.GuideCategoryScreener) -> Self:
        return cls(id=d.id, name=d.name, line=d.line, edges=[GuideEdgeRow.of(e) for e in d.edges])


@strawberry.type(
    description="A screener family's Guide page (ADR 0051): its title, one-line `purpose`, "
    "`intro` paragraph and its site screeners in Guide order"
)
class GuideScreenerCategory:
    id: str
    title: str
    purpose: str
    intro: str
    screeners: list[GuideCategoryScreener]

    @classmethod
    def of(cls, d: category.GuideScreenerCategory) -> Self:
        return cls(
            id=d.id,
            title=d.title,
            purpose=d.purpose,
            intro=d.intro,
            screeners=[GuideCategoryScreener.of(s) for s in d.screeners],
        )
