"""The regime's indicators (ADR 0047): every card of ``config/site/regime/cards.toml`` joined to
its catalogue value for exactly ``ctx.session``. ``status`` is the indicator's own verdict (its
``<feature>_on`` column: ON, OFF, or UNKNOWN when that column or the value is not stored for the
session) and ``changed`` whether that verdict differs from 5 sessions earlier (its
``<feature>_changed`` column); neither is derived here from the value or from another session.
Cards in file order, so a page lists them as the site reviewed them."""

from dataclasses import dataclass
from enum import StrEnum

from algotrade.config.site.regime.cards import RegimeCard, load_cards
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.regime.fields import CHANGED, ON, Reading, read_fields
from algotrade.services.read.values import Unknown


class IndicatorStatus(StrEnum):
    """An indicator's verdict for the session."""

    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IndicatorLink:
    """One reading-list entry of a card."""

    title: str
    url: str


@dataclass(frozen=True)
class IndicatorBefore:
    """What the indicator did before one episode (``episode``: ``"2008"``), in one line."""

    episode: str
    line: str


@dataclass(frozen=True)
class RegimeIndicator:
    """One card with its value for the session. ``value`` is ``None`` exactly when ``unknown``
    says why; ``pace``: ``slow`` (macro) or ``fast`` (market); ``changed``: ``None`` when not
    stored."""

    key: str
    pace: str
    plain_name: str
    technical_name: str
    one_liner: str
    why_it_matters: str
    what_on_means: str
    before: tuple[IndicatorBefore, ...]
    lead_time: str
    false_alarms: str
    links: tuple[IndicatorLink, ...]
    feature: str
    value: Scalar
    unknown: Unknown | None
    format: FeatureFormat | None
    status: IndicatorStatus
    changed: bool | None


def _status(verdict: Reading) -> IndicatorStatus:
    if verdict.value is None:
        return IndicatorStatus.UNKNOWN
    return IndicatorStatus.ON if bool(verdict.value) else IndicatorStatus.OFF


def _indicator(card: RegimeCard, read: dict[str, Reading]) -> RegimeIndicator:
    value, verdict, changed = (
        read[card.feature],
        read[card.feature + ON],
        read[card.feature + CHANGED],
    )
    return RegimeIndicator(
        key=card.key,
        pace=card.pace,
        plain_name=card.plain_name,
        technical_name=card.technical_name,
        one_liner=card.one_liner,
        why_it_matters=card.why_it_matters,
        what_on_means=card.what_on_means,
        before=tuple(IndicatorBefore(e, line) for e, line in card.before.items()),
        lead_time=card.lead_time,
        false_alarms=card.false_alarms,
        links=tuple(IndicatorLink(link.title, link.url) for link in card.links),
        feature=card.feature,
        value=value.value,
        unknown=value.unknown,
        format=value.format,
        status=_status(verdict),
        changed=None if changed.value is None else bool(changed.value),
    )


def load_indicators(ctx: ReadContext) -> tuple[RegimeIndicator, ...]:
    """Every card, in file order, with its value, verdict and change for ``ctx.session``."""
    cards = load_cards(ctx.configs).cards
    names = [n for c in cards for n in (c.feature, c.feature + ON, c.feature + CHANGED)]
    read = read_fields(ctx, names)
    return tuple(_indicator(card, read) for card in cards)
