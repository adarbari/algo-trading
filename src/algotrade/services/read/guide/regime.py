"""The regime pages of the Guide (ADR 0051): a market fall and an indicator, read together
because each names the other (``before_episode``).

``GuideEpisodeDetail`` (ADR 0051): one reference market fall's Guide page, found by its slug,
as ``config/site/regime/episodes.toml`` holds it (session-free: every date the file has; the
Regime page's read, ``services/read/regime/episodes.py``, is the one that gates them by
session), with ``cause`` and ``notes`` split at the catalogue names they mention, and the
indicators whose ``before`` line is about it (``indicators``, in card order).

An episode's slug is its ``key`` (unique by the loader; the Guide index carries it). Which
episode a card's ``before`` label means (``"2008"``) is the one rule ``before_episode``: the
one episode whose peak-to-trough years hold the label's year; the indicator page reads it the
other way round. A label no episode or two episodes hold names none (a fitness test fails
it).

``GuideIndicatorDetail`` (ADR 0051): one regime indicator's Guide page, found by its card
key, as ``config/site/regime/cards.toml`` writes it and without any session value (the Regime
page's read, ``services/read/regime/indicators.py``, joins the same card to the session): its
names and pace, the one-liner as ``summary``, why it matters, when it is on, lead time, track
record (the card's ``false_alarms``) and what it did before each reference fall (``before``,
in file order, each with the slug of the episode its label means: ``before_episode``),
all split at the catalogue names they mention; how it is computed (its terms linked); the
catalogue field it reads (``feature``, whose Guide page is the field page) and its reading
list (``sources``)."""

from collections.abc import Container
from dataclasses import dataclass
from datetime import date

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import Episode as EpisodeConfig
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.prose import LinkedProse, link_prose
from algotrade.services.read.regime.episodes import Episode, episode_known_by
from algotrade.services.read.regime.indicators import IndicatorLink, TextPart


@dataclass(frozen=True)
class GuideEpisodeIndicator:
    """A regime indicator whose ``before`` line (``label``: ``"2008"``) is about the episode."""

    key: str
    plain_name: str
    label: str
    line: LinkedProse


@dataclass(frozen=True)
class GuideEpisodeDetail:
    """An episode as the Regime read maps it, with every date the config has (``episode``:
    ``episode_known_by`` as of ``date.max``: the Guide has no session), with ``cause`` and
    ``notes`` linked and the indicators whose ``before`` line is about it."""

    episode: Episode
    cause: LinkedProse
    notes: LinkedProse
    indicators: tuple[GuideEpisodeIndicator, ...]

    @property
    def slug(self) -> str:
        return self.episode.key


def before_episode(label: str, episodes: tuple[EpisodeConfig, ...]) -> EpisodeConfig | None:
    """The one episode a ``before`` label means (module docstring); ``None`` for none or two."""
    if not label.isdecimal():
        return None
    year = int(label)
    found = [e for e in episodes if e.peak.year <= year <= e.trough.year]
    return found[0] if len(found) == 1 else None


def load_guide_episode(ctx: Stores, slug: str) -> GuideEpisodeDetail | None:
    """The episode ``slug`` names (module docstring); ``None``: no such episode."""
    config = load_episodes(ctx.configs)
    episodes = config.episodes
    e = next((e for e in episodes if e.key == slug), None)
    if e is None:
        return None
    fields = catalog_of(ctx.features).fields
    return GuideEpisodeDetail(
        episode=episode_known_by(e, date.max, config.recessions),
        cause=link_prose(e.cause, fields),
        notes=link_prose(e.notes, fields),
        indicators=_indicators(ctx, e, episodes, fields),
    )


def _indicators(
    ctx: Stores,
    episode: EpisodeConfig,
    episodes: tuple[EpisodeConfig, ...],
    fields: Container[str],
) -> tuple[GuideEpisodeIndicator, ...]:
    return tuple(
        GuideEpisodeIndicator(card.key, card.plain_name, label, link_prose(line, fields))
        for card in load_cards(ctx.configs).cards
        for label, line in card.before.items()
        if (found := before_episode(label, episodes)) is not None and found.key == episode.key
    )


@dataclass(frozen=True)
class GuideIndicatorBefore:
    """What the indicator did before one reference fall: ``label`` as the card writes it
    (``"2008"``), ``episode`` the slug of the episode it means (``None``: none does)."""

    label: str
    line: LinkedProse
    episode: str | None


@dataclass(frozen=True)
class GuideIndicatorDetail:
    """A card's explanation; ``pace``: ``slow`` (macro) or ``fast`` (market)."""

    key: str
    plain_name: str
    technical_name: str
    pace: str
    summary: LinkedProse
    why_it_matters: LinkedProse
    what_on_means: LinkedProse
    lead_time: LinkedProse
    track_record: LinkedProse
    before: tuple[GuideIndicatorBefore, ...]
    how: tuple[TextPart, ...]
    feature: str
    sources: tuple[IndicatorLink, ...]


def load_guide_indicator(ctx: Stores, key: str) -> GuideIndicatorDetail | None:
    """The card ``key`` names (module docstring); ``None``: no such card."""
    card = next((c for c in load_cards(ctx.configs).cards if c.key == key), None)
    if card is None:
        return None
    fields = catalog_of(ctx.features).fields
    episodes = load_episodes(ctx.configs).episodes

    def linked(text: str) -> LinkedProse:
        return link_prose(text, fields)

    def slug(label: str) -> str | None:
        found = before_episode(label, episodes)
        return found.key if found is not None else None

    return GuideIndicatorDetail(
        key=card.key,
        plain_name=card.plain_name,
        technical_name=card.technical_name,
        pace=card.pace,
        summary=linked(card.one_liner),
        why_it_matters=linked(card.why_it_matters),
        what_on_means=linked(card.what_on_means),
        lead_time=linked(card.lead_time),
        track_record=linked(card.false_alarms),
        before=tuple(GuideIndicatorBefore(k, linked(v), slug(k)) for k, v in card.before.items()),
        how=tuple(TextPart(p.text, p.url) for p in card.how),
        feature=card.feature,
        sources=tuple(IndicatorLink(link.title, link.url) for link in card.links),
    )
