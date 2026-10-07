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
- ``situations``: the field guide's situations whose ``affects`` names the field.

A name outside the caller's catalogue is ``UnknownFeatureError`` (GraphQL
``UNKNOWN_FEATURE``), as for the catalogue and distribution reads."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from algotrade.config.site.settings import load_field_guide
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.playbooks import SitePlaybook, rule_text, site_playbooks
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos

# A token a catalogue name could be: letters, digits, ``_``, ``@`` and dots (``feature.x``,
# ``rollup.g@v1.c``); a trailing dot is the sentence's, not the name's.
_TOKEN = re.compile(r"[A-Za-z0-9_@.]+")


@dataclass(frozen=True)
class GuidePlaybookUse:
    """A site preset that uses the field: ``rules`` (one per criterion on the field, as
    ``op value mode tolerance``), ``column`` (a display column), ``rank`` (its tie-break)."""

    id: str
    name: str
    family: str | None
    rules: tuple[str, ...]
    column: bool
    rank: bool


@dataclass(frozen=True)
class GuideSituation:
    """A situation that fools the field: how it shows (``signs``), what a screen does about
    it (``do``) and every field it fools (``affects``)."""

    name: str
    signs: str
    do: str
    affects: tuple[str, ...]


@dataclass(frozen=True)
class GuideField:
    info: FeatureInfo
    related: tuple[str, ...]
    playbooks: tuple[GuidePlaybookUse, ...]
    situations: tuple[GuideSituation, ...]


def load_guide_field(ctx: Stores, name: str) -> GuideField:
    """``name``'s Guide page (module docstring); ``UnknownFeatureError`` outside the
    caller's catalogue."""
    guide = load_field_guide(ctx.configs)
    info = feature_infos(ctx.features, [name], guide=guide)[name]
    situations = tuple(
        GuideSituation(s.name, s.signs, s.do, s.affects)
        for s in guide.situations
        if name in s.affects
    )
    found = (_use(p, name) for p in site_playbooks(ctx))
    return GuideField(
        info=info,
        related=_related(ctx, info),
        playbooks=tuple(p for p in found if p is not None),
        situations=situations,
    )


def _related(ctx: Stores, info: FeatureInfo) -> tuple[str, ...]:
    fields = catalog_of(ctx.features).fields
    texts = (
        [info.guide.reads, *info.guide.caveats, *(u.note for u in info.guide.uses)]
        if info.guide is not None
        else []
    )
    inputs = (ctx.features.feature(ref) for ref in info.inputs)
    named = [*_mentions(texts), *(f.field for f in inputs if f is not None)]
    out = dict.fromkeys(n for n in named if n in fields and n != info.name)
    return tuple(out)


def _mentions(texts: Iterable[str]) -> list[str]:
    """Every name-shaped token of ``texts`` in order (the caller keeps catalogue names)."""
    return [t.rstrip(".") for text in texts for t in _TOKEN.findall(text) if "." in t]


def _use(playbook: SitePlaybook, name: str) -> GuidePlaybookUse | None:
    spec = playbook.spec
    rules = tuple(rule_text(c) for c in spec.criteria if c.field == name)
    column = any(field == name for _, field in spec.columns)
    rank = spec.tie_break == name
    if not (rules or column or rank):
        return None
    return GuidePlaybookUse(playbook.id, playbook.name, playbook.family, rules, column, rank)
