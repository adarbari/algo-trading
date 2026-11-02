"""The payoff figures of a short option held to expiry, written once (ownership
``option-payoff-figures``): what the option calculators (``services/preview/options/``) show
when a trader rolls a sold option or sells calls on shares held. Per share, at the mid.

All inputs broadcast (scalars or numpy arrays); ``right`` is ``"put"`` or ``"call"``:

- **Short breakeven**: the underlying's price at expiry where a short option that collected
  ``credit`` in all (every premium taken in, less what was paid to buy back) neither gains nor
  loses: a put's strike - credit, a call's strike + credit.
- **Credit per extra day**: a roll's net credit over the calendar days it adds; NaN where it
  adds none.
- **Called-away return**: the return on shares bought at ``basis`` when a covered call at
  ``strike`` is assigned, keeping its ``premium``: ``(strike + premium - basis) / basis``; NaN
  where the basis is not positive.
- **Extrinsic value**: the part of a mid that is not intrinsic (``mid - max(0, spot - strike)``
  for a call, ``mid - max(0, strike - spot)`` for a put). An in-the-money call whose extrinsic
  value is below the coming dividend is the one an owner exercises early to collect it.

NaN propagates.
"""

import numpy as np

from algotrade.quant.black_scholes import Array, ArrayLike


def _is_call(right: str) -> bool:
    """True for a call; ``ValueError`` for anything but ``"put"`` or ``"call"``."""
    if right not in ("put", "call"):
        raise ValueError(f"right must be 'put' or 'call', got {right!r}")
    return right == "call"


def short_breakeven(strike: ArrayLike, credit: ArrayLike, right: str) -> Array:
    """``strike - credit`` for a put, ``strike + credit`` for a call."""
    sign = 1.0 if _is_call(right) else -1.0
    k = np.asarray(strike, dtype=np.float64)
    return np.asarray(k + sign * np.asarray(credit, dtype=np.float64), dtype=np.float64)


def credit_per_day(credit: ArrayLike, extra_days: ArrayLike) -> Array:
    """``credit / extra_days``; NaN where ``extra_days <= 0``."""
    c = np.asarray(credit, dtype=np.float64)
    days = np.asarray(extra_days, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(np.where(days > 0, c / days, np.nan), dtype=np.float64)


def called_away_return(strike: ArrayLike, premium: ArrayLike, basis: ArrayLike) -> Array:
    """``(strike + premium - basis) / basis``; NaN where ``basis`` is not positive."""
    b = np.asarray(basis, dtype=np.float64)
    gain = np.asarray(strike, dtype=np.float64) + np.asarray(premium, dtype=np.float64) - b
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.asarray(np.where(b > 0, gain / b, np.nan), dtype=np.float64)


def extrinsic(mid: ArrayLike, spot: ArrayLike, strike: ArrayLike, right: str) -> Array:
    """The mid less the option's intrinsic value at ``spot``."""
    s = np.asarray(spot, dtype=np.float64)
    k = np.asarray(strike, dtype=np.float64)
    intrinsic = np.maximum(s - k, 0.0) if _is_call(right) else np.maximum(k - s, 0.0)
    return np.asarray(np.asarray(mid, dtype=np.float64) - intrinsic, dtype=np.float64)
