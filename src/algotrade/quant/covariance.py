"""Cross-asset stress from a rolling covariance: turbulence and the absorption ratio.

Each function takes a panel of returns (sessions x assets, oldest first on axis 0; one column
per asset) and a ``window`` of observations, and returns one value per session. Every value
uses only rows up to that session (point in time: no later data is used), NaN until the
window is full. NaN marks a missing return: a window (or a session row) that contains one
gives NaN, never a shorter window or a smaller basket. Rows in a window have equal weight.

    turbulence         Kritzman and Li (2010), "Skulls, Financial Turbulence, and Risk
                       Management", FAJ 66(5): the squared Mahalanobis distance of the
                       session's return vector from the mean and covariance of the
                       ``window`` rows strictly BEFORE it,
                       d_t = (y_t - mu)' Sigma^+ (y_t - mu)  (the paper's d_t, not its root)
    absorption_ratio   Kritzman, Li, Page and Rigobon (2011), "Principal Components as a
                       Measure of Systemic Risk", JPM 37(4): the share of total variance
                       explained by the first n eigenvectors of the covariance of the
                       ``window`` rows ENDING at the session (n defaults to N / 5, as there)
    absorption_shift   the same paper's standardised shift,
                       (mean AR over ``short`` - mean AR over ``long``) / stdev AR over ``long``

Singular covariances (fewer rows than assets, a constant or duplicated asset) are handled
with a pseudo-inverse built from ``numpy.linalg.eigh``: eigenvalues at or below
``max eigenvalue * N * machine epsilon`` (numpy's rank tolerance) are dropped, so a
direction with no variance in the window adds nothing to turbulence (a zero covariance gives
0.0). Eigen decompositions are the symmetric LAPACK routines only (``eigh`` / ``eigvalsh``):
no SVD, no randomness, so the same panel gives the same bits on one machine. Column order
changes results only at rounding level; callers sort the assets (by instrument id) for
bit-reproducibility. Use a window several times the number of assets: close to it the
covariance is ill-conditioned and turbulence is dominated by its smallest eigenvalues.
"""

import numpy as np
import numpy.typing as npt

type Array = npt.NDArray[np.float64]


def _panel(returns: npt.ArrayLike) -> Array:
    panel = np.ascontiguousarray(returns, dtype=np.float64)  # one memory layout, one result
    if panel.ndim != 2 or panel.shape[1] < 1:
        raise ValueError("returns must be a 2-d array (sessions x assets) with an asset column")
    return panel


def _check_window(window: int, minimum: int) -> None:
    if window < minimum:
        raise ValueError(f"window must be >= {minimum}, got {window}")


def _quadratic_form(cov: Array, x: Array) -> float:
    """x' cov^+ x, with cov^+ the eigen pseudo-inverse of the symmetric ``cov``."""
    values, vectors = np.linalg.eigh(cov)
    keep = values > values.max(initial=0.0) * cov.shape[0] * np.finfo(np.float64).eps
    projections = vectors[:, keep].T @ x
    return float(np.sum(projections**2 / values[keep]))


def turbulence(returns: npt.ArrayLike, window: int) -> Array:
    """Kritzman-Li turbulence of each session against the ``window`` sessions before it.

    ``out[t]`` uses rows ``t - window .. t - 1`` for the mean and the sample covariance
    (ddof 1) and row ``t`` as the observation, so ``out[:window]`` is NaN.
    """
    _check_window(window, 2)
    panel = _panel(returns)
    out = np.full(panel.shape[0], np.nan)
    for t in range(window, panel.shape[0]):
        history = panel[t - window : t]
        today = panel[t]
        if np.isnan(history).any() or np.isnan(today).any():
            continue
        cov = np.cov(history, rowvar=False, ddof=1).reshape(panel.shape[1], panel.shape[1])
        out[t] = _quadratic_form(cov, today - history.mean(axis=0))
    return out


def absorption_ratio(returns: npt.ArrayLike, window: int, components: int | None = None) -> Array:
    """Share of the window's total variance absorbed by its first ``components`` eigenvectors.

    ``out[t]`` uses rows ``t - window + 1 .. t`` (the window ending at the session), so
    ``out[: window - 1]`` is NaN. ``components`` defaults to ``max(1, N // 5)``. A window
    with no variance at all gives NaN (0 / 0).
    """
    _check_window(window, 2)
    panel = _panel(returns)
    n_assets = panel.shape[1]
    n = max(1, n_assets // 5) if components is None else components
    if not 1 <= n <= n_assets:
        raise ValueError(f"components must be in 1..{n_assets}, got {n}")
    out = np.full(panel.shape[0], np.nan)
    for t in range(window - 1, panel.shape[0]):
        rows = panel[t - window + 1 : t + 1]
        if np.isnan(rows).any():
            continue
        cov = np.cov(rows, rowvar=False, ddof=1).reshape(n_assets, n_assets)
        values = np.clip(np.linalg.eigvalsh(cov), 0.0, None)  # ascending; drop rounding < 0
        total = values.sum()
        if total > 0.0:
            out[t] = values[-n:].sum() / total
    return out


def absorption_shift(ar: npt.ArrayLike, short: int = 15, long: int = 252) -> Array:
    """Standardised shift of the absorption ratio: (short mean - long mean) / long stdev.

    Both windows end at the session; the stdev is the sample stdev (ddof 1) of the ``long``
    window. NaN until ``long`` values exist, when a window holds a NaN, or when the long
    window is constant (no scale to standardise by).
    """
    series = np.asarray(ar, dtype=np.float64)
    if series.ndim != 1:
        raise ValueError("ar must be a 1-d array")
    if not 1 <= short <= long or long < 2:
        raise ValueError(f"need 1 <= short <= long and long >= 2, got {short}, {long}")
    out = np.full(series.shape[0], np.nan)
    for t in range(long - 1, series.shape[0]):
        window = series[t - long + 1 : t + 1]
        if np.isnan(window).any():
            continue
        if np.ptp(window) > 0.0:
            out[t] = (window[-short:].mean() - window.mean()) / window.std(ddof=1)
    return out
