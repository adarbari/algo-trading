"""Deterministic synthetic market data generators (price paths -> OHLCV ``PriceSeries``).

Synthetic data is the backbone of the golden test set: it is free, licence-clean, fully
reproducible, and lets us construct regimes (crashes, chop, trends) on purpose so we can
see how each strategy behaves in each of them.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from algotrade.core.time.clock import business_days
from algotrade.core.views.series import FloatArray, PriceSeries, TimeArray

TRADING_DAYS = 252


@dataclass(frozen=True)
class Regime:
    """A stretch of ``bars`` with constant annualised drift and volatility."""

    bars: int
    drift: float
    vol: float


def gbm_closes(
    rng: np.random.Generator, n: int, start: float, drift: float, vol: float
) -> FloatArray:
    """Geometric Brownian motion closes with annualised ``drift`` and ``vol``."""
    return regime_closes(rng, start, [Regime(n, drift, vol)])


def regime_closes(rng: np.random.Generator, start: float, regimes: Sequence[Regime]) -> FloatArray:
    dt = 1.0 / TRADING_DAYS
    rets = [
        (r.drift - 0.5 * r.vol**2) * dt + r.vol * np.sqrt(dt) * rng.standard_normal(r.bars)
        for r in regimes
    ]
    log_path = np.concatenate([[0.0], np.cumsum(np.concatenate(rets))[:-1]])
    return np.asarray(start * np.exp(log_path), dtype=np.float64)


def ou_closes(
    rng: np.random.Generator, n: int, mean: float, half_life: float, vol: float
) -> FloatArray:
    """Mean-reverting (Ornstein-Uhlenbeck in log space) closes around ``mean``."""
    theta = np.log(2) / half_life
    daily_vol = vol / np.sqrt(TRADING_DAYS)
    log_mean = np.log(mean)
    x = np.empty(n)
    x[0] = log_mean
    shocks = rng.standard_normal(n)
    for t in range(1, n):
        x[t] = x[t - 1] + theta * (log_mean - x[t - 1]) + daily_vol * shocks[t]
    return np.asarray(np.exp(x), dtype=np.float64)


def correlated_gbm(
    rng: np.random.Generator,
    n: int,
    starts: Sequence[float],
    drifts: Sequence[float],
    vols: Sequence[float],
    correlation: float,
) -> list[FloatArray]:
    k = len(starts)
    cov = np.full((k, k), correlation) + np.eye(k) * (1 - correlation)
    shocks = rng.standard_normal((n, k)) @ np.linalg.cholesky(cov).T
    dt = 1.0 / TRADING_DAYS
    out: list[FloatArray] = []
    for i in range(k):
        rets = (drifts[i] - 0.5 * vols[i] ** 2) * dt + vols[i] * np.sqrt(dt) * shocks[:, i]
        log_path = np.concatenate([[0.0], np.cumsum(rets)[:-1]])
        out.append(np.asarray(starts[i] * np.exp(log_path), dtype=np.float64))
    return out


def ohlcv_from_closes(
    symbol: str,
    rng: np.random.Generator,
    timestamps: TimeArray,
    closes: FloatArray,
    intraday_vol: float = 0.01,
    base_volume: float = 1_000_000.0,
) -> PriceSeries:
    """Build plausible OHLCV bars around a close path (open gaps from the prior close)."""
    n = len(closes)
    prev = np.concatenate([[closes[0]], closes[:-1]])
    opens = prev * np.exp(rng.normal(0, intraday_vol / 2, n))
    body_hi = np.maximum(opens, closes)
    body_lo = np.minimum(opens, closes)
    highs = body_hi * (1 + np.abs(rng.normal(0, intraday_vol, n)))
    lows = body_lo * (1 - np.abs(rng.normal(0, intraday_vol, n)))
    volume = np.round(base_volume * rng.lognormal(0, 0.3, n))
    return PriceSeries(
        instrument_id=symbol,
        timestamps=timestamps,
        open=np.round(opens, 4),
        high=np.round(highs, 4) + 0.0001,
        low=np.round(lows, 4) - 0.0001,
        close=np.round(closes, 4),
        volume=volume.astype(np.float64),
    )


__all__ = [
    "Regime",
    "business_days",
    "correlated_gbm",
    "gbm_closes",
    "ohlcv_from_closes",
    "ou_closes",
    "regime_closes",
]  # fmt: skip
