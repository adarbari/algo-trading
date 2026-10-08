"""``GuideSituationDetail``: one situation's Guide page (ADR 0051): its signs and what to do,
linked, the fields it fools and the site playbooks reading them."""

from typing import Self

import strawberry

from algotrade.services.read.guide import situation
from algotrade_api.graphql.types.guide.prose import GuideProse


@strawberry.type(
    description="A site playbook reading fields the situation fools: `fields`, those fields"
)
class GuideSituationPlaybook:
    id: str
    name: str
    fields: list[str]

    @classmethod
    def of(cls, d: situation.GuideSituationPlaybook) -> Self:
        return cls(id=d.id, name=d.name, fields=list(d.fields))


@strawberry.type(
    description="A situation's Guide page: `signs` (how it shows) and `do` (what a screen "
    "does about it) linked; `affects`, every field it fools; the site playbooks reading any "
    "of them"
)
class GuideSituationDetail:
    slug: str
    name: str
    signs: GuideProse
    do: GuideProse
    affects: list[str]
    playbooks: list[GuideSituationPlaybook]

    @classmethod
    def of(cls, d: situation.GuideSituationDetail) -> Self:
        return cls(
            slug=d.slug,
            name=d.name,
            signs=GuideProse.of(d.signs),
            do=GuideProse.of(d.do),
            affects=list(d.affects),
            playbooks=[GuideSituationPlaybook.of(p) for p in d.playbooks],
        )
