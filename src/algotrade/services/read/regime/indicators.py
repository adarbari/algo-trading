"""The regime's indicators (ADR 0047): every card of ``config/site/regime/cards.toml`` joined to
its catalogue value for exactly ``ctx.session``. ``status`` is the indicator's own verdict (its
``<feature>_on`` column: ON, OFF, or UNKNOWN when that column or the value is not stored for the
session) and ``changed`` whether that verdict differs from 5 sessions earlier (its
``<feature>_changed`` column); neither is derived here from the value or from another session.
Cards in file order, so a page lists them as the site reviewed them.

What explains the value comes from where it is decided, never a copy: the ``threshold`` (the
site's ``rollups.toml`` value of the card's primary threshold) and ``direction`` (which side is
the risk) from the code's ``Card`` (``features/rollups/market/indicators.py``; ``None`` for a
card the code has no rule for); ``range`` and the linked ``how`` from ``cards.toml``; the
``sources`` from the catalogue's lineage (``sources.py``)."""

from dataclasses import dataclass
from enum import StrEnum

from algotrade.config.site.regime.cards import RegimeCard, load_cards
from algotrade.config.site.settings import load_macro
from algotrade.core.views.feature_view import FeatureValue as Scalar
from algotrade.features.rollups.market import indicators as rules
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.regime.fields import CHANGED, ON, Reading, read_fields, site_params
from algotrade.services.read.regime.sources import IndicatorSource, load_sources
from algotrade.services.read.values import Unknown


class IndicatorStatus(StrEnum):
    """An indicator's verdict for the session."""

    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


class RiskDirection(StrEnum):
    """Which side of its threshold an indicator warns on."""

    HIGHER_IS_RISK = "HIGHER_IS_RISK"
    LOWER_IS_RISK = "LOWER_IS_RISK"


@dataclass(frozen=True)
class Rule:
    """A card's primary threshold under the site's params and the side that is the risk."""

    threshold: float
    direction: RiskDirection


@dataclass(frozen=True)
class IndicatorLink:
    """One reading-list entry of a card."""

    title: str
    url: str


@dataclass(frozen=True)
class IndicatorRange:
    """A meter's display range, in the value's stored unit."""

    min: float
    max: float


@dataclass(frozen=True)
class TextPart:
    """A run of a sentence: plain text (``url`` ``None``) or a linked term."""

    text: str
    url: str | None


@dataclass(frozen=True)
class IndicatorBefore:
    """What the indicator did before one episode (``episode``: ``"2008"``), in one line."""

    episode: str
    line: str


@dataclass(frozen=True)
class RegimeIndicator:
    """One card with its value for the session. ``value`` is ``None`` exactly when ``unknown``
    says why; ``pace``: ``slow`` (macro) or ``fast`` (market); ``changed``: ``None`` when not
    stored. ``range``: the meter's display range and ``threshold`` (both in the value's stored
    unit) with ``direction``; ``how``: the calculation as plain and linked parts;
    ``sources``: where the value comes from; ``verdict_feature``: the catalogue field of
    ``status``."""

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
    range: IndicatorRange
    threshold: float | None
    direction: RiskDirection | None
    how: tuple[TextPart, ...]
    sources: tuple[IndicatorSource, ...]
    verdict_feature: str


def _status(verdict: Reading) -> IndicatorStatus:
    if verdict.value is None:
        return IndicatorStatus.UNKNOWN
    return IndicatorStatus.ON if bool(verdict.value) else IndicatorStatus.OFF


def _rules(ctx: ReadContext) -> dict[str, Rule]:
    """Per card key of the code, its threshold under the site's ``rollups.toml`` and its
    direction."""
    params = site_params(ctx, rules.GROUP)
    lower, higher = RiskDirection.LOWER_IS_RISK, RiskDirection.HIGHER_IS_RISK
    return {
        c.key: Rule(c.threshold_of(params), lower if c.lower_is_risk else higher)
        for c in rules.CARDS
    }


def _indicator(
    card: RegimeCard,
    read: dict[str, Reading],
    rule: Rule | None,
    sources: tuple[IndicatorSource, ...],
) -> RegimeIndicator:
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
        range=IndicatorRange(card.range.min, card.range.max),
        threshold=rule.threshold if rule else None,
        direction=rule.direction if rule else None,
        how=tuple(TextPart(p.text, p.url) for p in card.how),
        sources=sources,
        verdict_feature=card.feature + ON,
    )


def load_indicators(ctx: ReadContext) -> tuple[RegimeIndicator, ...]:
    """Every card, in file order, with its value, verdict and change for ``ctx.session``, its
    threshold and direction, and its sources with their provenance."""
    doc = load_cards(ctx.configs)
    cards = doc.cards
    names = [n for c in cards for n in (c.feature, c.feature + ON, c.feature + CHANGED)]
    read = read_fields(ctx, names)
    lineage = {c.key: (c.feature, c.feature + ON) for c in cards}
    sources = load_sources(ctx, lineage, load_macro(ctx.configs), doc.sources)
    found = _rules(ctx)
    return tuple(_indicator(card, read, found.get(card.key), sources[card.key]) for card in cards)
