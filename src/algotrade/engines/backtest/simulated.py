"""Simulated broker: market orders fill at the *next* bar's open, plus costs.

Filling at the next open (rather than the close the decision was made on) is the single
most important guard against flattering backtests. See docs/adr/0002-fill-model.md.

Like a real broker, it enforces buying power: sells execute first, then buys are cut
down (in whole lots) to what the account can afford at the actual fill price.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import datetime

from algotrade.core.types import Fill, Order, Side
from algotrade.engines.backtest.costs import CostModel


class SimulatedBroker:
    def __init__(self, costs: CostModel | None = None, lot_size: float = 1.0) -> None:
        self.costs = costs or CostModel()
        self.lot_size = lot_size
        self._pending: list[Order] = []

    @property
    def pending(self) -> tuple[Order, ...]:
        return tuple(self._pending)

    def submit(self, orders: Sequence[Order]) -> None:
        self._pending.extend(orders)

    def cancel_all(self) -> None:
        self._pending.clear()

    def execute_pending(
        self,
        open_prices: Mapping[str, float],
        timestamp: datetime,
        buying_power: float = math.inf,
    ) -> list[Fill]:
        fills: list[Fill] = []
        ordered = sorted(self._pending, key=lambda o: o.side is Side.BUY)  # sells first
        for order in ordered:
            price = self.costs.fill_price(order.side, open_prices[order.symbol])
            quantity = order.quantity
            if order.side is Side.BUY:
                quantity = self._affordable(quantity, price, buying_power)
                if quantity <= 0:
                    continue
            commission = self.costs.commission(quantity * price)
            buying_power -= order.side.sign * quantity * price + commission
            fills.append(Fill(order.symbol, order.side, quantity, price, commission, timestamp))
        self._pending.clear()
        return fills

    def _affordable(self, quantity: float, price: float, buying_power: float) -> float:
        def cost(q: float) -> float:
            return q * price + self.costs.commission(q * price)

        if cost(quantity) <= buying_power:
            return quantity
        per_unit = price * (1 + self.costs.commission_bps / 10_000)
        lots = math.floor(max(buying_power, 0.0) / per_unit / self.lot_size)
        while lots > 0 and cost(lots * self.lot_size) > buying_power:
            lots -= 1
        return min(quantity, lots * self.lot_size)
