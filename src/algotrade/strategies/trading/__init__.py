"""Trading strategies for backtests.

A strategy is a pure decision function: given a ``MarketView`` (data up to *now*), it
returns target portfolio weights, or ``None`` to leave the portfolio unchanged. It never
places orders, sizes positions or touches I/O; the backtest engine and risk layer do that.
"""

from algotrade.strategies.trading.base import Strategy
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy

__all__ = ["STRATEGIES", "Strategy", "create_strategy"]
