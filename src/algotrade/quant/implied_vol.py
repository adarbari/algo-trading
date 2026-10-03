"""Implied volatility: invert Black-Scholes-Merton for sigma, vectorised (ADR 0021).

``implied_vol(price, spot, strike, t, r, q, is_call)`` returns an ``IVResult``: the vol
(NaN where there is none) and a status code per element saying why (``IVStatus``):

    OK               solved within [min_vol, max_vol]
    BAD_INPUT        a non-finite input, spot / strike / t <= 0 or a price below ``-tol * strike``
    BELOW_INTRINSIC  price below the no-arbitrage lower bound (discounted forward intrinsic)
    AT_INTRINSIC     price equals that bound within ``tol``: no time value, so no vol
    ABOVE_MAX        price at or above the upper bound (spot e^{-qt} calls, strike e^{-rt} puts)
    VOL_BELOW_MIN    within bounds, but cheaper than the price at ``min_vol``
    VOL_ABOVE_MAX    within bounds, but dearer than the price at ``max_vol``
    NO_CONVERGENCE   the iteration limit was reached (should not happen: bisection backs it)

The solver is a safeguarded Newton iteration on price: the root is kept bracketed (price
is increasing in sigma), a Newton step is taken when it lands inside the bracket and the
bracket keeps halving, otherwise the step bisects. Bisection alone reaches ``xtol`` within
~50 steps, so ``max_iter`` is a safety net. Prices match within ``tol * strike``.

``interpolate_total_variance`` carries vols across expiries (linear in ``sigma^2 t``), the
term-structure convention for a constant-maturity vol such as IV30 (ADR 0021).
"""

from dataclasses import dataclass
from enum import IntEnum

import numpy as np
import numpy.typing as npt

from algotrade.quant.black_scholes import Array, ArrayLike, bounds, prepare, price_of, vega_of

MIN_VOL = 1e-4
MAX_VOL = 5.0


class IVStatus(IntEnum):
    OK = 0
    BAD_INPUT = 1
    BELOW_INTRINSIC = 2
    AT_INTRINSIC = 3
    ABOVE_MAX = 4
    VOL_BELOW_MIN = 5
    VOL_ABOVE_MAX = 6
    NO_CONVERGENCE = 7


@dataclass(frozen=True)
class IVResult:
    iv: Array  # NaN where status != OK
    status: npt.NDArray[np.int8]  # IVStatus values

    def reasons(self) -> list[str]:
        """The status names, flattened (for logs and stored rows)."""
        return [IVStatus(int(s)).name for s in self.status.ravel()]


def _model(
    sigma: Array, spot: Array, strike: Array, t: Array, r: Array, q: Array, call: Array
) -> tuple[Array, Array]:
    x = prepare(spot, strike, t, r, q, sigma, call)
    return price_of(x), vega_of(x)


def _initial_guess(spot: Array, strike: Array, t: Array, r: Array, q: Array) -> Array:
    """Manaster-Koehler: the vol where d1 is flattest in sigma (0.2 at the money)."""
    moneyness = np.abs(np.log(spot / strike) + (r - q) * t)
    guess = np.sqrt(2.0 * moneyness / t)
    return np.where(guess > 0, guess, 0.2)


