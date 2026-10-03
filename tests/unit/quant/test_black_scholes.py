"""Black-Scholes-Merton prices and Greeks: textbook values, parity, finite differences."""

import itertools

import numpy as np
import pytest

from algotrade.quant import black_scholes as bs


def test_hull_textbook_prices() -> None:
    # Hull, Options Futures and Other Derivatives, Example 15.6: S=42 K=40 r=10% vol=20% T=0.5
    assert float(bs.price(42, 40, 0.5, 0.10, 0.0, 0.20, True)) == pytest.approx(4.7594, abs=1e-4)
    assert float(bs.price(42, 40, 0.5, 0.10, 0.0, 0.20, False)) == pytest.approx(0.8086, abs=1e-4)
    # Hull Example 17.1 (index with dividend yield): S=930 K=900 r=8% q=3% vol=20% T=2/12
    assert float(bs.price(930, 900, 2 / 12, 0.08, 0.03, 0.20)) == pytest.approx(51.83, abs=0.01)


def test_hull_textbook_greeks() -> None:
    # Hull, the running example of the Greeks chapter: S=49 K=50 r=5% vol=20% T=20 weeks
    g = bs.greeks(49, 50, 0.3846, 0.05, 0.0, 0.20, True)
    assert float(g.delta) == pytest.approx(0.522, abs=1e-3)
    assert float(g.gamma) == pytest.approx(0.066, abs=1e-3)
    assert float(g.vega) == pytest.approx(12.1, abs=0.05)  # per 1.00 of vol
    assert float(g.theta) == pytest.approx(-4.31, abs=0.01)  # per year
    assert float(g.rho) == pytest.approx(8.91, abs=0.01)


GRID = list(
    itertools.product(
        [60.0, 95.0, 100.0, 105.0, 160.0],  # strike, spot 100
        [1 / 365, 0.1, 1.0, 3.0],  # years
        [0.08, 0.3, 1.2],  # vol
        [(-0.01, 0.0), (0.05, 0.02)],  # (r, q)
    )
)


def _grid() -> tuple[np.ndarray, ...]:
    k, t, v, rq = zip(*GRID, strict=True)
    r, q = zip(*rq, strict=True)
    return tuple(np.array(a, dtype=float) for a in (k, t, v, r, q))


def test_put_call_parity_across_the_grid() -> None:
    k, t, v, r, q = _grid()
    call, put = bs.price(100.0, k, t, r, q, v, True), bs.price(100.0, k, t, r, q, v, False)
    forward = 100.0 * np.exp(-q * t) - k * np.exp(-r * t)
    np.testing.assert_allclose(call - put, forward, atol=1e-10)


@pytest.mark.parametrize("is_call", [True, False])
def test_greeks_match_finite_differences(is_call: bool) -> None:
    k, t, v, r, q = _grid()
    s = np.full_like(k, 100.0)
    g = bs.greeks(s, k, t, r, q, v, is_call)

    def p(**bump: np.ndarray) -> np.ndarray:
        args = {"spot": s, "strike": k, "t": t, "r": r, "q": q, "sigma": v} | bump
        return bs.price(**args, is_call=is_call)

    hs, hv, hr, ht = 1e-3, 1e-5, 1e-6, 1e-6
    np.testing.assert_allclose(g.delta, (p(spot=s + hs) - p(spot=s - hs)) / (2 * hs), atol=1e-6)
    gamma = (p(spot=s + hs) - 2 * g.price + p(spot=s - hs)) / hs**2
    np.testing.assert_allclose(g.gamma, gamma, atol=2e-3, rtol=1e-3)
    np.testing.assert_allclose(g.vega, (p(sigma=v + hv) - p(sigma=v - hv)) / (2 * hv), atol=1e-5)
    np.testing.assert_allclose(g.rho, (p(r=r + hr) - p(r=r - hr)) / (2 * hr), atol=1e-4)
    theta = -(p(t=t + ht) - p(t=t - ht)) / (2 * ht)  # -dV/dt: value lost as time passes
    np.testing.assert_allclose(g.theta, theta, atol=1e-3, rtol=1e-5)


def test_no_time_value_is_discounted_forward_intrinsic() -> None:
    expired = bs.greeks([110, 90, 100], 100, 0.0, 0.05, 0.0, 0.3, True)
    np.testing.assert_allclose(expired.price, [10, 0, 0])
    np.testing.assert_allclose(expired.delta, [1, 0, 0.5])
    assert not expired.gamma.any() and not expired.vega.any()
    zero_vol = bs.price(100, 100, 1.0, 0.05, 0.0, 0.0, [True, False])
    np.testing.assert_allclose(zero_vol, [100 - 100 * np.exp(-0.05), 0.0])
    assert float(bs.price(100, 100, -1.0, 0.05, 0.0, 0.2)) == 0.0  # negative t is expiry


def test_shapes_broadcast_and_scalars_are_zero_d() -> None:
    out = bs.price(100.0, np.array([[90.0], [110.0]]), np.array([0.5, 1.0]), 0.03, 0.0, 0.25)
    assert out.shape == (2, 2)
    assert bs.price(100, 100, 1, 0, 0, 0.2).shape == ()


def test_normal_cdf_is_accurate_in_the_tails() -> None:
    assert float(bs.norm_cdf(-10.0)) == pytest.approx(7.619853024160527e-24, rel=1e-12)
    assert float(bs.norm_cdf(0.0)) == 0.5
    np.testing.assert_allclose(bs.norm_cdf([-np.inf, np.inf]), [0.0, 1.0])
    assert float(bs.norm_pdf(0.0)) == pytest.approx(0.3989422804014327)


def test_no_arbitrage_bounds() -> None:
    lower, upper = bs.bounds(100, [90, 110], 1.0, 0.05, 0.02, [True, False])
    np.testing.assert_allclose(
        lower, [100 * np.exp(-0.02) - 90 * np.exp(-0.05), 110 * np.exp(-0.05) - 100 * np.exp(-0.02)]
    )
    assert float(bs.bounds(100, 120, 1.0, 0.05, 0.02)[0][()]) == 0.0  # OTM call
    np.testing.assert_allclose(upper, [100 * np.exp(-0.02), 110 * np.exp(-0.05)])
