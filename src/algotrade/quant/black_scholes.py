"""European option price and Greeks under Black-Scholes-Merton (ADR 0021).

Inputs broadcast against each other (scalars or numpy arrays):

    spot, strike   > 0
    t              time to expiry in YEARS (calendar days / 365, ADR 0021); t <= 0 is expiry
    r, q           continuously compounded risk-free rate and dividend yield (decimals)
    sigma          annualised volatility (decimal); sigma <= 0 prices the discounted forward
    is_call        True for calls, False for puts

Outputs are float arrays (0-d for scalar inputs). Greeks are the raw derivatives: ``vega``
per 1.00 of vol (divide by 100 for "per vol point"), ``theta`` per YEAR of calendar time
passing (divide by 365 for "per day"; it is ``-dV/dt``), ``rho`` per 1.00 of rate.
At expiry (or zero vol) the price is the discounted intrinsic value of the forward, delta is
a step, and gamma and vega are 0.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type Array = npt.NDArray[np.float64]
type ArrayLike = npt.ArrayLike

_SQRT2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)
_ERFC = np.frompyfunc(math.erfc, 1, 1)  # exact in the tails, unlike 1 - erf


def norm_cdf(x: ArrayLike) -> Array:
    """Standard normal CDF, accurate in both tails (``0.5 * erfc(-x / sqrt 2)``)."""
    values = np.asarray(x, dtype=np.float64)
    return np.asarray(0.5 * _ERFC(-values / _SQRT2), dtype=np.float64)


def norm_pdf(x: ArrayLike) -> Array:
    """Standard normal density."""
    values = np.asarray(x, dtype=np.float64)
    return np.asarray(_INV_SQRT_2PI * np.exp(-0.5 * values * values), dtype=np.float64)


@dataclass(frozen=True)
class Inputs:
    """Broadcast inputs and the quantities every formula shares."""

    spot: Array
    strike: Array
    t: Array  # clipped at 0
    r: Array
    q: Array
    sigma: Array
    is_call: npt.NDArray[np.bool_]
    fwd_s: Array  # spot * exp(-q t)
    pv_k: Array  # strike * exp(-r t)
    sd: Array  # sigma * sqrt(t), 0 when degenerate
    d1: Array
    d2: Array

    @property
    def live(self) -> npt.NDArray[np.bool_]:
        """Time value remains (t > 0 and sigma > 0)."""
        return np.asarray(self.sd > 0)


def prepare(
    spot: ArrayLike,
    strike: ArrayLike,
    t: ArrayLike,
    r: ArrayLike,
    q: ArrayLike,
    sigma: ArrayLike,
    is_call: ArrayLike = True,
) -> Inputs:
    """Broadcast the inputs and compute d1, d2 (``+-inf`` / 0 when there is no time value)."""
    s, k, tt, rr, qq, v, call = np.broadcast_arrays(
        *(np.asarray(a, dtype=np.float64) for a in (spot, strike, t, r, q, sigma)),
        np.asarray(is_call, dtype=bool),
    )
    tt = np.maximum(tt, 0.0)
    fwd_s = s * np.exp(-qq * tt)
    pv_k = k * np.exp(-rr * tt)
    sd = np.where(v > 0, v, 0.0) * np.sqrt(tt)
    live = sd > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        d1_live = (np.log(fwd_s / pv_k) + 0.5 * sd * sd) / sd
    # Without time value d1 is +inf / -inf / 0 by the moneyness of the forward.
    step = np.where(fwd_s > pv_k, np.inf, np.where(fwd_s < pv_k, -np.inf, 0.0))
    d1 = np.where(live, d1_live, step)
    d2 = np.where(live, d1 - sd, d1)
    return Inputs(s, k, tt, rr, qq, v, call, fwd_s, pv_k, sd, d1, d2)


def price_of(x: Inputs) -> Array:
    """The price for prepared inputs (``prepare``)."""
    call = x.fwd_s * norm_cdf(x.d1) - x.pv_k * norm_cdf(x.d2)
    put = x.pv_k * norm_cdf(-x.d2) - x.fwd_s * norm_cdf(-x.d1)
    return np.asarray(np.where(x.is_call, call, put), dtype=np.float64)


def price(
    spot: ArrayLike,
    strike: ArrayLike,
    t: ArrayLike,
    r: ArrayLike,
    q: ArrayLike,
    sigma: ArrayLike,
    is_call: ArrayLike = True,
) -> Array:
    """Black-Scholes-Merton price of European calls / puts."""
    return price_of(prepare(spot, strike, t, r, q, sigma, is_call))


def vega_of(x: Inputs) -> Array:
    """dV/dsigma (per 1.00 of vol); 0 without time value."""
    return np.asarray(np.where(x.live, x.fwd_s * norm_pdf(x.d1) * np.sqrt(x.t), 0.0))


@dataclass(frozen=True)
class Greeks:
    """Price and first-order sensitivities (gamma: second order in spot). Units: module doc."""

    price: Array
    delta: Array
    gamma: Array
    vega: Array
    theta: Array
    rho: Array


def greeks(
    spot: ArrayLike,
    strike: ArrayLike,
    t: ArrayLike,
    r: ArrayLike,
    q: ArrayLike,
    sigma: ArrayLike,
    is_call: ArrayLike = True,
) -> Greeks:
    """Price, delta, gamma, vega, theta (per year, ``-dV/dt``) and rho, vectorised."""
    x = prepare(spot, strike, t, r, q, sigma, is_call)
    n1, n2 = norm_cdf(x.d1), norm_cdf(x.d2)
    m1, m2 = norm_cdf(-x.d1), norm_cdf(-x.d2)
    pdf = norm_pdf(x.d1)
    df_q = np.exp(-x.q * x.t)
    with np.errstate(divide="ignore", invalid="ignore"):
        gamma = np.where(x.live, df_q * pdf / (x.spot * x.sd), 0.0)
        decay = np.where(x.live, -x.fwd_s * pdf * x.sigma / (2.0 * np.sqrt(x.t)), 0.0)
    theta_call = decay - x.r * x.pv_k * n2 + x.q * x.fwd_s * n1
    theta_put = decay + x.r * x.pv_k * m2 - x.q * x.fwd_s * m1
    call = x.is_call
    return Greeks(
        price=price_of(x),
        delta=np.asarray(np.where(call, df_q * n1, -df_q * m1)),
        gamma=np.asarray(gamma),
        vega=vega_of(x),
        theta=np.asarray(np.where(call, theta_call, theta_put)),
        rho=np.asarray(np.where(call, x.t * x.pv_k * n2, -x.t * x.pv_k * m2)),
    )


def bounds(
    spot: ArrayLike,
    strike: ArrayLike,
    t: ArrayLike,
    r: ArrayLike,
    q: ArrayLike,
    is_call: ArrayLike = True,
) -> tuple[Array, Array]:
    """No-arbitrage price bounds ``(lower, upper)``: the discounted intrinsic value of the
    forward, and ``spot e^{-qt}`` (calls) or ``strike e^{-rt}`` (puts)."""
    x = prepare(spot, strike, t, r, q, 0.0, is_call)
    lower = np.where(x.is_call, x.fwd_s - x.pv_k, x.pv_k - x.fwd_s)
    upper = np.where(x.is_call, x.fwd_s, x.pv_k)
    return np.asarray(np.maximum(lower, 0.0)), np.asarray(upper)
