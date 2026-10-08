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
Strikes and the risk-neutral chance of finishing out of the money (``strike_from_delta``,
``prob_otm``, ``prob_between``; r = q = 0) serve the edge harness's ``expires_otm`` outcome.
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


_ACKLAM_A = (
    -3.969683028665376e1,
    2.209460984245205e2,
    -2.759285104469687e2,
    1.383577518672690e2,
    -3.066479806614716e1,
    2.506628277459239,
)
_ACKLAM_B = (
    -5.447609879822406e1,
    1.615858368580409e2,
    -1.556989798598866e2,
    6.680131188771972e1,
    -1.328068155288572e1,
)
_ACKLAM_C = (
    -7.784894002430293e-3,
    -3.223964580411365e-1,
    -2.400758277161838,
    -2.549732539343734,
    4.374664141464968,
    2.938163982698783,
)
_ACKLAM_D = (7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416)
_ACKLAM_SPLIT = 0.02425


def inverse_normal_cdf(p: float) -> float:
    """Phi^-1(p) for 0 < p < 1: Acklam's rational approximation plus one Halley step."""
    a, b, c, d = _ACKLAM_A, _ACKLAM_B, _ACKLAM_C, _ACKLAM_D
    if p < _ACKLAM_SPLIT or p > 1.0 - _ACKLAM_SPLIT:
        q = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
        x = x if p < 0.5 else -x
    else:
        q = p - 0.5
        r = q * q
        x = (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    u = (float(norm_cdf(x)) - p) * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)


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


def _spread(sigma: ArrayLike, t_years: ArrayLike) -> tuple[Array, Array]:
    """``(sigma, sigma sqrt(t))`` as float arrays, NaN where either is not positive."""
    s = np.asarray(sigma, dtype=np.float64)
    years = np.asarray(t_years, dtype=np.float64)
    ok = (s > 0) & (years > 0)
    s = np.where(ok, s, np.nan)
    return s, s * np.sqrt(np.where(ok, years, np.nan))


def strike_from_delta(
    price: ArrayLike, sigma: ArrayLike, t_years: ArrayLike, delta: ArrayLike, right: str
) -> Array:
    """The strike whose Black-Scholes delta (r = q = 0) is ``delta`` in size: with
    ``d = |delta|`` and ``z = N^-1(1 - d)``, the put's is ``price exp(-z s sqrt(t) + s^2 t / 2)``
    and the call's ``price exp(+z s sqrt(t) + s^2 t / 2)`` (``right``: ``"put"`` | ``"call"``,
    ``0 < d < 1``). NaN where sigma or t is not positive."""
    if right not in ("put", "call"):
        raise ValueError(f"right must be 'put' or 'call', got {right!r}")
    d = np.abs(np.asarray(delta, dtype=np.float64))
    if np.any((d <= 0) | (d >= 1)):
        raise ValueError("|delta| must be in (0, 1)")
    z = np.vectorize(inverse_normal_cdf, otypes=[np.float64])(1.0 - d)
    _, sd = _spread(sigma, t_years)
    sign = -1.0 if right == "put" else 1.0
    return np.asarray(
        np.asarray(price, dtype=np.float64) * np.exp(sign * z * sd + 0.5 * sd * sd),
        dtype=np.float64,
    )


def _d2(price: ArrayLike, strike: ArrayLike, sigma: ArrayLike, t_years: ArrayLike) -> Array:
    _, sd = _spread(sigma, t_years)
    ratio = np.log(np.asarray(price, dtype=np.float64) / np.asarray(strike, dtype=np.float64))
    return np.asarray((ratio - 0.5 * sd * sd) / sd, dtype=np.float64)


def prob_otm(
    price: ArrayLike, strike: ArrayLike, sigma: ArrayLike, t_years: ArrayLike, right: str
) -> Array:
    """The risk-neutral chance (r = q = 0) the option expires out of the money: ``N(d2)`` for
    a put (``P(S_T > K)``), ``N(-d2)`` for a call (``P(S_T < K)``). NaN where sigma or t is
    not positive."""
    if right not in ("put", "call"):
        raise ValueError(f"right must be 'put' or 'call', got {right!r}")
    d2 = _d2(price, strike, sigma, t_years)
    return norm_cdf(d2 if right == "put" else -d2)


def prob_between(
    price: ArrayLike,
    put_strike: ArrayLike,
    call_strike: ArrayLike,
    sigma: ArrayLike,
    t_years: ArrayLike,
) -> Array:
    """``P(put_strike < S_T < call_strike)`` risk-neutral (r = q = 0): the chance both legs of a
    short strangle expire out of the money (``put_strike < call_strike``)."""
    put = prob_otm(price, put_strike, sigma, t_years, "put")
    call = prob_otm(price, call_strike, sigma, t_years, "call")
    return np.maximum(put + call - 1.0, 0.0)
