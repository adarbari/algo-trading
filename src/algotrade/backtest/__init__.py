"""Event-driven backtest engine wiring data -> strategy -> risk -> execution -> portfolio."""

from algotrade.backtest.config import BacktestConfig
from algotrade.backtest.engine import run_backtest
from algotrade.backtest.result import BacktestResult

__all__ = ["BacktestConfig", "BacktestResult", "run_backtest"]
