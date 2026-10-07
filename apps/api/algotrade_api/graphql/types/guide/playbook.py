"""``GuidePlaybookDetail``: one site playbook's Guide page (ADR 0051): its prose (linked), the
criteria table, the tie-break, related playbooks and the situations that fool its fields."""

from typing import Self

import strawberry

from algotrade.services.read.guide import playbook
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description="A playbook's prose: the summary (the hero), what a hit looks like, what it "
    "does not check, the caveats before acting (each linked) and the sources"
)
class GuidePlaybookProse:
    summary: GuideProse
    hit: GuideProse
    not_checked: GuideProse
    before_acting: list[GuideProse]
    sources: list[str]

    @classmethod
    def of(cls, d: playbook.GuidePlaybookProse) -> Self:
        return cls(
            summary=GuideProse.of(d.summary),
            hit=GuideProse.of(d.hit),
            not_checked=GuideProse.of(d.not_checked),
            before_acting=[GuideProse.of(c) for c in d.before_acting],
            sources=list(d.sources),
        )


@strawberry.type(
    description="One criterion of the playbook, in the preset's file order: `name` its id, "
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
    def of(cls, d: playbook.GuideCriterionRow) -> Self:
        return cls(
            name=d.name, asks=d.asks, field=d.field, rule=d.rule, mode=d.mode, on_miss=d.on_miss
        )


@strawberry.type(description="Another playbook worth reading next, and why")
class GuideRelatedPlaybook:
    id: str
    name: str
    reason: str

    @classmethod
    def of(cls, d: playbook.GuideRelatedPlaybook) -> Self:
        return cls(id=d.id, name=d.name, reason=d.reason)


@strawberry.type(
    description="A situation that fools the playbook: `fields`, the screen's fields it fools"
)
class GuidePlaybookSituation:
    slug: str
    name: str
    fields: list[str]

    @classmethod
    def of(cls, d: playbook.GuidePlaybookSituation) -> Self:
        return cls(slug=d.slug, name=d.name, fields=list(d.fields))


@strawberry.type(
    description="A site playbook's Guide page: the preset's latest `version`, its family, the "
    "prose (null: none written), the criteria in file order (the base gates are not marked "
    "apart), the tie-break, related playbooks and the situations that fool its fields"
)
class GuidePlaybookDetail:
    id: str
    name: str
    family: str | None
    family_title: str | None
    version: int | None
    prose: GuidePlaybookProse | None
    criteria: list[GuideCriterionRow]
    tie_break: str | None
    tie_break_descending: bool
    related: list[GuideRelatedPlaybook]
    situations: list[GuidePlaybookSituation]

    @classmethod
    def of(cls, d: playbook.GuidePlaybookDetail) -> Self:
        return cls(
            id=d.id,
            name=d.name,
            family=d.family,
            family_title=d.family_title,
            version=d.version,
            prose=GuidePlaybookProse.of(d.prose) if d.prose is not None else None,
            criteria=[GuideCriterionRow.of(c) for c in d.criteria],
            tie_break=d.tie_break,
            tie_break_descending=d.tie_break_descending,
            related=[GuideRelatedPlaybook.of(r) for r in d.related],
            situations=[GuidePlaybookSituation.of(s) for s in d.situations],
        )
