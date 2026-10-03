"""The IV solver: price -> IV -> price round trips, and a status code for every failure."""

import itertools

import numpy as np
import pytest

from algotrade.quant import black_scholes as bs
from algotrade.quant.implied_vol import IVStatus, implied_vol, interpolate_total_variance

SPOT, R, Q = 100.0, 0.045, 0.015
GRID = np.array(
    list(
        itertools.product(
            [40.0, 70.0, 90.0, 99.0, 100.0, 101.0, 110.0, 140.0, 250.0],  # deep ITM .. deep OTM
            [1 / 365, 2 / 365, 7 / 365, 30 / 365, 0.5, 1.0, 3.0],
            [0.03, 0.15, 0.4, 1.0, 2.5, 4.5],
            [1.0, 0.0],  # call, put
        )
    )
)


def test_round_trip_across_moneyness_expiry_and_vol() -> None:
    k, t, sigma, call = GRID.T
    call = call.astype(bool)
    prices = bs.price(SPOT, k, t, R, Q, sigma, call)
    result = implied_vol(prices, SPOT, k, t, R, Q, call)
    ok = result.status == IVStatus.OK
    recovered = bs.price(SPOT, k, t, R, Q, np.where(ok, result.iv, 0.2), call)
    assert np.all(np.abs(recovered[ok] - prices[ok]) <= 1e-9 * k[ok])
    # The vol itself comes back within what the price tolerance allows (tol * strike / vega).
    vega = bs.greeks(SPOT, k, t, R, Q, sigma, call).vega
    sharp = ok & (vega > 1e-4 * k)
    error = np.abs(result.iv - sigma)[sharp]
    assert np.all(error <= 2e-10 * k[sharp] / vega[sharp] + 1e-12)
    assert np.median(error) < 1e-9
    # Failures only where the price has (numerically) no time value left.
    lower, _ = bs.bounds(SPOT, k, t, R, Q, call)
    failed = ~ok
    assert set(result.status[failed]) <= {IVStatus.AT_INTRINSIC, IVStatus.VOL_BELOW_MIN}
    assert np.all(prices[failed] - lower[failed] < 1e-6 * k[failed])
    assert ok.mean() > 0.7  # the rest: deep ITM / OTM at tiny t, numerically no time value
    assert np.isnan(result.iv[failed]).all()


def test_failure_codes() -> None:
    upper_call = SPOT * np.exp(-Q)
    intrinsic = SPOT * np.exp(-Q) - 90 * np.exp(-R)
    cases = [
        (np.nan, 100.0, 1.0, IVStatus.BAD_INPUT),
        (-1.0, 100.0, 1.0, IVStatus.BAD_INPUT),
        (5.0, 100.0, 0.0, IVStatus.BAD_INPUT),
        (5.0, -100.0, 1.0, IVStatus.BAD_INPUT),
        (intrinsic - 1.0, 90.0, 1.0, IVStatus.BELOW_INTRINSIC),
        (intrinsic, 90.0, 1.0, IVStatus.AT_INTRINSIC),
        (upper_call, 100.0, 1.0, IVStatus.ABOVE_MAX),
        (1e-3, 100.0 * np.exp(R - Q), 1.0, IVStatus.VOL_BELOW_MIN),  # ATM forward, ~1e-5 vol
        (float(bs.price(SPOT, 100.0, 1.0, R, Q, 8.0)), 100.0, 1.0, IVStatus.VOL_ABOVE_MAX),
    ]
    price, strike, t, expected = (np.array(c) for c in zip(*cases, strict=True))
    result = implied_vol(price, SPOT, strike, t, R, Q, True)
    assert result.reasons() == [IVStatus(int(e)).name for e in expected]
    assert np.isnan(result.iv).all()


def test_iteration_limit_reports_no_convergence() -> None:
    price = bs.price(SPOT, 120.0, 0.25, R, Q, 0.35)
    result = implied_vol(price, SPOT, 120.0, 0.25, R, Q, max_iter=1)
    assert result.reasons() == ["NO_CONVERGENCE"]
    assert float(implied_vol(price, SPOT, 120.0, 0.25, R, Q).iv) == pytest.approx(0.35)


def test_vectorised_shapes_and_puts() -> None:
    strikes = np.array([[80.0, 100.0], [120.0, 150.0]])
    prices = bs.price(SPOT, strikes, 0.5, R, Q, 0.3, False)
    result = implied_vol(prices, SPOT, strikes, 0.5, R, Q, False)
    assert result.iv.shape == (2, 2) and result.status.shape == (2, 2)
    np.testing.assert_allclose(result.iv, 0.3, rtol=1e-8)


def test_total_variance_interpolation() -> None:
    t1, t2 = np.array([0.1, 0.1]), np.array([0.3, 0.1])
    out = interpolate_total_variance(t1, [0.2, 0.25], t2, [0.3, 0.9], 0.2)
    w = 0.04 * 0.1 + (0.09 * 0.3 - 0.04 * 0.1) * 0.5
    assert out[0] == pytest.approx(np.sqrt(w / 0.2))
    assert out[1] == 0.25  # one expiry: flat
    at_ends = interpolate_total_variance(0.1, 0.2, 0.3, 0.3, [0.1, 0.3])
    assert at_ends == pytest.approx([0.2, 0.3])
