"""``GuideMechanism``: one mechanism's Guide page (ADR 0051): the reason an edge should work,
its paragraphs linked, its stats and sources, and the site edges that rest on it as rows."""

from typing import Self

import strawberry

from algotrade.services.read.guide.edges import mechanism
from algotrade_api.graphql.types.guide.edges.edge import GuideEdgeRow
from algotrade_api.graphql.types.guide.edges.ideas import GuideIdea
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description="A tile of a mechanism page: `title`, `value` as shown, `reading` and `source`, a "
    "1-based index into the page's sources (null: our own bar, from the verdict settings)"
)
class GuideMechanismStat:
    title: str
    value: str
    reading: str
    source: int | None

    @classmethod
    def of(cls, d: mechanism.GuideMechanismStat) -> Self:
        return cls(title=d.title, value=d.value, reading=d.reading, source=d.source)


@strawberry.type(
    description="A source of a mechanism page: the citation `title`, its https `url` and "
    "`reading`, what it shows"
)
class GuideMechanismSource:
    title: str
    url: str
    reading: str

    @classmethod
    def of(cls, d: mechanism.GuideMechanismSource) -> Self:
        return cls(title=d.title, url=d.url, reading=d.reading)


@strawberry.type(
    description="A mechanism's Guide page: the card's `question`, `short` and `examples`, the "
    "paragraphs of how it works, why it survives, the research and real against decoy (each "
    "linked), the one thing not to read into it (`dont`), glossary terms (`seeAlso`), the stat "
    "tiles, the sources, the `edges` that rest on it (every status, Guide order) and the ideas "
    "researched but `notBuilt`"
)
class GuideMechanism:
    id: str
    title: str
    question: str
    examples: str
    short: str
    how_it_works: list[GuideProse]
    why_it_survives: list[GuideProse]
    research: list[GuideProse]
    real_vs_decoy: list[GuideProse]
    dont: GuideProse
    see_also: list[str]
    stats: list[GuideMechanismStat]
    sources: list[GuideMechanismSource]
    edges: list[GuideEdgeRow]
    not_built: list[GuideIdea]

    @classmethod
    def of(cls, d: mechanism.GuideMechanism) -> Self:
        return cls(
            id=d.id,
            title=d.title,
            question=d.question,
            examples=d.examples,
            short=d.short,
            how_it_works=[GuideProse.of(p) for p in d.how_it_works],
            why_it_survives=[GuideProse.of(p) for p in d.why_it_survives],
            research=[GuideProse.of(p) for p in d.research],
            real_vs_decoy=[GuideProse.of(p) for p in d.real_vs_decoy],
            dont=GuideProse.of(d.dont),
            see_also=list(d.see_also),
            stats=[GuideMechanismStat.of(s) for s in d.stats],
            sources=[GuideMechanismSource.of(s) for s in d.sources],
            edges=[GuideEdgeRow.of(e) for e in d.edges],
            not_built=[GuideIdea.of(i) for i in d.not_built],
        )
