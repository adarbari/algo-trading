"""Rate conventions: tenor days, par -> continuous, curve interpolation."""

import math

import numpy as np
import pytest

from algotrade.quant.rates import YieldCurve, par_to_continuous, tenor_days


@pytest.mark.parametrize(
    ("label", "days"),
    [
        *[("1M", 30), ("1.5M", 46), ("2m", 61), ("3M", 91), ("4M", 122), ("6M", 183)],
        *[("1Y", 365), ("2Y", 730), ("10Y", 3652), ("30Y", 10958)],
    ],
)
def test_tenor_days(label: str, days: int) -> None:
    assert tenor_days(label) == days


def test_bad_tenor() -> None:
    with pytest.raises(ValueError, match="tenor"):
        tenor_days("3 weeks")


def test_bills_are_simple_interest_and_coupons_semiannual() -> None:
    bill = par_to_continuous(0.05, 91)
    tau = 91 / 365
    assert float(bill) == pytest.approx(math.log(1 + 0.05 * tau) / tau)
    assert float(par_to_continuous(0.05, 3652)) == pytest.approx(2 * math.log(1.025))
    # The two conventions meet at half a year, so the curve has no step there.
    edges = par_to_continuous([0.05, 0.05], [182.5, 183])
    assert edges[0] == pytest.approx(edges[1], abs=1e-5)
    assert float(par_to_continuous(0.05, 365)) < 0.05  # continuous < compounded
    with pytest.raises(ValueError, match="positive"):
        par_to_continuous(0.05, 0)


def test_curve_interpolates_linearly_and_flat_outside() -> None:
    curve = YieldCurve.from_days([365, 30, 91, 182], [0.04, 0.05, np.nan, 0.045])
    assert curve.years.tolist() == pytest.approx([30 / 365, 182 / 365, 1.0])
    mid = (30 / 365 + 182 / 365) / 2
    assert float(curve.rate(mid)) == pytest.approx(0.0475)
    np.testing.assert_allclose(curve.rate([0.0, 5.0]), [0.05, 0.04])
    assert float(curve.discount(1.0)) == pytest.approx(math.exp(-0.04))


def test_curve_validation() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        YieldCurve(np.array([]), np.array([]))
    with pytest.raises(ValueError, match="increasing"):
        YieldCurve(np.array([1.0, 1.0]), np.array([0.01, 0.02]))
