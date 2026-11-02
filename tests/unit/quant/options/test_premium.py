"""The sold option's figures: exact identities, NaN edges, the convention of ``p_below``."""

import math

import numpy as np
import pytest

from algotrade.quant.black_scholes import prob_otm
from algotrade.quant.options import premium
from algotrade.quant.options.premium import assignment_chance, p_below


def test_return_on_collateral_is_mid_over_strike_for_a_put_and_over_spot_for_a_call() -> None:
    assert float(premium.return_on_collateral(2.0, 100.0, 120.0, "put")) == pytest.approx(0.02)
    assert float(premium.return_on_collateral(2.0, 100.0, 120.0, "call")) == pytest.approx(2 / 120)


def test_yield_is_simple_and_never_infinite() -> None:
    assert float(premium.yield_annualised(0.02, 30)) == pytest.approx(0.02 * 365 / 30)
    out = premium.yield_annualised(np.array([0.02, 0.02, 0.02]), np.array([0.0, -3.0, 365.0]))
    assert np.isnan(out[0]) and np.isnan(out[1]) and out[2] == pytest.approx(0.02)
    assert not np.isinf(out).any()


def test_breakeven_per_right() -> None:
    assert float(premium.breakeven(2.0, 100.0, 120.0, "put")) == 98.0
    assert float(premium.breakeven(2.0, 100.0, 120.0, "call")) == 118.0


def test_a_missing_mid_or_collateral_is_nan() -> None:
    assert np.isnan(premium.return_on_collateral(np.nan, 100.0, 100.0, "put"))
    assert np.isnan(premium.return_on_collateral(1.0, 0.0, 100.0, "put"))
    assert np.isnan(premium.return_on_collateral(1.0, 100.0, -1.0, "call"))


def test_p_below_is_one_minus_prob_otm_for_a_put_and_prob_otm_for_a_call() -> None:
    s, k, v, t = 100.0, 95.0, 0.3, 30 / 365
    assert float(premium.p_below(s, k, v, t, "put")) == pytest.approx(
        1 - float(prob_otm(s, k, v, t, "put"))
    )
    assert float(premium.p_below(s, k, v, t, "call")) == pytest.approx(
        float(prob_otm(s, k, v, t, "call"))
    )


def test_p_below_is_nan_without_a_vol_or_a_time() -> None:
    assert np.isnan(premium.p_below(100.0, 95.0, 0.0, 0.1, "put"))
    assert np.isnan(premium.p_below(100.0, 95.0, 0.3, 0.0, "call"))


def test_a_right_other_than_put_or_call_is_refused() -> None:
    with pytest.raises(ValueError):
        premium.p_below(100.0, 95.0, 0.3, 0.1, "straddle")
    with pytest.raises(ValueError):
        premium.breakeven(1.0, 100.0, 100.0, "C")


def test_assignment_chance_of_one_sold_put_is_its_chance_below_the_strike() -> None:
    expected = float(p_below(100.0, 95.0, 0.3, 30 / 365, "put"))
    assert assignment_chance(100.0, [(95.0, 0.3)], [], 30 / 365) == pytest.approx(expected)


def test_assignment_chance_takes_the_highest_put_and_the_lowest_call_disjointly() -> None:
    t = 30 / 365
    below = float(p_below(100.0, 95.0, 0.3, t, "put"))
    above = 1.0 - float(p_below(100.0, 105.0, 0.25, t, "call"))
    found = assignment_chance(100.0, [(90.0, 0.4), (95.0, 0.3)], [(105.0, 0.25), (110.0, 0.2)], t)
    assert found == pytest.approx(below + above)


def test_overlapping_sold_strikes_are_certain_and_a_missing_vol_is_nan() -> None:
    assert assignment_chance(100.0, [(100.0, 0.3)], [(100.0, 0.3)], 0.1) == 1.0
    assert math.isnan(assignment_chance(100.0, [(95.0, 0.0)], [], 0.1))
    assert assignment_chance(100.0, [], [], 0.1) == 0.0
