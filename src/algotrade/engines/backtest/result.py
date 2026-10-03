"""Backtest output."""

from dataclasses import dataclass

from algotrade.analytics.metrics import PerformanceMetrics
from algotrade.core.series import FloatArray, TimeArray
from algotrade.core.types import Fill


@dataclass(frozen=True)
class BacktestResult:
    strategy: str
    params: dict[str, float | int | str]
    timestamps: TimeArray
    equity: FloatArray
    gross_exposure: FloatArray
    fills: tuple[Fill, ...]
    metrics: PerformanceMetrics
