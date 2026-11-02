"""The sold option's figures: exact identities, NaN edges, the convention of ``p_below``."""

import numpy as np
import pytest

from algotrade.quant.black_scholes import prob_otm
from algotrade.quant.options import premium


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
