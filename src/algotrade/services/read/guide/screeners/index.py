"""``GuideScreenerIndex`` (ADR 0051; spec ``docs/ui/guide.md``, "Screeners"): the Screeners
section's lead page. What a screener is and how it differs from an edge (the ``screeners_page``
of ``config/site/guide/sections.toml``), then a card per family in Guide order: its id, title,
one-line purpose and how many site screeners it holds (a family with none is left out, so a card
always opens a page with rows). Session-free: the Guide shows no live number."""

from dataclasses import dataclass

from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.site_edges import screeners_of


@dataclass(frozen=True)
class GuideScreenerCategoryCard:
    """A family's card: ``id`` (the category page's key), ``title``, ``purpose`` (one line) and
    ``count`` of its screeners."""

    id: str
    title: str
    purpose: str
    count: int


@dataclass(frozen=True)
class GuideScreenerIndex:
    """The lead page: ``what`` a screener is, ``versus_edge`` (both empty without the
    ``screeners_page`` table), the ``categories`` and the ``count`` of every screener."""

    what: str
    versus_edge: str
    categories: tuple[GuideScreenerCategoryCard, ...]
    count: int


def load_guide_screener_index(ctx: Stores) -> GuideScreenerIndex:
    """The Screeners section's lead page (module docstring)."""
    sections = load_guide_sections(ctx.configs)
    screeners = screeners_of(ctx)
    cards = tuple(
        GuideScreenerCategoryCard(f.id, f.title, f.purpose, n)
        for f in sections.families
        if (n := sum(1 for p in screeners if p.family == f.id))
    )
    lead = sections.screeners_page
    return GuideScreenerIndex(
        what=lead.what if lead is not None else "",
        versus_edge=lead.versus_edge if lead is not None else "",
        categories=cards,
        count=len(screeners),
    )
