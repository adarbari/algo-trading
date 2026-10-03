"""Backtest configuration. Defaults are deliberately conservative (costs on, no leverage)."""

from dataclasses import dataclass, field

from algotrade.core.errors import ConfigurationError
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.limits import RiskLimits


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    costs: CostModel = field(default_factory=CostModel)
    limits: RiskLimits = field(default_factory=RiskLimits)
    lot_size: float = 1.0
    # Keep a slice of equity uninvested so next-open gaps + costs don't drive cash negative.
    cash_buffer: float = 0.01
    periods_per_year: int = 252

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ConfigurationError("initial_cash must be positive")
        if not 0 <= self.cash_buffer < 1:
            raise ConfigurationError("cash_buffer must be in [0, 1)")
