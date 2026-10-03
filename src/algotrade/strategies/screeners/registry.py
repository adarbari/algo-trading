"""Explicit registry of screeners available to the pipeline, services and UI."""

from collections.abc import Callable, Mapping

from algotrade.core.errors import ConfigurationError
from algotrade.strategies.screeners.base import Screener
from algotrade.strategies.screeners.short_premium_liquidity import ShortPremiumLiquidity

SCREENERS: Mapping[str, Callable[..., Screener]] = {
    ShortPremiumLiquidity.name: ShortPremiumLiquidity,
}


def create_screener(name: str, **params: float | int | str) -> Screener:
    if name not in SCREENERS:
        raise ConfigurationError(f"Unknown screener {name!r}; available: {sorted(SCREENERS)}")
    return SCREENERS[name](**params)
