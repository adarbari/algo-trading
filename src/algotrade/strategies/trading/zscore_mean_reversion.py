"""Long-only z-score mean reversion: buy oversold, exit on reversion to the mean."""

import numpy as np

from algotrade.core.errors import ConfigurationError
from algotrade.core.market_view import MarketView
from algotrade.core.types import TargetWeights
from algotrade.strategies.trading.base import Strategy


class ZScoreMeanReversion(Strategy):
    name = "zscore_mean_reversion"

    def __init__(self, lookback: int = 20, entry_z: float = 1.5, exit_z: float = 0.0) -> None:
        if lookback < 2:
            raise ConfigurationError("lookback must be at least 2")
        if exit_z >= entry_z:
            raise ConfigurationError("exit_z must be below entry_z")
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self._held: set[str] = set()

    @property
    def warmup_bars(self) -> int:
        return self.lookback

    def _zscore(self, view: MarketView, instrument: str) -> float:
        window = view.history(instrument, lookback=self.lookback)
        std = float(np.std(window, ddof=1))
        if std == 0:
            return 0.0
        return (float(window[-1]) - float(np.mean(window))) / std

    def on_bar(self, view: MarketView) -> TargetWeights | None:
        before = set(self._held)
        for instrument in view.instruments:
            z = self._zscore(view, instrument)
            if instrument not in self._held and z <= -self.entry_z:
                self._held.add(instrument)
            elif instrument in self._held and z >= -self.exit_z:
                self._held.discard(instrument)
        if self._held == before:
            return None
        return dict.fromkeys(sorted(self._held), 1.0 / len(view.instruments))

    def params(self) -> dict[str, float | int | str]:
        return {"lookback": self.lookback, "entry_z": self.entry_z, "exit_z": self.exit_z}
