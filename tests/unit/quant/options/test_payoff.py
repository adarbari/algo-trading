"""A short option's payoff figures: exact identities per right and the NaN edges."""

import numpy as np
import pytest

from algotrade.quant.options import payoff


def test_short_breakeven_is_strike_less_credit_for_a_put_and_plus_for_a_call() -> None:
    # The mockup's roll: sold at 1.40, rolled for 0.48 more, strike 85 -> 83.12.
    assert float(payoff.short_breakeven(85.0, 1.40 + 0.48, "put")) == pytest.approx(83.12)
    assert float(payoff.short_breakeven(85.0, 1.88, "call")) == pytest.approx(86.88)


def test_credit_per_day_is_nan_where_no_day_is_added() -> None:
    assert float(payoff.credit_per_day(0.48, 7)) == pytest.approx(0.48 / 7)
    out = payoff.credit_per_day(np.array([0.5, 0.5]), np.array([0.0, -1.0]))
    assert np.isnan(out).all()


def test_called_away_return_keeps_the_premium_and_is_nan_without_a_basis() -> None:
    # The mockup: basis 83.60, strike 85, premium 2.13 -> +4.2%.
    assert float(payoff.called_away_return(85.0, 2.13, 83.60)) == pytest.approx(0.0422, abs=1e-4)
    assert np.isnan(payoff.called_away_return(85.0, 2.13, 0.0))


def test_extrinsic_is_the_mid_less_intrinsic_per_right() -> None:
    assert float(payoff.extrinsic(5.0, 102.0, 100.0, "call")) == pytest.approx(3.0)
    assert float(payoff.extrinsic(5.0, 102.0, 100.0, "put")) == pytest.approx(5.0)
    assert float(payoff.extrinsic(5.0, 97.0, 100.0, "put")) == pytest.approx(2.0)


def test_an_unknown_right_is_an_error() -> None:
    with pytest.raises(ValueError, match="right"):
        payoff.short_breakeven(1.0, 1.0, "straddle")
