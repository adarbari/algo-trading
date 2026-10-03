"""Property-based tests for the quant library: invariants for every valid input."""

import numpy as np
from hypothesis import example, given, settings
from hypothesis import strategies as st

from algotrade.quant import black_scholes as bs
from algotrade.quant import realized_vol as rv
from algotrade.quant.implied_vol import IVStatus, implied_vol
from algotrade.quant.rates import YieldCurve, par_to_continuous

spots = st.floats(1.0, 1_000.0)
moneyness = st.floats(0.3, 3.0)
years = st.floats(1 / 365, 5.0)
rates = st.floats(-0.02, 0.15)
yields = st.floats(0.0, 0.08)
vols = st.floats(0.01, 3.0)


@given(spots, moneyness, years, rates, yields, vols)
def test_put_call_parity(s: float, m: float, t: float, r: float, q: float, v: float) -> None:
    k = s * m
    call, put = bs.price(s, k, t, r, q, v, True), bs.price(s, k, t, r, q, v, False)
    forward = s * np.exp(-q * t) - k * np.exp(-r * t)
    assert abs(float(call - put - forward)) <= 1e-9 * (s + k)


@given(spots, moneyness, years, rates, yields, vols, st.booleans())
def test_prices_respect_bounds_and_rise_with_vol(
    s: float, m: float, t: float, r: float, q: float, v: float, call: bool
) -> None:
    k = s * m
    lower, upper = bs.bounds(s, k, t, r, q, call)
    p = float(bs.price(s, k, t, r, q, v, call))
    tol = 1e-9 * (s + k)
    assert float(lower) - tol <= p <= float(upper) + tol
    assert float(bs.price(s, k, t, r, q, v * 1.1, call)) >= p - tol
    g = bs.greeks(s, k, t, r, q, v, call)
    assert float(g.gamma) >= 0 and float(g.vega) >= 0
    assert (0 <= float(g.delta) <= 1) if call else (-1 <= float(g.delta) <= 0)


@settings(max_examples=200)
@given(spots, moneyness, years, rates, yields, vols, st.booleans())
# Far-OTM put whose model price cancels to a negative subnormal (-5e-324): AT_INTRINSIC.
@example(s=1.0, m=0.3, t=0.0996, r=0.09375, q=0.0, v=0.1, call=False)
def test_implied_vol_round_trips_the_price(
    s: float, m: float, t: float, r: float, q: float, v: float, call: bool
) -> None:
    k = s * m
    p = bs.price(s, k, t, r, q, v, call)
    result = implied_vol(p, s, k, t, r, q, call)
    status = IVStatus(int(result.status))
    if status is IVStatus.OK:
        assert abs(float(bs.price(s, k, t, r, q, result.iv, call) - p)) <= 1e-9 * k
    else:  # only when the price has numerically no time value left
        lower, _ = bs.bounds(s, k, t, r, q, call)
        assert status in (IVStatus.AT_INTRINSIC, IVStatus.VOL_BELOW_MIN)
        assert float(p - lower) < 1e-6 * k


@given(
    st.lists(st.floats(1.0, 500.0), min_size=12, max_size=40),
    st.floats(0.01, 100.0),
    st.integers(2, 10),
)
def test_realized_vol_is_scale_free_and_non_negative(
    closes: list[float], scale: float, window: int
) -> None:
    c = np.array(closes)
    base, scaled = rv.close_to_close(c, window), rv.close_to_close(c * scale, window)
    full = ~np.isnan(base)
    assert np.all(base[full] >= 0)
    np.testing.assert_allclose(scaled[full], base[full], rtol=1e-9, atol=1e-12)


@given(st.floats(-0.01, 0.2), st.integers(1, 11_000))
def test_continuous_rate_never_exceeds_the_par_yield(y: float, days: int) -> None:
    r = float(par_to_continuous(y, days))
    assert r <= y + 1e-15


@given(st.lists(st.floats(-0.01, 0.1), min_size=2, max_size=8), st.floats(0.0, 40.0))
def test_curve_rates_stay_within_the_quoted_range(quotes: list[float], t: float) -> None:
    days = np.arange(1, len(quotes) + 1) * 90
    curve = YieldCurve.from_days(days, quotes)
    assert min(quotes) - 1e-12 <= float(curve.rate(t)) <= max(quotes) + 1e-12
