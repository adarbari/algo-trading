"""An option position's figures: exact payoffs, the unbounded case, NaN edges, the chance in the
money's convention and the one-sigma day against a hand reprice."""

import numpy as np
import pytest

from algotrade.quant.black_scholes import price, prob_otm
from algotrade.quant.options import position


def _arr(*xs: float) -> np.ndarray:
    return np.array(xs, dtype=np.float64)


def test_a_short_put_loses_the_strike_less_the_credit() -> None:
    lost = position.max_loss(_arr(-1), _arr(55), _arr(0), 0.71)
    assert lost == pytest.approx((55 - 0.71) * 100)


def test_a_put_spread_loses_the_width_less_the_credit() -> None:
    lost = position.max_loss(_arr(-1, 1), _arr(55, 50), _arr(0, 0), 1.10)
    assert lost == pytest.approx((5 - 1.10) * 100)


def test_a_covered_call_loses_the_share_cost_less_the_credit() -> None:
    lost = position.max_loss(_arr(-1), _arr(65), _arr(1), 0.80, shares=100, share_entry=60.0)
    assert lost == pytest.approx((60 - 0.80) * 100)


def test_a_naked_call_is_unbounded() -> None:
    assert position.max_loss(_arr(-1), _arr(65), _arr(1), 0.80) is None


def test_a_credit_that_covers_every_outcome_loses_nothing() -> None:
    assert position.max_loss(_arr(-1, 1), _arr(50, 55), _arr(0, 0), 6.0) == 0.0


def test_a_missing_credit_or_strike_is_nan() -> None:
    assert np.isnan(position.max_loss(_arr(-1), _arr(55), _arr(0), float("nan")))
    assert np.isnan(position.max_loss(_arr(-1), _arr(float("nan")), _arr(0), 0.5))


def test_theta_is_the_signed_sum_in_dollars_a_day_and_never_partial() -> None:
    assert position.position_theta(_arr(-1), _arr(-0.02)) == pytest.approx(2.0)
    assert position.position_theta(_arr(-1, 1), _arr(-0.02, -0.01)) == pytest.approx(1.0)
    assert np.isnan(position.position_theta(_arr(-1, 1), _arr(-0.02, float("nan"))))


def test_chance_in_the_money_is_the_chance_below_a_put_strike_and_above_a_call_strike() -> None:
    strike, iv, days = _arr(55, 65), _arr(0.4, 0.4), _arr(35, 35)
    out = position.p_itm(60.0, strike, iv, days, _arr(0, 1))
    t = 35 / 365
    assert out[0] == pytest.approx(1 - float(prob_otm(60.0, 55.0, 0.4, t, "put")))
    assert out[1] == pytest.approx(1 - float(prob_otm(60.0, 65.0, 0.4, t, "call")))
    assert 0 < out[0] < 0.5 and 0 < out[1] < 0.5


def test_chance_in_the_money_is_nan_without_a_positive_iv_or_time() -> None:
    out = position.p_itm(60.0, _arr(55, 55), _arr(0.0, 0.4), _arr(35, 0), _arr(0, 0))
    assert np.isnan(out).all()


def test_one_sigma_day_loss_matches_a_hand_reprice_of_a_short_put() -> None:
    spot, strike, iv, days = 60.0, 55.0, 0.4, 35.0
    move = spot * iv / np.sqrt(252)
    t = days / 365

    def put(at: float) -> float:
        return float(price(at, strike, t, 0.0, 0.0, iv, False))

    expected = -(-1 * (put(spot - move) - put(spot))) * 100
    got = position.one_sigma_day_loss(spot, _arr(-1), _arr(strike), _arr(0), _arr(iv), _arr(days))
    assert got == pytest.approx(expected)
    assert got > 0


def test_a_short_put_loses_on_a_down_day_and_a_hedged_pair_loses_nothing() -> None:
    down = position.one_sigma_day_loss(60.0, _arr(-1), _arr(55), _arr(0), _arr(0.4), _arr(35))
    assert down > 0
    flat = position.one_sigma_day_loss(
        60.0, _arr(-1, 1), _arr(55, 55), _arr(0, 0), _arr(0.4, 0.4), _arr(35, 35)
    )
    assert flat == pytest.approx(0.0)


def test_one_sigma_day_loss_is_nan_when_an_iv_is_missing_and_never_negative() -> None:
    nan = position.one_sigma_day_loss(
        60.0, _arr(-1), _arr(55), _arr(0), _arr(float("nan")), _arr(35)
    )
    assert np.isnan(nan)
    longcall = position.one_sigma_day_loss(60.0, _arr(1), _arr(60), _arr(1), _arr(0.4), _arr(35))
    assert longcall >= 0
