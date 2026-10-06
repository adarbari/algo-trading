"""The regime gate's inputs for one screen run (ADR 0049): the session's market values for the
names the run asks for (``[regime] label`` when the gate is enabled), read from exactly that
session's partition of the market feature groups (``data.rollups.group_view``; a session with
no row or no partition reads as ``None``, unknown, never an older session), and the
``RegimeGate`` the screening engine applies from the resolved ``[regime]`` settings."""

from collections.abc import Sequence
from datetime import date, datetime

from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.core.model.instruments import market_id
from algotrade.core.views.feature_view import FeatureValue
from algotrade.data import StoreReader
from algotrade.data.rollups import group_view
from algotrade.engines.screening.gate import RegimeGate
from algotrade.services.views import to_value

MARKET = market_id("US")  # the market whose row the gate reads (ADR 0047)


def session_market(
    reader: StoreReader, names: Sequence[str], session: date, as_of: datetime | None = None
) -> dict[str, FeatureValue]:
    """``names`` (market feature fields) for ``session``: ``None`` where nothing is stored."""
    if not names:
        return {}
    frame, _ = group_view(reader, session, sorted(set(names)), [MARKET], as_of)
    row = frame.iloc[0]
    return {n: to_value(row[n]) if n in frame.columns else None for n in names}


def market_names(config: ResolvedConfig) -> tuple[str, ...]:
    """The market values a screen run of ``config`` reads (none while the gate is off)."""
    regime = config.regime
    return (regime.label,) if regime.enabled else ()


def regime_gate(config: ResolvedConfig, market: dict[str, FeatureValue]) -> RegimeGate | None:
    """The gate for a run of ``config`` (``None`` while ``[regime]`` is off)."""
    regime = config.regime
    if not regime.enabled:
        return None
    return RegimeGate(
        screener=config.config.id,
        label=market.get(regime.label),
        multipliers=regime.multipliers,
        pause_in=config.gate_pauses,
        unknown_multiplier=regime.unknown_multiplier,
    )
