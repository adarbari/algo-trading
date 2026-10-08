"""``GuideEpisodeDetail`` (ADR 0051): one reference market fall's Guide page, found by its slug,
as ``config/site/regime/episodes.toml`` holds it (session-free: every date the file has; the
Regime page's read, ``services/read/regime/episodes.py``, is the one that gates them by
session), with ``cause`` and ``notes`` split at the catalogue names they mention, and the
indicators whose ``before`` line is about it (``indicators``, in card order).

An episode's slug is its ``key`` (unique by the loader; the Guide index carries it). Which
episode a card's ``before`` label means (``"2008"``) is the one rule ``before_episode``: the
one episode whose peak-to-trough years hold the label's year; the indicator page reads it the
other way round. A label no episode or two episodes hold names none (a fitness test fails
it)."""

from collections.abc import Container
from dataclasses import dataclass
from datetime import date

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import Episode, load_episodes
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.prose import LinkedProse, link_prose


@dataclass(frozen=True)
class GuideEpisodeIndicator:
    """A regime indicator whose ``before`` line (``label``: ``"2008"``) is about the episode."""

    key: str
    plain_name: str
    label: str
    line: LinkedProse


@dataclass(frozen=True)
class GuideEpisodeDetail:
    """An episode as the config holds it: ``spx_drawdown`` / ``nasdaq_drawdown`` peak-to-trough
    fractions (zero or negative); ``nber_start`` / ``nber_end`` the recession's first and last
    months (``None``: no recession); ``recovered`` ``None`` while the S&P 500 has not regained
    its peak."""

    slug: str
    name: str
    kind: str
    peak: date
    trough: date
    recovered: date | None
    spx_drawdown: float
    nasdaq_drawdown: float
    recession: bool
    nber_start: date | None
    nber_end: date | None
    known_from: date
    cause: LinkedProse
    notes: LinkedProse
    indicators: tuple[GuideEpisodeIndicator, ...]


def before_episode(label: str, episodes: tuple[Episode, ...]) -> Episode | None:
    """The one episode a ``before`` label means (module docstring); ``None`` for none or two."""
    if not label.isdigit():
        return None
    year = int(label)
    found = [e for e in episodes if e.peak.year <= year <= e.trough.year]
    return found[0] if len(found) == 1 else None


def load_guide_episode(ctx: Stores, slug: str) -> GuideEpisodeDetail | None:
    """The episode ``slug`` names (module docstring); ``None``: no such episode."""
    episodes = load_episodes(ctx.configs).episodes
    e = next((e for e in episodes if e.key == slug), None)
    if e is None:
        return None
    fields = catalog_of(ctx.features).fields
    return GuideEpisodeDetail(
        slug=e.key,
        name=e.name,
        kind=e.kind,
        peak=e.peak,
        trough=e.trough,
        recovered=e.recovered,
        spx_drawdown=e.spx_drawdown,
        nasdaq_drawdown=e.nasdaq_drawdown,
        recession=e.recession,
        nber_start=e.nber_start,
        nber_end=e.nber_end,
        known_from=e.known_from,
        cause=link_prose(e.cause, fields),
        notes=link_prose(e.notes, fields),
        indicators=_indicators(ctx, e, episodes, fields),
    )


def _indicators(
    ctx: Stores, episode: Episode, episodes: tuple[Episode, ...], fields: Container[str]
) -> tuple[GuideEpisodeIndicator, ...]:
    return tuple(
        GuideEpisodeIndicator(card.key, card.plain_name, label, link_prose(line, fields))
        for card in load_cards(ctx.configs).cards
        for label, line in card.before.items()
        if before_episode(label, episodes) == episode
    )
