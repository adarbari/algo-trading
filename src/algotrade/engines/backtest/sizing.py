"""Turn target weights into the orders needed to reach them."""

import math
from collections.abc import Mapping
from datetime import datetime

from algotrade.core.types import Order, Side, TargetWeights


def targets_to_orders(
    targets: TargetWeights,
    positions: Mapping[str, float],
    prices: Mapping[str, float],
    equity: float,
    timestamp: datetime,
    lot_size: float = 1.0,
) -> list[Order]:
    """Orders to move from ``positions`` to ``targets``. Sells are emitted before buys.

    Quantities are rounded toward zero to a multiple of ``lot_size`` so we never
    overshoot a target (and never accidentally use more cash than intended).
    """
    sells: list[Order] = []
    buys: list[Order] = []
    for symbol in sorted(set(targets) | set(positions)):
        current = positions.get(symbol, 0.0)
        desired = targets.get(symbol, 0.0) * equity / prices[symbol]
        delta = _round_lots(desired - current, lot_size)
        if delta == 0:
            continue
        side = Side.BUY if delta > 0 else Side.SELL
        order = Order(symbol, side, abs(delta), timestamp)
        (buys if side is Side.BUY else sells).append(order)
    return sells + buys


def _round_lots(quantity: float, lot_size: float) -> float:
    lots = math.trunc(round(quantity / lot_size, 9))
    return lots * lot_size
