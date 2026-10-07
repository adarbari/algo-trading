"""``GuideField`` (ADR 0051): a catalogue field's Guide page, with what the server derives for
it (ADR 0038: never the browser):

- ``info``: the field's ``FeatureInfo`` with the site field guide's entry;
- ``related``: the other catalogue fields its guide entry names, in the order written (how to
  read it, then the caveats, then the use notes), then the fields its formula reads (an
  expression's inputs); each once, first mention first, only names in the caller's catalogue,
  never the field itself. Names match exactly as written (``rollup.momentum@v1.rel_volume``,
  ``feature.atr_pct``);
- ``playbooks``: the site presets that name the field in a criterion (with each such rule as
  text), a display column or the rank tie-break, in Guide order;
- ``situations``: the field guide's situations whose ``affects`` names the field;
- ``reads_linked``, ``caveats_linked`` and each situation's ``signs_linked`` / ``do_linked``:
  the same prose split at the catalogue names it mentions (``prose.py``).

A name outside the caller's catalogue is ``UnknownFeatureError`` (GraphQL
``UNKNOWN_FEATURE``), as for the catalogue and distribution reads."""

from collections.abc import Container
from dataclasses import dataclass

from algotrade.config.site.field_guide import Situation
from algotrade.config.site.settings import load_field_guide
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.playbooks import SitePlaybook, rule_text, site_playbooks
from algotrade.services.read.guide.prose import LinkedProse, link_prose, mentions
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos


@dataclass(frozen=True)
class GuidePlaybookUse:
    """A site preset that uses the field: ``rules`` (one per criterion on the field, as
    ``op value mode tolerance``), ``column`` (a display column), ``rank`` (its tie-break),
    ``flag`` (a rule of one of its flags)."""

    id: str
    name: str
    family: str | None
    rules: tuple[str, ...]
    column: bool
    rank: bool
    flag: bool = False


@dataclass(frozen=True)
class GuideSituation:
    """A situation that fools the field: how it shows (``signs``), what a screen does about
    it (``do``) and every field it fools (``affects``)."""

    name: str
    signs: str
    do: str
    affects: tuple[str, ...]
    slug: str
    signs_linked: LinkedProse
    do_linked: LinkedProse

    @classmethod
    def of(cls, s: Situation, names: Container[str]) -> "GuideSituation":
        return cls(
            s.name,
            s.signs,
            s.do,
            s.affects,
            s.slug,
            link_prose(s.signs, names),
            link_prose(s.do, names),
        )


@dataclass(frozen=True)
class GuideField:
    info: FeatureInfo
    related: tuple[str, ...]
    playbooks: tuple[GuidePlaybookUse, ...]
    situations: tuple[GuideSituation, ...]
    reads_linked: LinkedProse | None  # None: the field has no guide entry
    caveats_linked: tuple[LinkedProse, ...]


def load_guide_field(ctx: Stores, name: str) -> GuideField:
    """``name``'s Guide page (module docstring); ``UnknownFeatureError`` outside the
    caller's catalogue."""
    guide = load_field_guide(ctx.configs)
    info = feature_infos(ctx.features, [name], guide=guide)[name]
    fields = catalog_of(ctx.features).fields
    situations = tuple(GuideSituation.of(s, fields) for s in guide.situations if name in s.affects)
    found = (_use(p, name) for p in site_playbooks(ctx))
    entry = info.guide
    return GuideField(
        info=info,
        related=_related(ctx, info, fields),
        playbooks=tuple(p for p in found if p is not None),
        situations=situations,
        reads_linked=link_prose(entry.reads, fields) if entry is not None else None,
        caveats_linked=tuple(link_prose(c, fields) for c in entry.caveats) if entry else (),
    )


def _related(ctx: Stores, info: FeatureInfo, fields: Container[str]) -> tuple[str, ...]:
    texts = (
        [info.guide.reads, *info.guide.caveats, *(u.note for u in info.guide.uses)]
        if info.guide is not None
        else []
    )
    inputs = (ctx.features.feature(ref) for ref in info.inputs)
    named = [*mentions(texts, fields), *(f.field for f in inputs if f is not None)]
    out = dict.fromkeys(n for n in named if n in fields and n != info.name)
    return tuple(out)


def _use(playbook: SitePlaybook, name: str) -> GuidePlaybookUse | None:
    spec = playbook.spec
    rules = tuple(rule_text(c) for c in spec.criteria if c.field == name)
    column = any(field == name for _, field in spec.columns)
    rank = spec.tie_break == name
    flag = any(r.field == name for _, group in spec.flags for r in group.rules())
    if not (rules or column or rank or flag):
        return None
    return GuidePlaybookUse(playbook.id, playbook.name, playbook.family, rules, column, rank, flag)
