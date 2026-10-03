"""Turn target weights into the orders needed to reach them."""

import math
from collections.abc import Mapping
from datetime import datetime

from algotrade.core.model.types import Order, Side, TargetWeights


def targets_to_orders(
    targets: TargetWeights,
    positions: Mapping[str, float],
    prices: Mapping[str, float],
    equity: float,
    timestamp: datetime,
    lot_size: float = 1.0,
    multipliers: Mapping[str, float] | None = None,
) -> list[Order]:
    """Orders to move from ``positions`` to ``targets``. Sells are emitted before buys.

    Quantities are rounded toward zero to a multiple of ``lot_size`` so we never
    overshoot a target (and never accidentally use more cash than intended). A position's
    value is ``quantity * price * multiplier``; missing multipliers default to 1.
    """
    multipliers = multipliers or {}
    sells: list[Order] = []
    buys: list[Order] = []
    for instrument in sorted(set(targets) | set(positions)):
        current = positions.get(instrument, 0.0)
        unit_value = prices[instrument] * multipliers.get(instrument, 1.0)
        desired = targets.get(instrument, 0.0) * equity / unit_value
        delta = _round_lots(desired - current, lot_size)
        if delta == 0:
            continue
        side = Side.BUY if delta > 0 else Side.SELL
        order = Order(instrument, side, abs(delta), timestamp)
        (buys if side is Side.BUY else sells).append(order)
    return sells + buys


def _round_lots(quantity: float, lot_size: float) -> float:
    lots = math.trunc(round(quantity / lot_size, 9))
    return lots * lot_size
