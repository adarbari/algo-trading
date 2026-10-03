"""Event-driven backtest engine: strategy -> risk limits -> sizing -> simulated broker -> portfolio.

Modules keep their old single responsibilities: ``limits``/``sizing`` (pre-trade risk),
``costs``/``simulated``/``broker`` (execution), ``portfolio`` (accounting), ``engine`` (the loop).
"""

from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.backtest.result import BacktestResult

__all__ = ["BacktestConfig", "BacktestResult", "run_backtest"]
