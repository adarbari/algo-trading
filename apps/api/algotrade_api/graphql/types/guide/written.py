"""``GuideTerm`` and ``GuideStartPage``: the Guide's own written pages (ADR 0051), a glossary
term and a Start here page, their prose linked."""

from typing import Self

import strawberry

from algotrade.services.read.guide import written
from algotrade_api.graphql.types.guide.index import GuideStartEntry, GuideTermEntry
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description="A glossary term's page: its index entry, the body linked and the terms it "
    "sends the reader on to"
)
class GuideTerm:
    entry: GuideTermEntry
    body: GuideProse
    see_also: list[GuideTermEntry]

    @classmethod
    def of(cls, d: written.GuideTerm) -> Self:
        return cls(
            entry=GuideTermEntry.of(d.entry),
            body=GuideProse.of(d.body),
            see_also=[GuideTermEntry.of(t) for t in d.see_also],
        )


@strawberry.type(description="A section of a Start here page, its body linked")
class GuideStartSection:
    title: str
    body: GuideProse

    @classmethod
    def of(cls, d: written.GuideStartSection) -> Self:
        return cls(title=d.title, body=GuideProse.of(d.body))


@strawberry.type(
    description="A Guide entry a page links to: `kind` (start, indicator, episode, playbook, "
    "field, situation or term), `id` (its page's key: a field's catalogue name, a situation's "
    "slug) and its title"
)
class GuideLink:
    kind: str
    id: str
    title: str

    @classmethod
    def of(cls, d: written.GuideLink) -> Self:
        return cls(kind=d.kind, id=d.id, title=d.title)


@strawberry.type(
    description="A Start here page: its index entry, the sections in reading order and the "
    "Guide entries it links to"
)
class GuideStartPage:
    entry: GuideStartEntry
    sections: list[GuideStartSection]
    links: list[GuideLink]

    @classmethod
    def of(cls, d: written.GuideStartPage) -> Self:
        return cls(
            entry=GuideStartEntry.of(d.entry),
            sections=[GuideStartSection.of(s) for s in d.sections],
            links=[GuideLink.of(link) for link in d.links],
        )
