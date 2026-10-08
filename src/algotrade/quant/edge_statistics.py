"""Edge statistics: the numbers that judge a screener's picks against the field (ADR 0053).

Pure, deterministic functions over arrays of per-session or per-name values; an undefined
result (too few observations, a zero denominator) is ``None``, never NaN.

    lift                 hit rate over base rate
    standardised_effect  Hedges' g between picks and eligible non-picks
    decile_spread        mean of the best bucket minus mean of the worst, in rank order
    spread_summary       (mean, sd, t, n) of a series of per-session spreads
    sharpe               per-period mean over sample sd
    deflated_sharpe      Bailey and Lopez de Prado (2014): the probability the true Sharpe
                         beats what the best of ``n_trials`` noise strategies would show
    pbo_cscv             Bailey, Borwein, Lopez de Prado, Zhu (2017): the probability of
                         backtest overfitting by combinatorially symmetric cross-validation

The normal CDF is ``black_scholes.norm_cdf``, its owner.
"""

import itertools
import math

import numpy as np
import numpy.typing as npt

from algotrade.quant.black_scholes import inverse_normal_cdf, norm_cdf

type Array = npt.NDArray[np.float64]
type ArrayLike = npt.ArrayLike

_EULER_GAMMA = 0.5772156649015329


def _cdf(x: float) -> float:
    return float(norm_cdf(x))


def _finite(values: ArrayLike) -> Array:
    """The finite entries as a flat float array (a NaN is a missing value, not a zero)."""
    arr = np.asarray(values, dtype=np.float64).ravel()
    return arr[np.isfinite(arr)]


def lift(hit_rate: float | None, base_rate: float | None) -> float | None:
    """``hit_rate / base_rate``; None when either is missing or the base rate is not positive."""
    if hit_rate is None or base_rate is None or base_rate <= 0.0:
        return None
    return hit_rate / base_rate


def standardised_effect(a: ArrayLike, b: ArrayLike) -> float | None:
    """Hedges' g of ``a`` over ``b`` (pooled sd, small-sample correction); None under two
    observations on a side or a zero pooled sd."""
    x, y = _finite(a), _finite(b)
    nx, ny = x.size, y.size
    if nx < 2 or ny < 2:
        return None
    pooled = ((nx - 1) * x.var(ddof=1) + (ny - 1) * y.var(ddof=1)) / (nx + ny - 2)
    if pooled <= 0.0:
        return None
    d = (x.mean() - y.mean()) / math.sqrt(pooled)
    return float(d * (1.0 - 3.0 / (4.0 * (nx + ny) - 9.0)))


def decile_spread(values_in_rank_order: ArrayLike, buckets: int = 10) -> float | None:
    """Mean of the first bucket minus mean of the last, the values best-ranked first, split in
    ``buckets`` near-equal runs; None under ``buckets`` values (or fewer than two buckets)."""
    v = np.asarray(values_in_rank_order, dtype=np.float64).ravel()
    if buckets < 2 or v.size < buckets or not np.all(np.isfinite(v)):
        return None
    parts = np.array_split(v, buckets)
    return float(parts[0].mean() - parts[-1].mean())


def spread_summary(x: ArrayLike) -> tuple[float | None, float | None, float | None, int]:
    """``(mean, sd, t, n)`` of the finite values: sample sd, ``t = mean / (sd / sqrt n)``;
    each None where undefined."""
    v = _finite(x)
    n = int(v.size)
    if n == 0:
        return None, None, None, 0
    mean = float(v.mean())
    if n < 2:
        return mean, None, None, n
    sd = float(v.std(ddof=1))
    if sd <= 0.0:
        return mean, sd, None, n
    return mean, sd, mean / (sd / math.sqrt(n)), n


def sharpe(x: ArrayLike) -> float | None:
    """Per-period Sharpe ratio (mean over sample sd, no annualisation); None under two
    observations or a zero sd."""
    mean, sd, _, n = spread_summary(x)
    if mean is None or sd is None or sd <= 0.0 or n < 2:
        return None
    return mean / sd


def deflated_sharpe(x: ArrayLike, n_trials: int, sr_variance: float) -> float | None:
    """Deflated Sharpe ratio of the series ``x`` after ``n_trials`` tried strategies whose
    Sharpe ratios had variance ``sr_variance``: ``Phi((SR - SR0) sqrt(T-1) / sqrt(1 - skew SR +
    (kurt-1)/4 SR^2))`` with ``SR0 = sqrt(V) ((1-g) Phi^-1(1-1/N) + g Phi^-1(1-1/(N e)))``.
    One trial gives SR0 = 0 (the probabilistic Sharpe ratio). None when undefined."""
    v = _finite(x)
    sr = sharpe(v)
    if sr is None or v.size < 3 or n_trials < 1 or sr_variance < 0.0:
        return None
    if n_trials == 1:
        sr0 = 0.0
    else:
        n = float(n_trials)
        sr0 = math.sqrt(sr_variance) * (
            (1.0 - _EULER_GAMMA) * inverse_normal_cdf(1.0 - 1.0 / n)
            + _EULER_GAMMA * inverse_normal_cdf(1.0 - 1.0 / (n * math.e))
        )
    z = (v - v.mean()) / v.std(ddof=0)
    skew, kurt = float(np.mean(z**3)), float(np.mean(z**4))
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0.0:  # pragma: no cover (>= 0 by Cauchy-Schwarz; guards float drift)
        return None
    return _cdf((sr - sr0) * math.sqrt(v.size - 1.0) / math.sqrt(denom))


def pbo_cscv(m: ArrayLike, splits: int = 16) -> float | None:
    """Probability of backtest overfitting over a T x N matrix of per-session returns (columns
    are strategies): the rows are cut in ``splits`` blocks, every choice of half as in-sample
    (all C(S, S/2), no sampling) picks the best in-sample Sharpe (ties to the lowest index) and
    PBO is the share of choices where that pick ranks at or below the median out of sample.
    None when N < 2, T < S, or S is odd or below 2."""
    mat = np.asarray(m, dtype=np.float64)
    if mat.ndim != 2 or splits < 2 or splits % 2 or mat.shape[0] < splits or mat.shape[1] < 2:
        return None
    if not np.all(np.isfinite(mat)):
        return None
    size = mat.shape[0] // splits
    blocks = mat[: size * splits].reshape(splits, size, -1)
    s1, s2 = blocks.sum(axis=1), (blocks**2).sum(axis=1)
    n_cols = mat.shape[1]
    all_blocks = set(range(splits))
    below = 0
    total = 0
    for chosen in itertools.combinations(range(splits), splits // 2):
        rest = sorted(all_blocks - set(chosen))
        is_perf = _block_sharpe(s1[list(chosen)], s2[list(chosen)], size * len(chosen))
        oos_perf = _block_sharpe(s1[rest], s2[rest], size * len(rest))
        best = int(np.argmax(is_perf))
        less = float(np.sum(oos_perf < oos_perf[best]))
        equal = float(np.sum(oos_perf == oos_perf[best]))
        rank = less + (equal + 1.0) / 2.0  # 1..N ascending, ties averaged
        below += rank / (n_cols + 1.0) <= 0.5
        total += 1
    return below / total


def _block_sharpe(sums: Array, squares: Array, count: int) -> Array:
    """Per-column Sharpe from block sums; a flat column scores -inf (never the best)."""
    total, total_sq = sums.sum(axis=0), squares.sum(axis=0)
    mean = total / count
    var = (total_sq - count * mean * mean) / (count - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = mean / np.sqrt(var)
    return np.where(var > 1e-18, score, -np.inf)
