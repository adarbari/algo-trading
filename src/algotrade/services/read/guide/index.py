"""``GuideIndex`` (ADR 0051): what the Guide holds, in the order the spec fixes
(``config/site/guide/sections.toml``): the sections with their entry counts, the field theme
groups with the number of guided fields per theme, the intents a trader has (each with the
number of fields offering a criterion for it, most first), the situations with the number of
fields each fools, the screeners by family, the regime indicators and reference episodes as
their config holds them, the mechanisms of the Edges section with the number of edges on each
(``edges/index.py``), the Start here pages in order and the glossary terms in file order.
Counts are computed here, never in the browser (ADR 0038)."""

from collections import Counter
from dataclasses import dataclass

from algotrade.config.site.field_guide import FieldGuideSettings
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.site.guide.start import load_guide_start
from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.config.site.settings import load_field_guide
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.edges.index import (
    GuideMechanismEntry,
    edge_entries,
    mechanism_entries,
)
from algotrade.services.read.guide.edges.site_edges import screeners_of
from algotrade.services.read.guide.screeners.site_screeners import SiteScreener


@dataclass(frozen=True)
class GuideSection:
    """One section in order: ``entries``, how many entries it has (0: none written yet)."""

    id: str
    title: str
    purpose: str
    entries: int


@dataclass(frozen=True)
class GuideTheme:
    """A field-guide theme and the number of fields it guides."""

    theme: str
    fields: int


@dataclass(frozen=True)
class GuideThemeGroup:
    id: str
    title: str
    themes: tuple[GuideTheme, ...]


@dataclass(frozen=True)
class GuideIntent:
    """An intent (``use.for``) and the number of fields with a criterion for it."""

    intent: str
    fields: int


@dataclass(frozen=True)
class GuideSituationEntry:
    """A situation, its slug (its page's key) and the number of fields it fools (its
    ``affects``)."""

    name: str
    fields: int
    slug: str


@dataclass(frozen=True)
class GuideScreener:
    """A site preset: its id and display name."""

    id: str
    name: str


@dataclass(frozen=True)
class GuideFamily:
    id: str
    title: str
    screeners: tuple[GuideScreener, ...]


@dataclass(frozen=True)
class GuideIndicator:
    """A regime indicator card: its key (its Guide page's, ``indicator.py``), plain-language
    name and pace (``slow``: macro, ``fast``: market; cards are listed slow first)."""

    key: str
    plain_name: str
    pace: str


@dataclass(frozen=True)
class GuideEpisode:
    """A reference market fall: its key (its Guide page's slug, ``episode.py``) and name."""

    key: str
    name: str


@dataclass(frozen=True)
class GuideStartEntry:
    """A Start here page: its id (its page's key, ``written.py``), number, title and one-line
    summary."""

    id: str
    order: int
    title: str
    summary: str


@dataclass(frozen=True)
class GuideTermEntry:
    """A glossary term: its id (its page's key, ``written.py``), the term as the app writes it
    and its one-sentence ``short`` (the help button's hover)."""

    id: str
    term: str
    short: str


@dataclass(frozen=True)
class GuideIndex:
    sections: tuple[GuideSection, ...]
    theme_groups: tuple[GuideThemeGroup, ...]
    intents: tuple[GuideIntent, ...]
    situations: tuple[GuideSituationEntry, ...]
    families: tuple[GuideFamily, ...]
    indicators: tuple[GuideIndicator, ...]
    episodes: tuple[GuideEpisode, ...]
    start_pages: tuple[GuideStartEntry, ...]
    terms: tuple[GuideTermEntry, ...]
    mechanisms: tuple[GuideMechanismEntry, ...] = ()


def load_guide_index(ctx: Stores) -> GuideIndex:
    """The Guide's index over the site configs ``ctx.configs`` holds (module docstring): built
    once per cache (site files change only with a deploy, which restarts the API; 0.5 s of TOML
    parsing a request before); the site catalogue only (no caller component in the key)."""
    key = ("guide-index",)
    return ctx.cache.get_or_compute(key, lambda: _guide_index(ctx))  # type: ignore[no-any-return]


def _guide_index(ctx: Stores) -> GuideIndex:
    sections = load_guide_sections(ctx.configs)
    guide = load_field_guide(ctx.configs)
    screeners = screeners_of(ctx)
    indicators = tuple(
        GuideIndicator(c.key, c.plain_name, c.pace) for c in load_cards(ctx.configs).cards
    )
    episodes = tuple(GuideEpisode(e.key, e.name) for e in load_episodes(ctx.configs).episodes)
    start = tuple(
        GuideStartEntry(p.id, p.order, p.title, p.summary)
        for p in load_guide_start(ctx.configs).pages
    )
    terms = tuple(
        GuideTermEntry(t.id, t.term, t.short) for t in load_guide_glossary(ctx.configs).terms
    )
    per_theme = Counter(f.theme for f in guide.fields)
    counts = {
        "start": len(start),
        "regime": len(indicators) + len(episodes),
        "edges": edge_entries(ctx),
        "screeners": len(screeners),
        "fields": len(guide.fields),
        "situations": len(guide.situations),
        "glossary": len(terms),
    }
    return GuideIndex(
        sections=tuple(
            GuideSection(s.id, s.title, s.purpose, counts.get(s.id, 0)) for s in sections.sections
        ),
        theme_groups=tuple(
            GuideThemeGroup(g.id, g.title, tuple(GuideTheme(t, per_theme[t]) for t in g.themes))
            for g in sections.theme_groups
        ),
        intents=_intents(guide),
        situations=tuple(
            GuideSituationEntry(s.name, len(s.affects), s.slug) for s in guide.situations
        ),
        families=tuple(
            GuideFamily(f.id, f.title, _members(screeners, f.id)) for f in sections.families
        ),
        indicators=indicators,
        episodes=episodes,
        start_pages=start,
        terms=terms,
        mechanisms=mechanism_entries(ctx),
    )


def _intents(guide: FieldGuideSettings) -> tuple[GuideIntent, ...]:
    """Each intent once, with the number of fields offering it; most fields first, then A-Z."""
    found = Counter(intent for f in guide.fields for intent in {u.intent for u in f.uses})
    ranked = sorted(found.items(), key=lambda item: (-item[1], item[0]))
    return tuple(GuideIntent(intent, n) for intent, n in ranked)


def _members(screeners: tuple[SiteScreener, ...], family: str) -> tuple[GuideScreener, ...]:
    return tuple(GuideScreener(p.id, p.name) for p in screeners if p.family == family)
