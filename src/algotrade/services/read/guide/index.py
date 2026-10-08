"""``GuideIndex`` (ADR 0051): what the Guide holds, in the order the spec fixes
(``config/site/guide/sections.toml``): the sections with their entry counts, the field theme
groups with the number of guided fields per theme, the intents a trader has (each with the
number of fields offering a criterion for it, most first), the situations with the number of
fields each fools, the playbooks by family, and the regime indicators and reference episodes
as their config holds them. Counts are computed here, never in the browser (ADR 0038)."""

from collections import Counter
from dataclasses import dataclass

from algotrade.config.site.field_guide import FieldGuideSettings
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.config.site.settings import load_field_guide
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.playbooks import SitePlaybook, site_playbooks


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
class GuidePlaybook:
    """A site preset: its id and display name."""

    id: str
    name: str


@dataclass(frozen=True)
class GuideFamily:
    id: str
    title: str
    playbooks: tuple[GuidePlaybook, ...]


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
class GuideIndex:
    sections: tuple[GuideSection, ...]
    theme_groups: tuple[GuideThemeGroup, ...]
    intents: tuple[GuideIntent, ...]
    situations: tuple[GuideSituationEntry, ...]
    families: tuple[GuideFamily, ...]
    indicators: tuple[GuideIndicator, ...]
    episodes: tuple[GuideEpisode, ...]


def load_guide_index(ctx: Stores) -> GuideIndex:
    """The Guide's index over the site configs ``ctx.configs`` holds (module docstring)."""
    sections = load_guide_sections(ctx.configs)
    guide = load_field_guide(ctx.configs)
    playbooks = site_playbooks(ctx)
    indicators = tuple(
        GuideIndicator(c.key, c.plain_name, c.pace) for c in load_cards(ctx.configs).cards
    )
    episodes = tuple(GuideEpisode(e.key, e.name) for e in load_episodes(ctx.configs).episodes)
    per_theme = Counter(f.theme for f in guide.fields)
    counts = {
        "start": 0,
        "regime": len(indicators) + len(episodes),
        "playbooks": len(playbooks),
        "fields": len(guide.fields),
        "situations": len(guide.situations),
        "glossary": 0,
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
            GuideFamily(f.id, f.title, _members(playbooks, f.id)) for f in sections.families
        ),
        indicators=indicators,
        episodes=episodes,
    )


def _intents(guide: FieldGuideSettings) -> tuple[GuideIntent, ...]:
    """Each intent once, with the number of fields offering it; most fields first, then A-Z."""
    found = Counter(intent for f in guide.fields for intent in {u.intent for u in f.uses})
    ranked = sorted(found.items(), key=lambda item: (-item[1], item[0]))
    return tuple(GuideIntent(intent, n) for intent, n in ranked)


def _members(playbooks: tuple[SitePlaybook, ...], family: str) -> tuple[GuidePlaybook, ...]:
    return tuple(GuidePlaybook(p.id, p.name) for p in playbooks if p.family == family)
