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


@pytest.mark.parametrize("delta", [0.05, 0.16, 0.30, 0.50])
@pytest.mark.parametrize("sigma,t", [(0.2, 21 / 252), (0.6, 31 / 252), (1.5, 15 / 252)])
def test_the_strike_from_delta_has_that_exact_delta(delta: float, sigma: float, t: float) -> None:
    put = float(bs.strike_from_delta(100.0, sigma, t, delta, "put"))
    call = float(bs.strike_from_delta(100.0, sigma, t, -delta, "call"))  # the sign is ignored
    assert float(bs.greeks(100.0, put, t, 0.0, 0.0, sigma, False).delta) == pytest.approx(-delta)
    assert float(bs.greeks(100.0, call, t, 0.0, 0.0, sigma, True).delta) == pytest.approx(delta)
    assert put <= 100.0 * np.exp(0.5 * sigma * sigma * t) * (1 + 1e-12) and call >= 100.0


def test_the_chance_of_expiring_out_of_the_money_matches_a_seeded_lognormal_simulation() -> None:
    price, sigma, t = 100.0, 0.35, 21 / 252
    rng = np.random.default_rng(7)
    end = price * np.exp(-0.5 * sigma**2 * t + sigma * np.sqrt(t) * rng.standard_normal(400_000))
    kp = float(bs.strike_from_delta(price, sigma, t, 0.30, "put"))
    kc = float(bs.strike_from_delta(price, sigma, t, 0.16, "call"))
    assert float(bs.prob_otm(price, kp, sigma, t, "put")) == pytest.approx(
        float((end > kp).mean()), abs=0.004
    )
    assert float(bs.prob_otm(price, kc, sigma, t, "call")) == pytest.approx(
        float((end < kc).mean()), abs=0.004
    )
    assert float(bs.prob_between(price, kp, kc, sigma, t)) == pytest.approx(
        float(((end > kp) & (end < kc)).mean()), abs=0.004
    )


def test_the_chance_of_expiring_out_of_the_money_is_monotone_in_the_strike() -> None:
    puts = bs.prob_otm(100.0, [80.0, 90.0, 100.0], 0.3, 0.1, "put")
    calls = bs.prob_otm(100.0, [100.0, 110.0, 120.0], 0.3, 0.1, "call")
    assert np.all(np.diff(puts) < 0) and np.all(np.diff(calls) > 0)
    far = bs.prob_between(100.0, 70.0, 130.0, 0.3, 0.1)
    near = bs.prob_between(100.0, 90.0, 110.0, 0.3, 0.1)
    assert near < far < 1.0


def test_a_strike_or_probability_is_nan_without_a_positive_vol_or_time_and_refuses_bad_input() -> (
    None
):
    assert np.isnan(bs.strike_from_delta(100.0, 0.0, 0.1, 0.3, "put"))
    assert np.isnan(bs.prob_otm(100.0, 90.0, 0.2, 0.0, "put"))
    with pytest.raises(ValueError):
        bs.strike_from_delta(100.0, 0.2, 0.1, 1.2, "put")
    with pytest.raises(ValueError):
        bs.prob_otm(100.0, 90.0, 0.2, 0.1, "straddle")
