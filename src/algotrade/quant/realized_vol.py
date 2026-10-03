"""Realised (historical) volatility estimators over a rolling window, annualised (ADR 0021).

Each function takes aligned price arrays (one value per session, oldest first, on axis 0) and
a ``window`` of ``n`` observations, and returns an array of the same shape: the annualised
volatility of the window ENDING at each session (point in time: no later data is used), NaN
until the window is full. A 2-d array holds one series per column (sessions x instruments),
so a whole universe is one call. NaN marks a missing observation: every window that
contains one is NaN (never a shorter window). Annualisation multiplies the per-session variance by
``periods_per_year`` (252 trading sessions, the convention used throughout the project).

    close_to_close  sample stdev of log close-to-close returns (n returns, n + 1 closes)
    parkinson       high-low range: sum ln(H/L)^2 / (4 ln 2 n)            (n bars)
    garman_klass    0.5 ln(H/L)^2 - (2 ln 2 - 1) ln(C/O)^2, averaged       (n bars)
    yang_zhang      overnight + k * open-to-close + (1 - k) * Rogers-Satchell variances,
                    k = 0.34 / (1.34 + (n + 1) / (n - 1))                  (n bars + 1 close)

Range estimators ignore drift and assume continuous trading; Yang-Zhang handles opening
jumps and drift. Prices must be positive (or NaN: missing); ``ValueError`` otherwise.
"""

import math

import numpy as np
import numpy.typing as npt
from numpy.lib.stride_tricks import sliding_window_view

type Array = npt.NDArray[np.float64]

TRADING_DAYS = 252
_LN2 = math.log(2.0)


def _prices(*series: npt.ArrayLike) -> list[Array]:
    arrays = [np.asarray(s, dtype=np.float64) for s in series]
    if any(a.ndim not in (1, 2) for a in arrays) or len({a.shape for a in arrays}) != 1:
        raise ValueError("price series must be 1-d or 2-d arrays of equal length (shape)")
    if any(not np.all((a > 0) | np.isnan(a)) for a in arrays):
        raise ValueError("prices must be positive (NaN: missing)")
    return arrays


def _check_window(window: int, minimum: int) -> None:
    if window < minimum:
        raise ValueError(f"window must be >= {minimum}, got {window}")


def _rolling_mean(values: Array, window: int, offset: int) -> Array:
    """Mean over each window of ``values``, placed so that ``out[i]`` covers data up to
    session ``i`` (``offset``: how many sessions ``values`` lags the price arrays by)."""
    out = np.full((values.shape[0] + offset, *values.shape[1:]), np.nan)
    if values.shape[0] >= window:
        out[offset + window - 1 :] = sliding_window_view(values, window, axis=0).mean(axis=-1)
    return out


def _rolling_var(values: Array, window: int, offset: int) -> Array:
    """Sample variance (ddof=1) over each window, aligned like ``_rolling_mean``."""
    out = np.full((values.shape[0] + offset, *values.shape[1:]), np.nan)
    if values.shape[0] >= window:
        windows = sliding_window_view(values, window, axis=0)
        out[offset + window - 1 :] = windows.var(axis=-1, ddof=1)
    return out


def _annualise(variance: Array, periods_per_year: int) -> Array:
    return np.sqrt(np.maximum(variance, 0.0) * periods_per_year)


def close_to_close(
    close: npt.ArrayLike, window: int, periods_per_year: int = TRADING_DAYS
) -> Array:
    """Annualised sample stdev of the last ``window`` log close-to-close returns."""
    _check_window(window, 2)
    (c,) = _prices(close)
    returns = np.diff(np.log(c), axis=0)
    return _annualise(_rolling_var(returns, window, 1), periods_per_year)


def parkinson(
    high: npt.ArrayLike, low: npt.ArrayLike, window: int, periods_per_year: int = TRADING_DAYS
) -> Array:
    """Parkinson (1980) high-low estimator over the last ``window`` bars."""
    _check_window(window, 1)
    h, lo = _prices(high, low)
    ranges = np.log(h / lo) ** 2 / (4.0 * _LN2)
    return _annualise(_rolling_mean(ranges, window, 0), periods_per_year)


def garman_klass(
    open_: npt.ArrayLike,
    high: npt.ArrayLike,
    low: npt.ArrayLike,
    close: npt.ArrayLike,
    window: int,
    periods_per_year: int = TRADING_DAYS,
) -> Array:
    """Garman-Klass (1980) OHLC estimator over the last ``window`` bars."""
    _check_window(window, 1)
    o, h, lo, c = _prices(open_, high, low, close)
    terms = 0.5 * np.log(h / lo) ** 2 - (2.0 * _LN2 - 1.0) * np.log(c / o) ** 2
    return _annualise(_rolling_mean(terms, window, 0), periods_per_year)


def yang_zhang(
    open_: npt.ArrayLike,
    high: npt.ArrayLike,
    low: npt.ArrayLike,
    close: npt.ArrayLike,
    window: int,
    periods_per_year: int = TRADING_DAYS,
) -> Array:
    """Yang-Zhang (2000) estimator over the last ``window`` bars (needs the close before)."""
    _check_window(window, 2)
    o, h, lo, c = _prices(open_, high, low, close)
    overnight = np.log(o[1:] / c[:-1])
    open_close = np.log(c[1:] / o[1:])
    h1, l1, o1, c1 = h[1:], lo[1:], o[1:], c[1:]
    rogers_satchell = np.log(h1 / c1) * np.log(h1 / o1) + np.log(l1 / c1) * np.log(l1 / o1)
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    variance = (
        _rolling_var(overnight, window, 1)
        + k * _rolling_var(open_close, window, 1)
        + (1.0 - k) * _rolling_mean(rogers_satchell, window, 1)
    )
    return _annualise(variance, periods_per_year)
