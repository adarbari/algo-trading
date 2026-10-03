"""Standard performance statistics computed from an equity curve and its fills."""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np

from algotrade.core.series import FloatArray
from algotrade.core.types import Fill


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: float
    cagr: float
    annual_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    num_trades: int
    turnover: float  # total traded notional / average equity
    total_commission: float
    exposure: float  # fraction of bars with any position

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


def max_drawdown(equity: FloatArray) -> float:
    """Largest peak-to-trough decline as a positive fraction (0.25 == -25%)."""
    peaks = np.maximum.accumulate(equity)
    return float(np.max(1 - equity / peaks)) if len(equity) else 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 1e-12 else 0.0


def compute_metrics(
    equity: FloatArray,
    fills: Sequence[Fill],
    gross_exposure: FloatArray,
    periods_per_year: int = 252,
) -> PerformanceMetrics:
    if len(equity) < 2:
        raise ValueError("need at least two equity observations")
    returns = np.diff(equity) / equity[:-1]
    years = (len(equity) - 1) / periods_per_year
    total_return = float(equity[-1] / equity[0] - 1)
    cagr = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0
    ann = math.sqrt(periods_per_year)
    vol = float(np.std(returns, ddof=1)) * ann
    downside = returns[returns < 0]
    downside_vol = float(np.sqrt(np.mean(downside**2))) * ann if len(downside) else 0.0
    mean_ret = float(np.mean(returns)) * periods_per_year
    mdd = max_drawdown(equity)
    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        annual_volatility=vol,
        sharpe=_ratio(mean_ret, vol),
        sortino=_ratio(mean_ret, downside_vol),
        max_drawdown=mdd,
        calmar=_ratio(cagr, mdd),
        num_trades=len(fills),
        turnover=sum(f.notional for f in fills) / float(np.mean(equity)),
        total_commission=sum(f.commission for f in fills),
        exposure=float(np.mean(gross_exposure > 1e-9)),
    )
