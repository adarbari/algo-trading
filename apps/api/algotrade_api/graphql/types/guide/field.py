"""``GuideField``: a catalogue field's Guide page (ADR 0051): its ``FeatureInfo`` with the
field guide's entry, and what the server derives for it (related fields, the playbooks that
use it, the situations that fool it; ADR 0038)."""

from typing import Self

import strawberry

from algotrade.services.read.guide import field
from algotrade_api.graphql.types.instruments.feature import FeatureInfo


@strawberry.type(
    description="A site preset that uses the field: `rules`, one per criterion on it as `op "
    "value mode tolerance`; `column`: a display column; `rank`: its tie-break; `flag`: a rule "
    "of one of its flags"
)
class GuidePlaybookUse:
    id: str
    name: str
    family: str | None
    rules: list[str]
    column: bool
    rank: bool
    flag: bool

    @classmethod
    def of(cls, d: field.GuidePlaybookUse) -> Self:
        return cls(
            id=d.id,
            name=d.name,
            family=d.family,
            rules=list(d.rules),
            column=d.column,
            rank=d.rank,
            flag=d.flag,
        )


@strawberry.type(
    description="A situation that fools the field: how it shows, what a screen does about it "
    "and every field it fools"
)
class GuideSituation:
    name: str
    signs: str
    do: str
    affects: list[str]

    @classmethod
    def of(cls, d: field.GuideSituation) -> Self:
        return cls(name=d.name, signs=d.signs, do=d.do, affects=list(d.affects))


@strawberry.type(
    description="A field's Guide page: `info` with the field guide's entry; `related` the "
    "other catalogue fields its entry names, then its formula's inputs (first mention first); "
    "the site playbooks that use it; the situations that fool it"
)
class GuideField:
    info: FeatureInfo
    related: list[str]
    playbooks: list[GuidePlaybookUse]
    situations: list[GuideSituation]

    @classmethod
    def of(cls, d: field.GuideField) -> Self:
        return cls(
            info=FeatureInfo.of(d.info),
            related=list(d.related),
            playbooks=[GuidePlaybookUse.of(p) for p in d.playbooks],
            situations=[GuideSituation.of(s) for s in d.situations],
        )
