"""``GuideIndicatorDetail`` (ADR 0051): one regime indicator's Guide page, found by its card
key, as ``config/site/regime/cards.toml`` writes it and without any session value (the Regime
page's read, ``services/read/regime/indicators.py``, joins the same card to the session): its
names and pace, the one-liner as ``summary``, why it matters, when it is on, lead time, track
record (the card's ``false_alarms``) and what it did before each reference fall (``before``,
in file order, each with the slug of the episode its label means: ``episode.before_episode``),
all split at the catalogue names they mention; how it is computed (its terms linked); the
catalogue field it reads (``feature``, whose Guide page is the field page) and its reading
list (``sources``)."""

from dataclasses import dataclass

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.regime.episodes import load_episodes
from algotrade.services.configs import catalog_of
from algotrade.services.read.context import Stores
from algotrade.services.read.guide.episode import before_episode
from algotrade.services.read.guide.prose import LinkedProse, link_prose
from algotrade.services.read.regime.indicators import IndicatorLink, TextPart


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
