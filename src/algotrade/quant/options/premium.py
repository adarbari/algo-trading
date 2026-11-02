"""The figures of a sold option from its mid premium, written once (ownership
``option-premium-figures``): what the option grid and the ``short_premium@v1`` summary show.

All inputs broadcast (scalars or numpy arrays); ``right`` is ``"put"`` or ``"call"``:

- **Return on collateral**: the premium over what backs the position: a put's mid / strike
  (cash secured), a call's mid / spot (the shares held).
- **Yield a year**: the return on collateral scaled to 365 days, simple, not compounded:
  ``roc * 365 / dte`` (calendar days, ``rates.DAYS_PER_YEAR``). NaN where ``dte <= 0``, never
  infinity.
- **Breakeven**: the price the underlying can fall to before the position loses: a put's
  strike - mid, a call's spot - mid (a covered call).
- **Chance below the strike** (``p_below``): the risk-neutral chance the underlying ends
  below the strike, from ``black_scholes.prob_otm`` with r = q = 0 (ADR 0053's convention):
  a put's ``1 - prob_otm(put)``, a call's ``prob_otm(call)``. It is the one quantity for both
  rights; the grid's IV is inverted with the session's rate and dividend yield, so the two
  differ by about 0.01 at 30 days (documented in docs/options/backend-concepts-2.md).

- **Chance of assignment** (``assignment_chance``): the risk-neutral chance at least one sold leg
  ends in the money at the expiry, from ``p_below`` per leg: below the highest sold put's strike
  or above the lowest sold call's, the two disjoint while the put's strike is under the call's
  (their sum), and certain when they overlap (a straddle: one of them always ends in the money).

NaN propagates: a missing mid, a non-positive collateral, strike or vol gives NaN.
"""

import numpy as np

from algotrade.quant.black_scholes import Array, ArrayLike, prob_otm
from algotrade.quant.rates import DAYS_PER_YEAR


def _check(right: str) -> bool:
    """True for a call; ``ValueError`` for anything but ``"put"`` or ``"call"``."""
    if right not in ("put", "call"):
        raise ValueError(f"right must be 'put' or 'call', got {right!r}")
    return right == "call"


def return_on_collateral(mid: ArrayLike, strike: ArrayLike, spot: ArrayLike, right: str) -> Array:
    """Premium over collateral: ``mid / strike`` for a put, ``mid / spot`` for a call; NaN
    where the collateral is not positive."""
    collateral = np.asarray(spot if _check(right) else strike, dtype=np.float64)
    m = np.asarray(mid, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(np.where(collateral > 0, m / collateral, np.nan), dtype=np.float64)


def yield_annualised(roc: ArrayLike, dte: ArrayLike) -> Array:
    """``roc * 365 / dte`` (simple); NaN where ``dte <= 0``."""
    r = np.asarray(roc, dtype=np.float64)
    days = np.asarray(dte, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(np.where(days > 0, r * DAYS_PER_YEAR / days, np.nan), dtype=np.float64)


def breakeven(mid: ArrayLike, strike: ArrayLike, spot: ArrayLike, right: str) -> Array:
    """``strike - mid`` for a put, ``spot - mid`` for a call."""
    base = np.asarray(spot if _check(right) else strike, dtype=np.float64)
    return np.asarray(base - np.asarray(mid, dtype=np.float64), dtype=np.float64)


def p_below(
    spot: ArrayLike, strike: ArrayLike, sigma: ArrayLike, t_years: ArrayLike, right: str
) -> Array:
    """The risk-neutral chance (r = q = 0) the underlying ends below ``strike``; NaN where
    ``sigma`` or ``t_years`` is not positive. In [0, 1]."""
    if _check(right):
        return prob_otm(spot, strike, sigma, t_years, "call")
    return np.asarray(1.0 - prob_otm(spot, strike, sigma, t_years, "put"), dtype=np.float64)


def assignment_chance(
    spot: float,
    puts: list[tuple[float, float]],
    calls: list[tuple[float, float]],
    t_years: float,
) -> float:
    """The chance at least one sold leg ends in the money at the expiry; ``puts`` and ``calls``:
    the sold legs' ``(strike, sigma)``. NaN where a leg's sigma or ``t_years`` is not positive
    (``p_below``'s NaN), 0 with no sold leg. In [0, 1]."""
    put = max(puts, default=None, key=lambda leg: leg[0])
    call = min(calls, default=None, key=lambda leg: leg[0])
    if put is not None and call is not None and put[0] >= call[0]:
        legs = [put, call]
        known = all(sigma > 0 for _, sigma in legs) and t_years > 0
        return 1.0 if known else float("nan")
    below = 0.0 if put is None else float(p_below(spot, put[0], put[1], t_years, "put"))
    above = 0.0 if call is None else 1.0 - float(p_below(spot, call[0], call[1], t_years, "call"))
    return float(min(below + above, 1.0))
