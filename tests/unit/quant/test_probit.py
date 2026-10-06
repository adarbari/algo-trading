"""``quant.probit``: coefficients recovered from a simulated probit, the score is zero at the fit,
the likelihood by hand, separation does not converge, bad input is refused, deterministic."""

import math

import numpy as np
import pytest

from algotrade.quant.black_scholes import norm_cdf, norm_pdf
from algotrade.quant.probit import fit, predict

TRUE = np.array([-0.5, 1.2, -0.8])


def simulated(n: int = 4000, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = np.column_stack([np.ones(n), rng.normal(size=n), rng.normal(size=n)])
    y = (x @ TRUE + rng.normal(size=n) > 0).astype(float)
    return x, y


def test_the_coefficients_of_a_simulated_probit_are_recovered() -> None:
    x, y = simulated()
    got = fit(x, y, max_iter=50, tol=1e-10)
    assert got.converged
    assert got.coef == pytest.approx(TRUE, abs=0.1)
    z = x @ got.coef
    q = 2 * y - 1
    score = x.T @ (q * norm_pdf(q * z) / norm_cdf(q * z))
    assert np.max(np.abs(score)) < 1e-6  # the first-order condition holds at the fit
    assert got.loglik == pytest.approx(float(np.sum(np.log(norm_cdf(q * z)))))
    again = fit(x, y, max_iter=50, tol=1e-10)
    assert np.array_equal(again.coef, got.coef) and again.loglik == got.loglik


def test_a_constant_alone_fits_the_share_of_ones() -> None:
    y = np.array([1.0, 0.0, 0.0, 1.0, 0.0])
    got = fit(np.ones((5, 1)), y)
    assert got.converged and float(norm_cdf(got.coef[0])) == pytest.approx(0.4, abs=1e-9)
    assert got.loglik == pytest.approx(2 * math.log(0.4) + 3 * math.log(0.6))


def test_predict_is_the_normal_cdf_of_the_index() -> None:
    coef = np.array([0.1, 2.0])
    rows = np.array([[1.0, 0.0], [1.0, -0.05], [1.0, np.nan]])
    got = predict(rows, coef)
    assert got[:2] == pytest.approx([norm_cdf(0.1), norm_cdf(0.0)])
    assert np.isnan(got[2])
    assert float(predict([1.0, 1.0], coef)) == pytest.approx(float(norm_cdf(2.1)))


def test_separable_classes_do_not_converge() -> None:
    x = np.column_stack([np.ones(6), [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0]])
    got = fit(x, [0, 0, 0, 1, 1, 1], max_iter=15)
    assert not got.converged and got.coef[1] > 1.0  # the slope runs off
    assert got.loglik > -1e-3


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="n x k"):
        fit(np.ones(3), [0, 1, 0])
    with pytest.raises(ValueError, match="0 or 1"):
        fit(np.ones((3, 1)), [0, 2, 0])
    with pytest.raises(ValueError, match="finite"):
        fit(np.array([[1.0], [np.nan], [1.0]]), [0, 1, 0])
    with pytest.raises(ValueError, match="rows"):
        fit(np.ones((1, 2)), [1])
    with pytest.raises(ValueError, match="linearly dependent"):
        fit(np.ones((4, 2)), [0, 1, 0, 1])
    with pytest.raises(ValueError, match="max_iter"):
        fit(np.ones((3, 1)), [0, 1, 0], max_iter=0)
