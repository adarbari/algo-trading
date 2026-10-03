"""Explicit registry of strategies available to the CLI and the evaluation suite.

Adding a strategy = add a module + one line here + tests. Explicit beats import-time magic.
"""

from collections.abc import Callable, Mapping

from algotrade.core.model.errors import ConfigurationError
from algotrade.strategies.trading.base import Strategy
from algotrade.strategies.trading.buy_and_hold import BuyAndHold
from algotrade.strategies.trading.sma_crossover import SmaCrossover
from algotrade.strategies.trading.zscore_mean_reversion import ZScoreMeanReversion

type StrategyFactory = Callable[..., Strategy]

STRATEGIES: Mapping[str, StrategyFactory] = {
    BuyAndHold.name: BuyAndHold,
    SmaCrossover.name: SmaCrossover,
    ZScoreMeanReversion.name: ZScoreMeanReversion,
}


def create_strategy(name: str, **params: float | int | str) -> Strategy:
    if name not in STRATEGIES:
        raise ConfigurationError(f"Unknown strategy {name!r}; available: {sorted(STRATEGIES)}")
    try:
        return STRATEGIES[name](**params)
    except TypeError as exc:
        raise ConfigurationError(f"Bad parameters for {name!r}: {exc}") from exc
