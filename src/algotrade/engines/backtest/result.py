"""Backtest output."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from algotrade.analytics.metrics import PerformanceMetrics
from algotrade.core.model.types import Fill
from algotrade.core.views.series import FloatArray, TimeArray


@dataclass(frozen=True)
class BacktestResult:
    strategy: str
    params: dict[str, float | int | str]
    timestamps: TimeArray
    equity: FloatArray
    gross_exposure: FloatArray
    fills: tuple[Fill, ...]
    metrics: PerformanceMetrics
    # bars on which an overlay changed the weights, per reason (ADR 0049); empty without one
    overlay_reasons: Mapping[str, int] = field(default_factory=dict)
