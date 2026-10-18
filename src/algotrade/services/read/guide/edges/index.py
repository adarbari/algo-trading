"""``GuideEdgeIndex`` (ADR 0051; spec ``docs/ui/guide.md``, "Edges"): the Edges section's top
page. The mechanisms in ``MECHANISM_KINDS`` order, each a card (id, title, question, the
one-line ``short``, the ``examples`` line, how many edges rest on it, the count by status and
the edges as rows); the filter options with their counts (asset class, side, holding band: the
server counts, the browser derives nothing); the edges set aside (status ``rejected`` or
``blocked``, each with the reason on file). The counts are over every site edge. Session-free:
the Guide shows no live number."""

from collections import Counter
from dataclasses import dataclass

from algotrade.config.edges.document import MECHANISM_KINDS, STATUSES
from algotrade.config.site.guide.mechanisms import MechanismProse, load_guide_mechanisms
from algotrade.config.site.guide.sections import EdgeGroup, load_guide_sections
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.edge import ASSET_TEXT, GuideEdgeRow, edge_row
from algotrade.services.read.guide.edges.schedule import BANDS
from algotrade.services.read.guide.edges.site_edges import SiteEdge, site_edges
from algotrade.services.read.guide.edges.universe import ASSETS
from algotrade.services.read.guide.prose import LinkedProse, link_prose

SET_ASIDE = ("rejected", "blocked")
SIDE_TEXT = {"long": "Long", "short": "Short", "long_short": "Long and short"}
BAND_TEXT = {"short": "Up to 5 sessions", "medium": "6 to 21 sessions", "long": "Over 21 sessions"}


@dataclass(frozen=True)
class GuideStatusCount:
    """How many of a mechanism's edges have ``status`` (``document.STATUSES`` order, none
    with zero)."""

    status: str
    count: int


@dataclass(frozen=True)
class GuideMechanismCard:
    id: str
    title: str
    question: str
    short: str
    examples: str
    count: int
    statuses: tuple[GuideStatusCount, ...]
    edges: tuple[GuideEdgeRow, ...]


@dataclass(frozen=True)
class GuideFilterOption:
    """A value of a filter: its ``id`` (what an edge row carries), ``text`` and how many edges
    have it."""

    id: str
    text: str
    count: int


@dataclass(frozen=True)
class GuideMechanismEntry:
    """A mechanism in the Guide's index: its id, title and how many edges rest on it."""

    id: str
    title: str
    count: int


@dataclass(frozen=True)
class GuideEdgeFilters:
    assets: tuple[GuideFilterOption, ...]
    sides: tuple[GuideFilterOption, ...]
    holdings: tuple[GuideFilterOption, ...]


@dataclass(frozen=True)
class GuideSetAsideEdge:
    """An edge set aside: its row and ``why``, the reason on file."""

    edge: GuideEdgeRow
    why: LinkedProse


@dataclass(frozen=True)
class GuideEdgeIndex:
    mechanisms: tuple[GuideMechanismCard, ...]
    filters: GuideEdgeFilters
    set_aside_title: str
    set_aside_purpose: str
    set_aside: tuple[GuideSetAsideEdge, ...]


def load_guide_edge_index(ctx: Stores) -> GuideEdgeIndex:
    """The Edges section's top page (module docstring)."""
    edges = site_edges(ctx)
    prose = load_guide_mechanisms(ctx.configs)
    cards = tuple(
        _card(m, [e for e in edges if e.mechanism == m.id])
        for kind in MECHANISM_KINDS
        if (m := prose.get(kind)) is not None
    )
    fields = catalog_of(ctx.features).fields
    group = _group(ctx, "set_aside")
    set_aside = tuple(
        GuideSetAsideEdge(edge_row(e), link_prose(e.edge.rejection_reason, fields))
        for status in SET_ASIDE
        for e in edges
        if e.edge.status == status and e.edge.rejection_reason.strip()
    )
    return GuideEdgeIndex(
        mechanisms=cards,
        filters=_filters(edges),
        set_aside_title=group.title if group is not None else "",
        set_aside_purpose=group.purpose if group is not None else "",
        set_aside=set_aside,
    )


def edge_entries(ctx: Stores) -> int:
    """How many entries the Edges section holds: its mechanisms and its edges."""
    found = load_guide_mechanisms(ctx.configs).mechanisms
    return len(found) + len(site_edges(ctx)) if found else 0


def mechanism_entries(ctx: Stores) -> tuple[GuideMechanismEntry, ...]:
    """The mechanisms in ``MECHANISM_KINDS`` order with their edge counts (the Guide index's
    rail)."""
    prose = load_guide_mechanisms(ctx.configs)
    counts = Counter(e.mechanism for e in site_edges(ctx))
    return tuple(
        GuideMechanismEntry(m.id, m.title, counts[m.id])
        for kind in MECHANISM_KINDS
        if (m := prose.get(kind)) is not None
    )


def _group(ctx: Stores, group_id: str) -> EdgeGroup | None:
    return next((g for g in load_guide_sections(ctx.configs).edge_groups if g.id == group_id), None)


def _card(m: MechanismProse, members: list[SiteEdge]) -> GuideMechanismCard:
    counts = Counter(e.edge.status for e in members)
    return GuideMechanismCard(
        id=m.id,
        title=m.title,
        question=m.question,
        short=m.short,
        examples=m.examples,
        count=len(members),
        statuses=tuple(GuideStatusCount(s, counts[s]) for s in STATUSES if counts[s]),
        edges=tuple(edge_row(e) for e in members),
    )


def _filters(edges: tuple[SiteEdge, ...]) -> GuideEdgeFilters:
    assets = Counter(e.asset for e in edges)
    sides = Counter(e.side for e in edges)
    bands = Counter(e.band for e in edges)
    return GuideEdgeFilters(
        assets=tuple(GuideFilterOption(a, ASSET_TEXT[a], assets[a]) for a in ASSETS if assets[a]),
        sides=tuple(GuideFilterOption(s, SIDE_TEXT[s], sides[s]) for s in SIDE_TEXT if sides[s]),
        holdings=tuple(GuideFilterOption(b, BAND_TEXT[b], bands[b]) for b in BANDS if bands[b]),
    )
