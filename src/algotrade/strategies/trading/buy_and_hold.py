"""Equal-weight buy-and-hold: the benchmark every other strategy must beat."""

from algotrade.core.market_view import MarketView
from algotrade.core.types import TargetWeights
from algotrade.strategies.trading.base import Strategy


class BuyAndHold(Strategy):
    name = "buy_and_hold"

    def __init__(self) -> None:
        self._invested = False

    def on_bar(self, view: MarketView) -> TargetWeights | None:
        if self._invested:
            return None
        self._invested = True
        weight = 1.0 / len(view.symbols)
        return dict.fromkeys(view.symbols, weight)
