"""Edge statistics: the numbers that judge a screener's picks against the field (ADR 0053).

Pure, deterministic functions over arrays of per-session or per-name values; an undefined
result (too few observations, a zero denominator) is ``None``, never NaN.

    lift                 hit rate over base rate
    standardised_effect  Hedges' g between picks and eligible non-picks
    moments              (n, mean, m2) of values: the running form a side is kept in
    merge_moments        Chan et al.: moments of parts -> moments of their union
    effect_vs_moments    Hedges' g of an array over a side given only as moments
    decile_spread        mean of the best bucket minus mean of the worst, in rank order
    spread_summary       (mean, sd, t, n) of a series of per-session spreads
    random_pick_sums     per draw, the sum of values and of hits over ``k`` names drawn
                         uniformly without replacement (the random-pick backtests)
    percentile_of        the share of a sample a value beats (ties half)
    sharpe               per-period mean over sample sd
    deflated_sharpe      Bailey and Lopez de Prado (2014): the probability the true Sharpe
                         beats what the best of ``n_trials`` noise strategies would show
    win_rate_pmf         the binomial distribution of the number of wins in n trades
    win_rate_band        the usual range of a live win rate: two quantiles of that distribution
    pbo_cscv             Bailey, Borwein, Lopez de Prado, Zhu (2017): the probability of
                         backtest overfitting by combinatorially symmetric cross-validation

The normal CDF is ``black_scholes.norm_cdf``, its owner.
"""

import itertools
import math
from collections.abc import Sequence

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


type Moments = tuple[int, float, float]  # n, mean, m2 (sum of squared deviations from the mean)


def moments(values: ArrayLike) -> Moments:
    """``(n, mean, m2)`` of the finite values, ``m2`` the sum of squared deviations about the
    mean (the numerically stable running form of the sum and sum of squares)."""
    v = _finite(values)
    if v.size == 0:
        return 0, 0.0, 0.0
    mean = float(v.mean())
    return int(v.size), mean, float(((v - mean) ** 2).sum())


def merge_moments(parts: Sequence[Moments]) -> Moments:
    """The moments of the union of disjoint samples (Chan, Golub, LeVeque 1979)."""
    n, mean, m2 = 0, 0.0, 0.0
    for pn, pmean, pm2 in parts:
        if pn == 0:
            continue
        total = n + pn
        delta = pmean - mean
        m2 += pm2 + delta * delta * n * pn / total
        mean += delta * pn / total
        n = total
    return n, mean, m2


def effect_vs_moments(a: ArrayLike, b: Moments) -> float | None:
    """Hedges' g of the array ``a`` over a side given as ``moments``: ``standardised_effect``
    without needing that side's values."""
    x = _finite(a)
    nx, (ny, mean_y, m2_y) = x.size, b
    if nx < 2 or ny < 2:
        return None
    pooled = ((nx - 1) * x.var(ddof=1) + m2_y) / (nx + ny - 2)
    if pooled <= 0.0:
        return None
    d = (x.mean() - mean_y) / math.sqrt(pooled)
    return float(d * (1.0 - 3.0 / (4.0 * (nx + ny) - 9.0)))


def standardised_effect(a: ArrayLike, b: ArrayLike) -> float | None:
    """Hedges' g of ``a`` over ``b`` (pooled sd, small-sample correction); None under two
    observations on a side or a zero pooled sd."""
    return effect_vs_moments(a, moments(b))


def decile_spread(values_in_rank_order: ArrayLike, buckets: int = 10) -> float | None:
    """Mean of the first bucket minus mean of the last, the values best-ranked first, split in
    ``buckets`` near-equal runs; None under ``buckets`` values (or fewer than two buckets)."""
    v = np.asarray(values_in_rank_order, dtype=np.float64).ravel()
    if buckets < 2 or v.size < buckets or not np.all(np.isfinite(v)):
        return None
    parts = np.array_split(v, buckets)
    return float(parts[0].mean() - parts[-1].mean())


def random_pick_sums(
    values: ArrayLike, hits: ArrayLike, k: int, draws: int, rng: np.random.Generator
) -> tuple[Array, Array] | None:
    """For each of ``draws`` draws, ``(sum of values, number of hits)`` over ``k`` of the names
    drawn uniformly without replacement (``values`` and ``hits`` aligned per name; every name
    must have a finite value). ``k`` above the names is every name. None with no names or no
    draws. Deterministic given ``rng`` and the order of the names."""
    v = np.asarray(values, dtype=np.float64).ravel()
    h = np.asarray(hits, dtype=np.float64).ravel()
    if v.size == 0 or draws < 1 or k < 1:
        return None
    k = min(k, v.size)
    keys = rng.random((draws, v.size))
    chosen = np.argpartition(keys, k - 1, axis=1)[:, :k] if k < v.size else None
    if chosen is None:
        return np.full(draws, v.sum()), np.full(draws, h.sum())
    return v[chosen].sum(axis=1), h[chosen].sum(axis=1)


def percentile_of(value: float | None, sample: ArrayLike) -> float | None:
    """The share of the finite ``sample`` that ``value`` beats (a tie counts half), in 0..1;
    None without a value or a sample."""
    v = _finite(sample)
    if value is None or not math.isfinite(value) or v.size == 0:
        return None
    return float(((v < value).sum() + 0.5 * (v == value).sum()) / v.size)


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


def win_rate_pmf(p: float, n: int) -> Array | None:
    """P(k wins) for k = 0..n when each of ``n`` independent trades wins with probability ``p``
    (the backtest's win rate): the array of length ``n + 1``. ``None`` when undefined (``n < 1``
    or ``p`` outside [0, 1])."""
    if n < 1 or not math.isfinite(p) or not 0.0 <= p <= 1.0:
        return None
    k = np.arange(n + 1, dtype=np.float64)
    if p in (0.0, 1.0):
        out = np.zeros(n + 1)
        out[n if p == 1.0 else 0] = 1.0
        return out
    log_choose = np.array(
        [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) for i in range(n + 1)]
    )
    return np.exp(log_choose + k * math.log(p) + (n - k) * math.log(1.0 - p))


def win_rate_band(
    p: float, n: int, low: float = 0.10, high: float = 0.90
) -> tuple[float, float] | None:
    """The usual range of a win rate over ``n`` closed trades if the backtest's win rate ``p``
    held: the ``low`` and ``high`` quantiles of the binomial wins, as rates (wins / ``n``). The
    live rate is "on track" inside it. ``None`` when undefined (``win_rate_pmf``)."""
    pmf = win_rate_pmf(p, n)
    if pmf is None or not 0.0 < low < high < 1.0:
        return None
    cdf = np.cumsum(pmf)
    lo = int(np.searchsorted(cdf, low - 1e-12))
    hi = int(np.searchsorted(cdf, high - 1e-12))
    return lo / n, hi / n
