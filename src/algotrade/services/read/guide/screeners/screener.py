"""``GuideScreenerDetail`` (ADR 0051; spec ``docs/ui/guide.md`` "The screener page"): one
site screener's page, what the server derives for it (ADR 0038: never the browser):

- ``prose``: its ``config/site/guide/screeners/<family>/<id>.toml`` (summary, what a hit looks like,
  what it does not check, the caveats before acting, split at the catalogue names they
  mention, a source marker ``[^n]`` its own segment; the sources as written, each with the
  https url when one is verified); ``None`` without a file (a fitness test forbids that for
  a shipped preset);
- ``family`` (its id: the category page's key) and ``family_title`` from ``sections.toml``;
  ``version``, the preset's latest version (the one the nightly runs);
- ``criteria``: one row per criterion **in the preset's file order** (its funnel order) with
  what it asks in words (the prose's ``asks``), the field, the rule as text (``rule_text``),
  the mode and, for a soft criterion, what a near miss gives (``on_miss``). The presets mark
  the site base gates only with a TOML comment, so the rows are not split into base gates and
  setup (in every site preset today the base gates come first);
- ``tie_break`` (the field ordering equal scores) and its direction;
- ``related``: the prose's related screeners with their names (an id that is no site
  screener is left out);
- ``situations``: the field guide's situations that fool any field the screen decides on
  (criteria, flags, the tie-break), each with those fields (``situation.fooled``);
- ``edges``: the site edges whose screeners include this screener (``edges/site_edges.py``:
  the one derivation of the link both ways), as rows in Guide order."""

from dataclasses import dataclass

from algotrade.config.site.guide.screeners import ScreenerProse, load_guide_screeners
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.site.settings import load_field_guide
from algotrade.core.model.screen_spec import Criterion, Mode
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.edge import GuideEdgeRow, edge_row
from algotrade.services.read.guide.edges.site_edges import edges_of_screener
from algotrade.services.read.guide.prose import LinkedProse, link_prose
from algotrade.services.read.guide.screeners.site_screeners import rule_text, site_screeners
from algotrade.services.read.guide.situation import fooled


@dataclass(frozen=True)
class GuideScreenerSource:
    """A source: the citation ``title``, its https ``url`` (``None``: no page verified) and
    ``note``, what it shows. A marker ``[^n]`` of the prose points at the n-th."""

    title: str
    url: str | None
    note: str


@dataclass(frozen=True)
class GuideScreenerProse:
    summary: LinkedProse
    hit: LinkedProse
    not_checked: LinkedProse
    before_acting: tuple[LinkedProse, ...]
    sources: tuple[GuideScreenerSource, ...]


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
class GuideRelatedScreener:
    id: str
    name: str
    reason: str


@dataclass(frozen=True)
class GuideScreenerSituation:
    """A situation that fools the screener: ``fields``, the screen's fields it fools."""

    slug: str
    name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class GuideScreenerDetail:
    id: str
    name: str
    family: str | None
    family_title: str | None
    version: int | None
    prose: GuideScreenerProse | None
    criteria: tuple[GuideCriterionRow, ...]
    tie_break: str | None
    tie_break_descending: bool
    related: tuple[GuideRelatedScreener, ...]
    situations: tuple[GuideScreenerSituation, ...]
    edges: tuple[GuideEdgeRow, ...] = ()


def load_guide_screener(ctx: Stores, screener_id: str) -> GuideScreenerDetail | None:
    """The site screener ``screener_id`` (module docstring); ``None``: no site rule-screen
    preset of that id."""
    screeners = site_screeners(ctx)
    screener = next((p for p in screeners if p.id == screener_id), None)
    if screener is None:
        return None
    prose = load_guide_screeners(ctx.configs).get(screener_id)
    titles = {f.id: f.title for f in load_guide_sections(ctx.configs).families}
    names = {p.id: p.name for p in screeners}
    situations = (
        GuideScreenerSituation(s.slug, s.name, fooled(screener, s))
        for s in load_field_guide(ctx.configs).situations
    )
    spec = screener.spec
    return GuideScreenerDetail(
        id=screener.id,
        name=screener.name,
        family=screener.family,
        family_title=titles.get(screener.family) if screener.family is not None else None,
        version=spec.version,
        prose=_prose(ctx, prose) if prose is not None else None,
        criteria=tuple(_row(c, prose) for c in spec.criteria),
        tie_break=spec.tie_break,
        tie_break_descending=spec.tie_break_descending,
        related=tuple(
            GuideRelatedScreener(r.id, names[r.id], r.reason)
            for r in (prose.related if prose is not None else ())
            if r.id in names
        ),
        situations=tuple(s for s in situations if s.fields),
        edges=tuple(edge_row(e) for e in edges_of_screener(ctx, screener_id)),
    )


def _prose(ctx: Stores, prose: ScreenerProse) -> GuideScreenerProse:
    fields = catalog_of(ctx.features).fields
    count = len(prose.sources)
    return GuideScreenerProse(
        summary=link_prose(prose.summary, fields, count),
        hit=link_prose(prose.hit, fields, count),
        not_checked=link_prose(prose.not_checked, fields, count),
        before_acting=tuple(link_prose(c, fields, count) for c in prose.before_acting),
        sources=tuple(GuideScreenerSource(s.title, s.url, s.note) for s in prose.sources),
    )


def _row(criterion: Criterion, prose: ScreenerProse | None) -> GuideCriterionRow:
    return GuideCriterionRow(
        name=criterion.id,
        asks=prose.ask(criterion.id) if prose is not None else None,
        field=criterion.field,
        rule=rule_text(criterion),
        mode=criterion.mode.value,
        on_miss=criterion.on_miss if criterion.mode is Mode.SOFT else None,
    )
