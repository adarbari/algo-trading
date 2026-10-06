"""``MarketRegime`` (ADR 0047, docs/market-regime-plan.md 5.4-5.5) for ``ctx.session``: the
regime label as market weather, its three scores, every indicator card with its value, and the
sizing rule in force, all read by catalogue name from the market's ``MKT:US`` row of exactly the
session (``fields.py``; never an older partition). A label not stored for the session is
``UNKNOWN`` with the reason (``NOT_IN_CATALOGUE`` until the RG3 groups exist); the page says
"Not computed yet" rather than guess a weather. The headline is templated here from the
indicators' counts, so the browser derives nothing (ADR 0038).

Sizing: the multiplier per label, the typed ``[regime] multipliers`` of
``config/site/defaults.toml`` (``config.strategy.regime.site_regime``; the plan's 1 / 0.75 /
0.5 / 0.25 where it sets none), the ``unknown_multiplier`` and, for the caller's screeners as
the config layers resolve them (ADR 0015: a user's copy of a preset, their own ``[regime]``),
the labels each pauses in. The multipliers are the site's: a user layer that sets its own
multipliers changes that screener's runs, not this summary. An UNKNOWN regime has no
multiplier (the overlay fails closed, ADR 0049)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.config.strategy.regime import site_regime
from algotrade.services.read.context import ReadContext
from algotrade.services.read.regime.fields import (
    FRAGILITY,
    LABEL,
    MACRO_RISK,
    MARKET_STRESS,
    Reading,
    read_fields,
)
from algotrade.services.read.regime.indicators import (
    IndicatorStatus,
    RegimeIndicator,
    load_indicators,
)
from algotrade.services.read.screens.screeners import load_screeners
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar


class RegimeLabel(StrEnum):
    """The regime: ``UNKNOWN`` when it is not stored for the session."""

    CALM = "CALM"
    CAUTION = "CAUTION"
    STRESS = "STRESS"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"


PLAIN_LABELS = {
    RegimeLabel.CALM: "Clear",
    RegimeLabel.CAUTION: "Clouds building",
    RegimeLabel.STRESS: "Storm",
    RegimeLabel.CRISIS: "Severe storm",
    RegimeLabel.UNKNOWN: "Not computed yet",
}
KNOWN = (RegimeLabel.CALM, RegimeLabel.CAUTION, RegimeLabel.STRESS, RegimeLabel.CRISIS)
NOT_COMPUTED = "Not computed yet"


@dataclass(frozen=True)
class RegimeScore:
    """One 0-100 score; ``value`` is ``None`` exactly when ``unknown`` says why."""

    value: float | None
    unknown: Unknown | None


@dataclass(frozen=True)
class RegimeScores:
    """``macro_risk`` (slow, weekly), ``market_stress`` (fast, daily) and ``fragility``
    (context only: never changes the label)."""

    macro_risk: RegimeScore
    market_stress: RegimeScore
    fragility: RegimeScore


@dataclass(frozen=True)
class LabelSize:
    """New positions are sized at ``multiplier`` of the normal size in ``label``."""

    label: RegimeLabel
    multiplier: float


@dataclass(frozen=True)
class ScreenerGate:
    """One of the caller's screeners and the labels its picks are PAUSED in (``enabled``:
    its ``[regime]`` gate is on; with it off nothing is paused), calmest first."""

    screener_id: str
    name: str
    enabled: bool
    pause_in: tuple[RegimeLabel, ...]


@dataclass(frozen=True)
class RegimeSizing:
    """The sizing rule in force for the caller: new positions are sized at ``multiplier`` of
    the normal size while the regime is ``label`` (``None``: the regime is UNKNOWN);
    ``enabled``: the gate is on (site-wide or for one of the caller's screeners; off, sizes
    are 100% and nothing pauses); ``multipliers`` per label, ``unknown_multiplier`` for a
    label not stored, and ``screeners`` with the labels each pauses in."""

    label: RegimeLabel
    multiplier: float | None
    enabled: bool
    multipliers: tuple[LabelSize, ...]
    unknown_multiplier: float
    screeners: tuple[ScreenerGate, ...]


@dataclass(frozen=True)
class MarketRegime:
    """The regime for ``session``. ``label`` is UNKNOWN exactly when ``unknown_reason`` says
    why; ``headline`` a sentence from the indicator counts (``Not computed yet`` for UNKNOWN);
    ``indicators`` every card in file order."""

    session: date
    label: RegimeLabel
    plain_label: str
    headline: str
    scores: RegimeScores
    indicators: tuple[RegimeIndicator, ...]
    sizing: RegimeSizing
    unknown_reason: Unknown | None


def _label(reading: Reading) -> tuple[RegimeLabel, Unknown | None]:
    if reading.unknown is not None or reading.value is None:
        return RegimeLabel.UNKNOWN, reading.unknown
    found = next((label for label in KNOWN if label.value == reading.value), None)
    if found is None:
        detail = f"{LABEL} holds {reading.value!r}, not one of {[k.value for k in KNOWN]}"
        return RegimeLabel.UNKNOWN, Unknown(UnknownCode.NULL, detail)
    return found, None


def _score(reading: Reading) -> RegimeScore:
    value = to_scalar(reading.value)
    return RegimeScore(None if value is None else float(value), reading.unknown)


def _sizing(ctx: ReadContext, label: RegimeLabel) -> RegimeSizing:
    """The caller's sizing rule: ``[regime]`` of ``defaults.toml``, typed and validated by
    ``RegimeSettings`` (its defaults where the file sets none), and each screener's resolved
    pauses."""
    regime = site_regime(ctx.configs.load)
    sizes: Mapping[RegimeLabel, float] = {k: regime.multipliers[k.value] for k in KNOWN}
    gates = tuple(
        ScreenerGate(s.id, s.name, s.regime_enabled, tuple(RegimeLabel(p) for p in s.pause_in))
        for s in load_screeners(ctx)
    )
    return RegimeSizing(
        label=label,
        multiplier=sizes.get(label),
        enabled=regime.enabled or any(g.enabled for g in gates),
        multipliers=tuple(LabelSize(k, sizes[k]) for k in KNOWN),
        unknown_multiplier=regime.unknown_multiplier,
        screeners=gates,
    )


def _count(items: list[RegimeIndicator], pace: str) -> tuple[int, int]:
    """``(on, known)`` among the ``pace`` indicators."""
    known = [i for i in items if i.pace == pace and i.status is not IndicatorStatus.UNKNOWN]
    return sum(i.status is IndicatorStatus.ON for i in known), len(known)


def headline(label: RegimeLabel, indicators: tuple[RegimeIndicator, ...]) -> str:
    """The one sentence under the weather: how many slow warning signs and fast signs are on,
    and how many changed in the last 5 sessions (only the indicators with a stored verdict)."""
    if label is RegimeLabel.UNKNOWN:
        return NOT_COMPUTED
    items = list(indicators)
    slow_on, slow = _count(items, "slow")
    fast_on, fast = _count(items, "fast")
    changed = sum(i.changed is True for i in items)
    parts = [
        f"{slow_on} of {slow} slow-moving warning signs are on."
        if slow
        else "The slow-moving warning signs are not available.",
        "The fast signs are quiet."
        if fast and not fast_on
        else f"{fast_on} of {fast} fast signs are on."
        if fast
        else "The fast signs are not available.",
    ]
    if changed:
        parts.append(f"{changed} changed in the last 5 sessions.")
    return " ".join(parts)


def load_regime(ctx: ReadContext) -> MarketRegime:
    """The regime for ``ctx.session``; never ``None`` (nothing stored is an UNKNOWN regime)."""
    read = read_fields(ctx, [LABEL, MACRO_RISK, MARKET_STRESS, FRAGILITY])
    label, reason = _label(read[LABEL])
    indicators = load_indicators(ctx)
    return MarketRegime(
        session=ctx.session.date,
        label=label,
        plain_label=PLAIN_LABELS[label],
        headline=headline(label, indicators),
        scores=RegimeScores(
            _score(read[MACRO_RISK]), _score(read[MARKET_STRESS]), _score(read[FRAGILITY])
        ),
        indicators=indicators,
        sizing=_sizing(ctx, label),
        unknown_reason=reason,
    )
