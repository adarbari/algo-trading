"""``GuideScreenerDetail``: one site screener's Guide page (ADR 0051): its prose (linked), the
criteria table, the tie-break, related screeners and the situations that fool its fields."""

from typing import Self

import strawberry

from algotrade.services.read.guide.screeners import screener
from algotrade_api.graphql.types.guide.edges.edge import GuideEdgeRow
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description="A source of a screener page: the citation `title`, its https `url` (null: no "
    "page verified) and `note`, what it shows; the n-th is the one the marker `[^n]` cites"
)
class GuideScreenerSource:
    title: str
    url: str | None
    note: str

    @classmethod
    def of(cls, d: screener.GuideScreenerSource) -> Self:
        return cls(title=d.title, url=d.url, note=d.note)


@strawberry.type(
    description="A screener's prose: the summary (the hero), what a hit looks like, what it "
    "does not check, the caveats before acting (each linked, with its source markers) and the "
    "sources they cite, in order"
)
class GuideScreenerProse:
    summary: GuideProse
    hit: GuideProse
    not_checked: GuideProse
    before_acting: list[GuideProse]
    sources: list[GuideScreenerSource]

    @classmethod
    def of(cls, d: screener.GuideScreenerProse) -> Self:
        return cls(
            summary=GuideProse.of(d.summary),
            hit=GuideProse.of(d.hit),
            not_checked=GuideProse.of(d.not_checked),
            before_acting=[GuideProse.of(c) for c in d.before_acting],
            sources=[GuideScreenerSource.of(s) for s in d.sources],
        )


@strawberry.type(
    description="One criterion of the screener, in the preset's file order: `name` its id, "
    "`asks` in words (null: not written), `rule` as `op value mode tolerance`, `onMiss` what a "
    "soft near miss gives (null unless soft)"
)
class GuideCriterionRow:
    name: str
    asks: str | None
    field: str
    rule: str
    mode: str
    on_miss: str | None

    @classmethod
    def of(cls, d: screener.GuideCriterionRow) -> Self:
        return cls(
            name=d.name, asks=d.asks, field=d.field, rule=d.rule, mode=d.mode, on_miss=d.on_miss
        )


@strawberry.type(description="Another screener worth reading next, and why")
class GuideRelatedScreener:
    id: str
    name: str
    reason: str

    @classmethod
    def of(cls, d: screener.GuideRelatedScreener) -> Self:
        return cls(id=d.id, name=d.name, reason=d.reason)


@strawberry.type(
    description="A situation that fools the screener: `fields`, the screen's fields it fools"
)
class GuideScreenerSituation:
    slug: str
    name: str
    fields: list[str]

    @classmethod
    def of(cls, d: screener.GuideScreenerSituation) -> Self:
        return cls(slug=d.slug, name=d.name, fields=list(d.fields))


@strawberry.type(
    description="A site screener's Guide page: the preset's latest `version`, its family "
    "(id, then title), the "
    "prose (null: none written), the criteria in file order (the base gates are not marked "
    "apart), the tie-break, related screeners, the situations that fool its fields and the "
    "site edges it implements (`edges`, as rows)"
)
class GuideScreenerDetail:
    id: str
    name: str
    family: str | None
    family_title: str | None
    version: int | None
    prose: GuideScreenerProse | None
    criteria: list[GuideCriterionRow]
    tie_break: str | None
    tie_break_descending: bool
    related: list[GuideRelatedScreener]
    situations: list[GuideScreenerSituation]
    edges: list[GuideEdgeRow]

    @classmethod
    def of(cls, d: screener.GuideScreenerDetail) -> Self:
        return cls(
            id=d.id,
            name=d.name,
            family=d.family,
            family_title=d.family_title,
            version=d.version,
            prose=GuideScreenerProse.of(d.prose) if d.prose is not None else None,
            criteria=[GuideCriterionRow.of(c) for c in d.criteria],
            tie_break=d.tie_break,
            tie_break_descending=d.tie_break_descending,
            related=[GuideRelatedScreener.of(r) for r in d.related],
            situations=[GuideScreenerSituation.of(s) for s in d.situations],
            edges=[GuideEdgeRow.of(e) for e in d.edges],
        )
