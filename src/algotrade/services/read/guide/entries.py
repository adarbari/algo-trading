"""Many Guide entries in one read (ADR 0051, ADR 0037): the regime indicators, episodes,
mechanisms, edges, glossary terms and Start here pages a page's help buttons name, each by its
kind and id, read through the single-entry loaders (``regime``, ``edges``, ``written``). Each
distinct ref is read once; a ref with no entry is left out; each list keeps the order of the
refs."""

from dataclasses import dataclass
from enum import Enum

from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.edge import GuideEdgeEntry, load_guide_edge
from algotrade.services.read.guide.edges.mechanism import GuideMechanism, load_guide_mechanism
from algotrade.services.read.guide.regime import (
    GuideEpisodeDetail,
    GuideIndicatorDetail,
    load_guide_episode,
    load_guide_indicator,
)
from algotrade.services.read.guide.written import (
    GuideStartPage,
    GuideTerm,
    load_guide_start_page,
    load_guide_term,
)


class GuideEntryKind(Enum):
    INDICATOR = "indicator"
    EPISODE = "episode"
    TERM = "term"
    START = "start"
    MECHANISM = "mechanism"
    EDGE = "edge"


@dataclass(frozen=True)
class GuideRef:
    """One entry asked for: its ``kind`` and ``id`` (an indicator's key, an episode's slug, a
    term's or Start here page's id)."""

    kind: GuideEntryKind
    id: str


@dataclass(frozen=True)
class GuideEntries:
    indicators: tuple[GuideIndicatorDetail, ...]
    episodes: tuple[GuideEpisodeDetail, ...]
    terms: tuple[GuideTerm, ...]
    start_pages: tuple[GuideStartPage, ...]
    mechanisms: tuple[GuideMechanism, ...]
    edges: tuple[GuideEdgeEntry, ...]


def load_guide_entries(ctx: Stores, refs: list[GuideRef]) -> GuideEntries:
    """The entries ``refs`` name (module docstring)."""
    indicators: list[GuideIndicatorDetail] = []
    episodes: list[GuideEpisodeDetail] = []
    terms: list[GuideTerm] = []
    pages: list[GuideStartPage] = []
    mechanisms: list[GuideMechanism] = []
    edges: list[GuideEdgeEntry] = []
    for ref in dict.fromkeys(refs):
        if ref.kind is GuideEntryKind.INDICATOR:
            if (i := load_guide_indicator(ctx, ref.id)) is not None:
                indicators.append(i)
        elif ref.kind is GuideEntryKind.EPISODE:
            if (e := load_guide_episode(ctx, ref.id)) is not None:
                episodes.append(e)
        elif ref.kind is GuideEntryKind.TERM:
            if (t := load_guide_term(ctx, ref.id)) is not None:
                terms.append(t)
        elif ref.kind is GuideEntryKind.MECHANISM:
            if (m := load_guide_mechanism(ctx, ref.id)) is not None:
                mechanisms.append(m)
        elif ref.kind is GuideEntryKind.EDGE:
            if (x := load_guide_edge(ctx, ref.id)) is not None:
                edges.append(x)
        elif (s := load_guide_start_page(ctx, ref.id)) is not None:
            pages.append(s)
    return GuideEntries(
        tuple(indicators),
        tuple(episodes),
        tuple(terms),
        tuple(pages),
        tuple(mechanisms),
        tuple(edges),
    )
