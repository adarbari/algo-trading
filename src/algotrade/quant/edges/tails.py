"""The tail and resampling statistics of a setup's return on capital (ADR 0088, design 2.6): CVaR at
a level with the count of windows in the tail, the worst window, the stationary block bootstrap
(Politis and Romano 1994) of a mean, and the probabilistic Sharpe ratio. Pure numpy, no global
random state: a bootstrap is a function of (values, mean block, draws, seed), drawn in fixed chunks
of rows so memory is bounded and the result does not depend on the chunk size."""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from algotrade.quant.edges.statistics import deflated_sharpe

Array = npt.NDArray[np.float64]
CHUNK = 250  # bootstrap rows drawn at once: at most CHUNK x n cells are held, never draws x n
INTERVAL = (0.05, 0.95)  # the 90% interval
_FLAT = 1e-12  # a spread of the draw means below this is float noise of a constant series: no t


@dataclass(frozen=True)
class Bootstrap:
    """The mean of the series, the 5% and 95% quantiles of the draw means, and the t ratio
    ``mean / sd(draw means)``; all None when the series has fewer than two values (``draws``: 0)."""

    mean: float | None = None
    lo: float | None = None
    hi: float | None = None
    t: float | None = None
    draws: int = 0


def _finite(values: npt.ArrayLike) -> Array:
    arr = np.asarray(values, dtype=np.float64).ravel()
    return arr[np.isfinite(arr)]


def tail_count(n: int, alpha: float) -> int:
    """The windows in the ``alpha`` tail of ``n``: ``ceil(alpha n)``, at least 1 when ``n > 0``.
    The float is guarded (``0.07 * 100`` is 7.000000000000001 and must give 7, not 8)."""
    if n <= 0:
        return 0
    return max(1, math.ceil(alpha * n - 1e-9))


def cvar(values: npt.ArrayLike, alpha: float) -> tuple[float | None, int]:
    """The mean of the ``tail_count`` lowest finite values and that count; ``(None, 0)`` with no
    value. A return (negative for a loss), never a positive loss figure."""
    v = _finite(values)
    if v.size == 0:
        return None, 0
    k = tail_count(int(v.size), alpha)
    return float(np.sort(v)[:k].mean()), k


def worst(values: npt.ArrayLike) -> float | None:
    """The lowest finite value; None with none."""
    v = _finite(values)
    return float(v.min()) if v.size else None


def _uniforms(rng: np.random.Generator, rows: int, n: int) -> Array:
    return rng.random((rows, n))


def stationary_indices(u: Array, mean_block: float) -> npt.NDArray[np.int64]:
    """The circular stationary-bootstrap index rows for the uniforms ``u`` (rows x n): at each
    cell a new block starts with probability ``1 / mean_block`` (always at the first), else the
    previous index plus one, modulo n. One uniform per cell serves both choices: given a jump
    (``u < p``) ``u / p`` is again uniform, and it picks the block's start."""
    n = u.shape[1]
    p = 1.0 / mean_block
    jump = u < p
    jump[:, 0] = True
    scaled = np.where(jump, u / p, u)
    scaled[:, 0] = u[:, 0]
    starts = np.minimum((scaled * n).astype(np.int64), n - 1)
    cols = np.arange(n)
    last = np.maximum.accumulate(np.where(jump, cols, 0), axis=1)
    picked = np.take_along_axis(starts, last, axis=1)
    indices: npt.NDArray[np.int64] = (picked + cols - last) % n
    return indices


def bootstrap_summary(mean: float, draw_means: Array) -> Bootstrap:
    """The interval and t ratio of ``mean`` from the means of the bootstrap draws."""
    lo, hi = (float(q) for q in np.quantile(draw_means, INTERVAL, method="linear"))
    sd = float(draw_means.std(ddof=1)) if draw_means.size > 1 else 0.0
    return Bootstrap(mean, lo, hi, mean / sd if sd > _FLAT else None, int(draw_means.size))


def stationary_bootstrap(
    values: npt.ArrayLike, mean_block: float, draws: int, seed: int
) -> Bootstrap:
    """The stationary block bootstrap of the mean of ``values`` (finite entries): ``draws``
    resamples of mean block length ``mean_block``, a 90% interval from the quantiles of their
    means and ``t = mean / sd`` of those means. Seeded: same inputs, same output."""
    v = _finite(values)
    if v.size < 2:
        return Bootstrap()
    rng = np.random.default_rng(seed)
    means = np.empty(draws, dtype=np.float64)
    for lo in range(0, draws, CHUNK):
        rows = min(CHUNK, draws - lo)
        idx = stationary_indices(_uniforms(rng, rows, int(v.size)), mean_block)
        means[lo : lo + rows] = v[idx].mean(axis=1)
    return bootstrap_summary(float(v.mean()), means)


def psr(values: npt.ArrayLike) -> float | None:
    """The probabilistic Sharpe ratio: the deflated Sharpe ratio of one trial against zero."""
    return deflated_sharpe(values, 1, 0.0)
