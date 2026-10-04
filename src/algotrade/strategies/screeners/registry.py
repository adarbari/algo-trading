"""Explicit registry of screeners available to the pipeline, services and UI.

``rules`` (ADR 0029) is built from the resolved config's ``ScreenSpec``; the others from
scalar ``params``."""

from collections.abc import Callable, Mapping

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.screen_spec import ScreenSpec
from algotrade.strategies.screeners.base import Screener
from algotrade.strategies.screeners.rules import RULES, RuleScreener
from algotrade.strategies.screeners.short_premium_liquidity import ShortPremiumLiquidity

SCREENERS: Mapping[str, Callable[..., Screener]] = {
    ShortPremiumLiquidity.name: ShortPremiumLiquidity,
    RULES: RuleScreener,
}


def create_screener(
    name: str,
    spec: ScreenSpec | None = None,
    params: Mapping[str, float | int | str] | None = None,
) -> Screener:
    if name not in SCREENERS:
        raise ConfigurationError(f"Unknown screener {name!r}; available: {sorted(SCREENERS)}")
    if name == RULES:
        if spec is None:
            raise ConfigurationError("a rule screen needs its spec (impl = 'rules')")
        return RuleScreener(spec)
    if spec is not None:
        raise ConfigurationError(f"{name} is not a rule screen: it takes no spec")
    return SCREENERS[name](**(params or {}))
