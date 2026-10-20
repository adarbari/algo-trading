"""``GuideScreenerCategory`` (ADR 0051; spec ``docs/ui/guide.md``, "Screeners"): one family's
page, ``config/site/guide/sections.toml``'s ``purpose`` and ``intro`` for it and its site
screeners as rows in Guide order: id, name, ``line`` (what the screen asks, from its prose file;
empty without one) and the site edges whose screeners include it (``GuideEdgeRow``, the one
derivation of the link, ``edges/site_edges.py``). Session-free; ``None`` for an id that is no
family or a family with no site screener."""

from dataclasses import dataclass

from algotrade.config.site.guide.screeners import load_guide_screeners
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.edge import GuideEdgeRow, edge_row
from algotrade.services.read.guide.edges.site_edges import edges_of_screener, screeners_of


@dataclass(frozen=True)
class GuideCategoryScreener:
    """A screener's row: ``line`` is what it asks in one line (``""``: no prose written)."""

    id: str
    name: str
    line: str
    edges: tuple[GuideEdgeRow, ...]


@dataclass(frozen=True)
class GuideScreenerCategory:
    id: str
    title: str
    purpose: str
    intro: str
    screeners: tuple[GuideCategoryScreener, ...]


def load_guide_screener_category(ctx: Stores, category_id: str) -> GuideScreenerCategory | None:
    """The family ``category_id`` names (module docstring)."""
    families = load_guide_sections(ctx.configs).families
    family = next((f for f in families if f.id == category_id), None)
    if family is None:
        return None
    members = [p for p in screeners_of(ctx) if p.family == family.id]
    if not members:
        return None
    prose = load_guide_screeners(ctx.configs)
    rows = tuple(
        GuideCategoryScreener(
            id=p.id,
            name=p.name,
            line=written.line if (written := prose.get(p.id)) is not None else "",
            edges=tuple(edge_row(e) for e in edges_of_screener(ctx, p.id)),
        )
        for p in members
    )
    return GuideScreenerCategory(family.id, family.title, family.purpose, family.intro, rows)
