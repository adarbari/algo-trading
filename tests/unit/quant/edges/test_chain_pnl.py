"""The chain P&L maths on hand-computed cases: the long P&L per premium (mid, executable) and per
underlying, intrinsic value, our own delta recovered from a model mid, the hedge's gain and its
NaN rules (a quote or delta that is missing is missing, never zero)."""

import numpy as np
import pytest

from algotrade.quant.black_scholes import greeks, price
from algotrade.quant.edges.chain_pnl import (
    hedged_pnl,
    intrinsic,
    leg_delta,
    leg_greeks,
    long_pnl,
    position_sum,
)


def test_long_pnl_per_premium_executable_and_per_underlying() -> None:
    mid, executable, per_underlying = long_pnl(5.0, 5.2, 7.0, 6.8, 100.0)
    assert mid == pytest.approx(0.4)  # (7 - 5) / 5
    assert executable == pytest.approx((6.8 - 5.2) / 5.2)  # bought at the ask, sold at the bid
    assert per_underlying == pytest.approx(0.02)  # 2 / 100


def test_a_missing_price_or_a_zero_premium_is_nan_never_zero() -> None:
    mid, executable, per_underlying = long_pnl(
        [np.nan, 0.0], [5.0, 0.0], [6.0, 1.0], [5.5, 1.0], 100.0
    )
    assert np.isnan(mid).all()  # no entry mid, or a zero premium: no return per premium
    assert executable[0] == pytest.approx(0.1) and np.isnan(executable[1])
    assert np.isnan(per_underlying[0])  # a missing entry price is not a zero


def test_intrinsic_value_at_expiry() -> None:
    assert intrinsic(105.0, 100.0, True) == 5.0 and intrinsic(105.0, 100.0, False) == 0.0
    assert intrinsic([95.0, 95.0], 100.0, [True, False]).tolist() == [0.0, 5.0]


@pytest.mark.parametrize("is_call", [True, False])
def test_our_delta_from_the_mid_recovers_the_models_delta(is_call: bool) -> None:
    t, sigma, spot, strike = 30 / 365, 0.35, 100.0, 105.0
    mid = float(price(spot, strike, t, 0.0, 0.0, sigma, is_call))
    ours = float(leg_delta(mid, spot, strike, t, is_call))
    assert ours == pytest.approx(
        float(greeks(spot, strike, t, 0.0, 0.0, sigma, is_call).delta), abs=1e-6
    )


def test_no_delta_where_the_mid_is_missing_or_prices_nothing() -> None:
    # missing, a zero mid on an at-the-money strike, a call priced above the spot
    out = leg_delta([np.nan, 0.0, 200.0], 100.0, 100.0, 30 / 365, True)
    assert np.isnan(out).all()


def test_the_delta_limit_when_no_vol_solves_far_from_the_money() -> None:
    t = 30 / 365
    far_otm_put = float(leg_delta(1e-12, 120.0, 100.0, t, False))  # a bid-0 quote's mid
    far_otm_call = float(leg_delta(1e-12, 80.0, 100.0, t, True))
    deep_itm_call = float(leg_delta(20.0, 120.0, 100.0, t, True))  # at its intrinsic value
    deep_itm_put = float(leg_delta(19.9, 80.0, 100.0, t, False))  # below its intrinsic value
    assert (far_otm_put, far_otm_call, deep_itm_call, deep_itm_put) == (0.0, 0.0, 1.0, -1.0)


def test_hedged_pnl_subtracts_the_gain_of_the_stock_hedge() -> None:
    spots = np.array([[100.0, 102.0, 99.0]])
    deltas = np.array([[0.1, -0.2]])  # the position's net delta at the first two closes
    gain = 0.1 * 2.0 + (-0.2) * (-3.0)
    out = hedged_pnl([4.0], [5.0], spots, deltas)
    assert out[0] == pytest.approx(5.0 - 4.0 - gain)


def test_a_missing_delta_or_spot_makes_the_hedged_pnl_nan() -> None:
    spots = np.array([[100.0, 102.0], [100.0, np.nan]])
    deltas = np.array([[np.nan], [0.5]])
    assert np.isnan(hedged_pnl([1.0, 1.0], [2.0, 2.0], spots, deltas)).all()


def test_leg_greeks_are_the_models_at_the_vol_the_mid_implies() -> None:
    spot, strike, t, vol = 100.0, 105.0, 45 / 365, 0.28
    mid = float(price(spot, strike, t, 0.0, 0.0, vol, True))
    g = leg_greeks(mid, spot, strike, t, True)
    want = greeks(spot, strike, t, 0.0, 0.0, vol, True)
    for ours, theirs in ((g.delta, want.delta), (g.gamma, want.gamma), (g.vega, want.vega),
                         (g.theta, want.theta)):  # fmt: skip
        assert float(ours) == pytest.approx(float(theirs), rel=1e-6)


def test_a_leg_with_no_solvable_vol_has_nan_gamma_vega_theta_never_zero() -> None:
    g = leg_greeks(np.nan, 100.0, 105.0, 45 / 365, True)
    assert np.isnan([g.delta, g.gamma, g.vega, g.theta]).all()


def test_position_sum_weights_each_leg_by_its_quantity_and_nan_poisons() -> None:
    values = np.array([[2.0, 3.0], [0.5, np.nan]])  # (legs, names)
    out = position_sum([-1.0, 1.0], values)
    assert out[0] == pytest.approx(-1.5) and np.isnan(out[1])  # a short and a long leg
