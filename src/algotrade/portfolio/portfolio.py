"""Cash and position bookkeeping. The single source of truth for what we own."""

from collections.abc import Mapping
from types import MappingProxyType

from algotrade.core.types import Fill

_EPSILON = 1e-9


class Portfolio:
    def __init__(self, initial_cash: float) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.cash = initial_cash
        self._positions: dict[str, float] = {}
        self.total_commission = 0.0

    @property
    def positions(self) -> Mapping[str, float]:
        return MappingProxyType(self._positions)

    def apply_fill(self, fill: Fill) -> None:
        self.cash -= fill.signed_quantity * fill.price + fill.commission
        self.total_commission += fill.commission
        qty = self._positions.get(fill.symbol, 0.0) + fill.signed_quantity
        if abs(qty) < _EPSILON:
            self._positions.pop(fill.symbol, None)
        else:
            self._positions[fill.symbol] = qty

    def market_value(self, prices: Mapping[str, float]) -> float:
        return sum(qty * prices[s] for s, qty in self._positions.items())

    def equity(self, prices: Mapping[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def gross_exposure(self, prices: Mapping[str, float]) -> float:
        equity = self.equity(prices)
        if equity <= 0:
            return float("inf")
        return sum(abs(qty * prices[s]) for s, qty in self._positions.items()) / equity
