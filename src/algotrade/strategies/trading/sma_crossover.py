"""Long-only moving-average crossover (trend following)."""

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.types import TargetWeights
from algotrade.core.views.market_view import MarketView
from algotrade.strategies.trading.base import Strategy


class SmaCrossover(Strategy):
    """Hold an instrument while its fast SMA is above its slow SMA; equal-weight the holdings."""

    name = "sma_crossover"

    def __init__(self, fast: int = 20, slow: int = 100) -> None:
        if not 0 < fast < slow:
            raise ConfigurationError(f"need 0 < fast < slow, got fast={fast} slow={slow}")
        self.fast = fast
        self.slow = slow
        self._held: frozenset[str] = frozenset()

    @property
    def warmup_bars(self) -> int:
        return self.slow

    def on_bar(self, view: MarketView) -> TargetWeights | None:
        held = frozenset(
            s
            for s in view.instruments
            if view.history(s, lookback=self.fast).mean()
            > view.history(s, lookback=self.slow).mean()
        )
        if held == self._held:
            return None
        self._held = held
        if not held:
            return {}
        return dict.fromkeys(sorted(held), 1.0 / len(view.instruments))

    def params(self) -> dict[str, float | int | str]:
        return {"fast": self.fast, "slow": self.slow}