def implied_vol(
    price: ArrayLike,
    spot: ArrayLike,
    strike: ArrayLike,
    t: ArrayLike,
    r: ArrayLike,
    q: ArrayLike,
    is_call: ArrayLike = True,
    *,
    min_vol: float = MIN_VOL,
    max_vol: float = MAX_VOL,
    tol: float = 1e-10,
    xtol: float = 1e-12,
    max_iter: int = 100,
) -> IVResult:
    """Implied vol per element (see the module doc for statuses and the method)."""
    p, s, k, tt, rr, qq, call = np.broadcast_arrays(
        *(np.asarray(a, dtype=np.float64) for a in (price, spot, strike, t, r, q)),
        np.asarray(is_call, dtype=bool),
    )
    status = np.full(p.shape, IVStatus.NO_CONVERGENCE, dtype=np.int8)
    iv = np.full(p.shape, np.nan)
    finite = np.isfinite(p) & np.isfinite(s) & np.isfinite(k) & np.isfinite(tt)
    finite &= np.isfinite(rr) & np.isfinite(qq)
    with np.errstate(invalid="ignore"):
        bad = ~finite | (s <= 0) | (k <= 0) | (tt <= 0)
        atol = tol * np.where(bad, 1.0, k)
        # A price is only negative beyond the tolerance: a model price of a far-OTM option
        # can cancel to -0.0 or a negative subnormal, which is "no time value", not bad input.
        bad |= p < -atol
    status[bad] = IVStatus.BAD_INPUT
    with np.errstate(all="ignore"):
        lower, upper = bounds(s, k, tt, rr, qq, call)
        p_lo, _ = _model(np.full(p.shape, min_vol), s, k, tt, rr, qq, call)
        p_hi, _ = _model(np.full(p.shape, max_vol), s, k, tt, rr, qq, call)
    rules = (
        (p < lower - atol, IVStatus.BELOW_INTRINSIC),
        (p <= lower + atol, IVStatus.AT_INTRINSIC),
        (p >= upper, IVStatus.ABOVE_MAX),
        (p < p_lo - atol, IVStatus.VOL_BELOW_MIN),
        (p > p_hi + atol, IVStatus.VOL_ABOVE_MAX),
    )
    todo = ~bad
    for failed, code in rules:
        hit = todo & failed
        status[hit] = code
        todo &= ~hit
    idx = np.flatnonzero(todo)
    solved, ok = _solve(
        tuple(a.ravel()[idx] for a in (p, s, k, tt, rr, qq, call, atol)),
        min_vol,
        max_vol,
        xtol,
        max_iter,
    )
    flat_iv, flat_status = iv.ravel(), status.ravel()
    flat_iv[idx[ok]] = solved[ok]
    flat_status[idx[ok]] = IVStatus.OK
    return IVResult(flat_iv.reshape(p.shape), flat_status.reshape(p.shape))


def _solve(
    arrays: tuple[Array, ...], min_vol: float, max_vol: float, xtol: float, max_iter: int
) -> tuple[Array, npt.NDArray[np.bool_]]:
    """Safeguarded Newton over 1-d arrays whose root is bracketed in [min_vol, max_vol]."""
    target, s, k, t, r, q, call, atol = arrays
    n = target.shape[0]
    out, ok = np.full(n, np.nan), np.zeros(n, dtype=bool)
    a, b = np.full(n, min_vol), np.full(n, max_vol)
    x = np.clip(_initial_guess(s, k, t, r, q), min_vol, max_vol)
    prev_width = np.full(n, np.inf)
    active = np.arange(n)
    for _ in range(max_iter):
        if active.size == 0:
            break
        sl = active
        price, vega = _model(x[sl], s[sl], k[sl], t[sl], r[sl], q[sl], call[sl])
        f = price - target[sl]
        done = (np.abs(f) <= atol[sl]) | (b[sl] - a[sl] <= xtol)
        out[sl[done]], ok[sl[done]] = x[sl[done]], True
        a[sl] = np.where(f < 0, x[sl], a[sl])
        b[sl] = np.where(f > 0, x[sl], b[sl])
        with np.errstate(divide="ignore", invalid="ignore"):
            newton = x[sl] - f / vega
        width = b[sl] - a[sl]
        inside = np.isfinite(newton) & (newton > a[sl]) & (newton < b[sl])
        use_newton = inside & (width <= 0.5 * prev_width[sl])
        prev_width[sl] = width
        x[sl] = np.where(use_newton, newton, 0.5 * (a[sl] + b[sl]))
        active = sl[~done]
    return out, ok


def interpolate_total_variance(
    t_near: ArrayLike, iv_near: ArrayLike, t_far: ArrayLike, iv_far: ArrayLike, t: ArrayLike
) -> Array:
    """The vol at time ``t`` (years) between two expiries, linear in total variance
    ``sigma^2 t`` (ADR 0021): ``w(t) = w1 + (w2 - w1) (t - t1) / (t2 - t1)`` and
    ``sigma = sqrt(w / t)``.

    Where ``t_near == t_far`` (one expiry) the near vol is returned unchanged (flat). Outside
    ``[t_near, t_far]`` the line extends; a negative total variance is NaN."""
    t1, v1, t2, v2, tt = np.broadcast_arrays(
        *(np.asarray(a, dtype=np.float64) for a in (t_near, iv_near, t_far, iv_far, t))
    )
    w1, w2 = v1 * v1 * t1, v2 * v2 * t2
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where(t2 > t1, w1 + (w2 - w1) * (tt - t1) / (t2 - t1), v1 * v1 * tt)
        out = np.sqrt(np.where(w >= 0, w, np.nan) / tt)
    return np.asarray(out, dtype=np.float64)
