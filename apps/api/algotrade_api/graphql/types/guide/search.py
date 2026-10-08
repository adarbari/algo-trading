"""``GuideSearch``: one search over every Guide entry, the results grouped by kind (ADR 0051;
the ranking is the server's, ``services/read/guide/search.py``)."""

from typing import Self

import strawberry

from algotrade.services.read.guide import search


@strawberry.type(
    description="A search result: the entry (`kind`, `id`: its page's key), its title and a "
    "snippet of its text"
)
class GuideSearchHit:
    kind: str
    id: str
    title: str
    snippet: str

    @classmethod
    def of(cls, d: search.GuideSearchHit) -> Self:
        return cls(kind=d.kind, id=d.id, title=d.title, snippet=d.snippet)


@strawberry.type(description="The results of one kind, best first")
class GuideSearchGroup:
    kind: str
    hits: list[GuideSearchHit]

    @classmethod
    def of(cls, d: search.GuideSearchGroup) -> Self:
        return cls(kind=d.kind, hits=[GuideSearchHit.of(h) for h in d.hits])


@strawberry.type(
    description="Guide search results for `query`, grouped by kind; the groups by their best "
    "result (exact name, then name or title, then intent or theme, then prose)"
)
class GuideSearch:
    query: str
    groups: list[GuideSearchGroup]

    @classmethod
    def of(cls, d: search.GuideSearch) -> Self:
        return cls(query=d.query, groups=[GuideSearchGroup.of(g) for g in d.groups])
