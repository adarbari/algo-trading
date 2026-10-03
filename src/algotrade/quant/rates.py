"""Risk-free rates for option pricing: Treasury par yields -> continuous rates, and a curve.

Conventions (ADR 0021):

- **Tenors** are labels like ``1M``, ``1.5M``, ``6M``, ``1Y``, ``30Y``; ``tenor_days`` maps
  them to calendar days as ``round(months * 365.25 / 12)`` (1M = 30, 3M = 91, 6M = 183,
  1Y = 365, 10Y = 3652). Time in years is ``days / 365`` everywhere (``DAYS_PER_YEAR``).
- **Par -> continuous.** Treasury publishes constant-maturity par yields on a
  bond-equivalent basis. Up to half a year (bills) that is simple interest on actual/365,
  so ``r = ln(1 + y tau) / tau``; beyond, it is semi-annual compounding, so
  ``r = 2 ln(1 + y / 2)``. Par yields of coupon tenors (2Y+) are used as zero rates without
  bootstrapping; the error is a few basis points, negligible for option prices.
- **Interpolation** is linear in the continuous rate against time in years, flat beyond the
  first and last tenor. Rates are decimals (0.0425 = 4.25%) everywhere.
"""

import re
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type Array = npt.NDArray[np.float64]

DAYS_PER_YEAR = 365.0
_TENOR = re.compile(r"^(\d+(?:\.\d+)?)([MY])$")


def tenor_days(label: str) -> int:
    """Calendar days of a tenor label (``"3M"`` -> 91, ``"2Y"`` -> 730)."""
    match = _TENOR.match(label.strip().upper())
    if match is None:
        raise ValueError(f"tenor {label!r}: expected <number>M or <number>Y, e.g. 3M, 10Y")
    months = float(match.group(1)) * (12 if match.group(2) == "Y" else 1)
    return round(months * 365.25 / 12)


def par_to_continuous(rate_par: npt.ArrayLike, days: npt.ArrayLike) -> Array:
    """Continuously compounded rate from a bond-equivalent par yield (decimals)."""
    y = np.asarray(rate_par, dtype=np.float64)
    tau = np.asarray(days, dtype=np.float64) / DAYS_PER_YEAR
    if np.any(tau <= 0):
        raise ValueError("tenor days must be positive")
    with np.errstate(invalid="ignore", divide="ignore"):
        simple = np.log1p(y * tau) / tau
        semiannual = 2.0 * np.log1p(y / 2.0)
    return np.asarray(np.where(tau <= 0.5, simple, semiannual), dtype=np.float64)


@dataclass(frozen=True)
class YieldCurve:
    """Continuous rates by time to maturity in years (ascending, at least one point)."""

    years: Array
    rates: Array

    def __post_init__(self) -> None:
        if self.years.ndim != 1 or self.years.shape != self.rates.shape or not len(self.years):
            raise ValueError("a curve needs equal-length, non-empty 1-d years and rates")
        if np.any(np.diff(self.years) <= 0):
            raise ValueError("curve maturities must be strictly increasing")

    @classmethod
    def from_days(cls, days: npt.ArrayLike, rates: npt.ArrayLike) -> "YieldCurve":
        """A curve from tenor days and continuous rates, in any order (NaN rates dropped)."""
        d = np.asarray(days, dtype=np.float64)
        r = np.asarray(rates, dtype=np.float64)
        keep = np.isfinite(r) & np.isfinite(d)
        order = np.argsort(d[keep])
        return cls(d[keep][order] / DAYS_PER_YEAR, r[keep][order])

    def rate(self, t: npt.ArrayLike) -> Array:
        """The continuous rate for time to expiry ``t`` (years): linear, flat outside."""
        return np.asarray(np.interp(np.asarray(t, dtype=np.float64), self.years, self.rates))

    def discount(self, t: npt.ArrayLike) -> Array:
        """Discount factor ``exp(-r(t) t)``."""
        tt = np.asarray(t, dtype=np.float64)
        return np.asarray(np.exp(-self.rate(tt) * tt))
