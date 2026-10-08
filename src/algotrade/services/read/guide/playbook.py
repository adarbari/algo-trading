"""``GuidePlaybookDetail`` (ADR 0051; spec ``docs/ui/guide.md`` "The playbook page"): one
site playbook's page, what the server derives for it (ADR 0038: never the browser):

- ``prose``: its ``config/site/guide/playbooks/<id>.toml`` (summary, what a hit looks like,
  what it does not check, the caveats before acting, split at the catalogue names they
  mention; the sources as written); ``None`` without a file (a fitness test forbids that for
  a shipped preset);
- ``family`` and ``family_title`` from ``sections.toml``; ``version``, the preset's latest
  version (the one the nightly runs);
- ``criteria``: one row per criterion **in the preset's file order** (its funnel order) with
  what it asks in words (the prose's ``asks``), the field, the rule as text (``rule_text``),
  the mode and, for a soft criterion, what a near miss gives (``on_miss``). The presets mark
  the site base gates only with a TOML comment, so the rows are not split into base gates and
  setup (in every site preset today the base gates come first);
- ``tie_break`` (the field ordering equal scores) and its direction;
- ``related``: the prose's related playbooks with their names (an id that is no site
  playbook is left out);
- ``situations``: the field guide's situations that fool any field the screen decides on
  (criteria, flags, the tie-break), each with those fields (``situation.fooled``)."""

from dataclasses import dataclass

from algotrade.config.site.guide.playbooks import PlaybookProse, load_guide_playbooks
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.site.settings import load_field_guide
from algotrade.core.model.screen_spec import Criterion, Mode
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.playbooks import rule_text, site_playbooks
from algotrade.services.read.guide.prose import LinkedProse, link_prose
from algotrade.services.read.guide.situation import fooled


@dataclass(frozen=True)
class GuidePlaybookProse:
    summary: LinkedProse
    hit: LinkedProse
    not_checked: LinkedProse
    before_acting: tuple[LinkedProse, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class GuideCriterionRow:
    """One criterion: ``name`` (its id in the preset), ``asks`` (in words; ``None``: not
    written), ``rule`` (``op value mode tolerance``), ``on_miss`` (soft only)."""

    name: str
    asks: str | None
    field: str
    rule: str
    mode: str
    on_miss: str | None


@dataclass(frozen=True)
class GuideRelatedPlaybook:
    id: str
    name: str
    reason: str


@dataclass(frozen=True)
class GuidePlaybookSituation:
    """A situation that fools the playbook: ``fields``, the screen's fields it fools."""

    slug: str
    name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class GuidePlaybookDetail:
    id: str
    name: str
    family: str | None
    family_title: str | None
    version: int | None
    prose: GuidePlaybookProse | None
    criteria: tuple[GuideCriterionRow, ...]
    tie_break: str | None
    tie_break_descending: bool
    related: tuple[GuideRelatedPlaybook, ...]
    situations: tuple[GuidePlaybookSituation, ...]


def load_guide_playbook(ctx: Stores, playbook_id: str) -> GuidePlaybookDetail | None:
    """The site playbook ``playbook_id`` (module docstring); ``None``: no site rule-screen
    preset of that id."""
    playbooks = site_playbooks(ctx)
    playbook = next((p for p in playbooks if p.id == playbook_id), None)
    if playbook is None:
        return None
    prose = load_guide_playbooks(ctx.configs).get(playbook_id)
    titles = {f.id: f.title for f in load_guide_sections(ctx.configs).families}
    names = {p.id: p.name for p in playbooks}
    situations = (
        GuidePlaybookSituation(s.slug, s.name, fooled(playbook, s))
        for s in load_field_guide(ctx.configs).situations
    )
    spec = playbook.spec
    return GuidePlaybookDetail(
        id=playbook.id,
        name=playbook.name,
        family=playbook.family,
        family_title=titles.get(playbook.family) if playbook.family is not None else None,
        version=spec.version,
        prose=_prose(ctx, prose) if prose is not None else None,
        criteria=tuple(_row(c, prose) for c in spec.criteria),
        tie_break=spec.tie_break,
        tie_break_descending=spec.tie_break_descending,
        related=tuple(
            GuideRelatedPlaybook(r.id, names[r.id], r.reason)
            for r in (prose.related if prose is not None else ())
            if r.id in names
        ),
        situations=tuple(s for s in situations if s.fields),
    )


def _prose(ctx: Stores, prose: PlaybookProse) -> GuidePlaybookProse:
    fields = catalog_of(ctx.features).fields
    return GuidePlaybookProse(
        summary=link_prose(prose.summary, fields),
        hit=link_prose(prose.hit, fields),
        not_checked=link_prose(prose.not_checked, fields),
        before_acting=tuple(link_prose(c, fields) for c in prose.before_acting),
        sources=prose.sources,
    )


def _row(criterion: Criterion, prose: PlaybookProse | None) -> GuideCriterionRow:
    return GuideCriterionRow(
        name=criterion.id,
        asks=prose.ask(criterion.id) if prose is not None else None,
        field=criterion.field,
        rule=rule_text(criterion),
        mode=criterion.mode.value,
        on_miss=criterion.on_miss if criterion.mode is Mode.SOFT else None,
    )
