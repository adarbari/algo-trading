"""OHLCV sanity checks, the one definition (storage validates bars on write with it; the
synthetic golden source checks its files with it). Bad bars silently produce great-looking
backtests.

Plain numpy on purpose: it runs on every partition written, often thousands per backfill,
and ``core`` stays free of pandas.
"""

import numpy as np
from numpy.typing import ArrayLike


def ohlcv_problems(
    open_: ArrayLike, high: ArrayLike, low: ArrayLike, close: ArrayLike, volume: ArrayLike
) -> list[str]:
    """Problems with these bars (columns as arrays); an empty list means they are sane."""
    o, h, lo, c, v = (np.asarray(a, dtype=np.float64) for a in (open_, high, low, close, volume))
    prices = np.stack([o, h, lo, c])
    if np.isnan(prices).any() or np.isnan(v).any():
        return ["bars contain NaN prices or volume"]
    problems: list[str] = []
    if (prices <= 0).any():
        problems.append("non-positive prices")
    if (v < 0).any():
        problems.append("negative volume")
    if (h < np.maximum(o, c)).any():
        problems.append("high below open/close")
    if (lo > np.minimum(o, c)).any():
        problems.append("low above open/close")
    return problems
