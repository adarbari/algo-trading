"""Use case: run a configured strategy backtest over stored data."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from algotrade.config.resolve import ResolvedConfig
from algotrade.core.errors import ConfigurationError
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.backtest.limits import RiskLimits
from algotrade.engines.backtest.result import BacktestResult
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.services.market_data import load_price_data
from algotrade.services.selection import select
from algotrade.storage.readers import StoreReader
from algotrade.strategies.trading.registry import create_strategy


def backtest_settings(settings: Mapping[str, Any]) -> BacktestConfig:
    """Resolved ``[backtest]`` settings -> engine config."""
    bt = dict(settings["backtest"])
    return BacktestConfig(
        initial_cash=float(bt["initial_cash"]),
        costs=CostModel(**bt["costs"]),
        limits=RiskLimits(**bt["limits"]),
        lot_size=float(bt["lot_size"]),
        cash_buffer=float(bt["cash_buffer"]),
        periods_per_year=int(bt["periods_per_year"]),
    )


@dataclass(frozen=True)
class BacktestOutcome:
    config: ResolvedConfig
    selection: SelectionResult
    result: BacktestResult


def run_configured_backtest(
    reader: StoreReader, config: ResolvedConfig, start: date, end: date
) -> BacktestOutcome:
    """Selection is evaluated as of ``start`` (no survivorship from today's universe)."""
    if config.config.kind != "strategy":
        raise ConfigurationError(f"{config.config.id} is a {config.config.kind}, not a strategy")
    if config.selection is None:
        raise ConfigurationError(f"{config.config.id}: a backtest needs a selection")
    selected = select(reader, config.selection, start)
    if selected.empty:
        raise ConfigurationError(f"{config.config.id}: selection matched no instruments on {start}")
    data, terms = load_price_data(reader, selected.instruments, start, end)
    strategy = create_strategy(config.config.impl, **dict(config.config.params))
    result = run_backtest(data, strategy, backtest_settings(config.settings), terms)
    return BacktestOutcome(config, selected, result)
