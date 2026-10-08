"""``GuideSituationDetail`` (ADR 0051): one situation's Guide page, found by its slug
(``Situation.slug``, the one definition): how it shows (``signs``) and what a screen does
about it (``do``), both split at the catalogue names they mention; every field it fools (its
``affects``, as written) and the site playbooks that decide on any of them, each with the
fields it fools there (in ``affects`` order). Also the one rule for "the fields of a playbook a
situation fools" (``fooled``), which the playbook page reads the other way round."""

from dataclasses import dataclass

from algotrade.config.site.field_guide import Situation
from algotrade.config.site.settings import load_field_guide
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.playbooks import SitePlaybook, site_playbooks
from algotrade.services.read.guide.prose import LinkedProse, link_prose


@dataclass(frozen=True)
class GuideSituationPlaybook:
    """A site playbook reading a field the situation fools: ``fields``, those fields."""

    id: str
    name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class GuideSituationDetail:
    slug: str
    name: str
    signs: LinkedProse
    do: LinkedProse
    affects: tuple[str, ...]
    playbooks: tuple[GuideSituationPlaybook, ...]


def load_guide_situation(ctx: Stores, slug: str) -> GuideSituationDetail | None:
    """The situation ``slug`` names (module docstring); ``None``: no such situation."""
    situation = next((s for s in load_field_guide(ctx.configs).situations if s.slug == slug), None)
    if situation is None:
        return None
    fields = catalog_of(ctx.features).fields
    found = (
        GuideSituationPlaybook(p.id, p.name, fooled(p, situation)) for p in site_playbooks(ctx)
    )
    return GuideSituationDetail(
        slug=situation.slug,
        name=situation.name,
        signs=link_prose(situation.signs, fields),
        do=link_prose(situation.do, fields),
        affects=situation.affects,
        playbooks=tuple(p for p in found if p.fields),
    )


def fooled(playbook: SitePlaybook, situation: Situation) -> tuple[str, ...]:
    """The fields ``playbook`` decides on (its criteria, its flags' rules, the tie-break; not a
    display column, which decides nothing) that ``situation`` fools, in its ``affects``
    order."""
    spec = playbook.spec
    flags = (r.field for _, group in spec.flags for r in group.rules())
    decides = {*(c.field for c in spec.criteria), *flags, spec.tie_break}
    return tuple(f for f in situation.affects if f in decides)
