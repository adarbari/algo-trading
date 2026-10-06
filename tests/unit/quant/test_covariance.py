"""Turbulence and the absorption ratio: hand-computed panels, singular covariances, NaN, errors."""

import statistics
from collections.abc import Callable

import numpy as np
import pytest

from algotrade.quant import covariance as cv

# Four sessions of two assets: mean 0, covariance [[4/3, 2/3], [2/3, 2/3]] (ddof 1), whose
# inverse is [[1.5, -1.5], [-1.5, 3]]; for (1, -1): 1.5 + 2 * 1.5 + 3 = 7.5.
HISTORY = np.array([[1.0, 1.0], [-1.0, -1.0], [1.0, 0.0], [-1.0, 0.0]])
TODAY = np.array([[1.0, -1.0]])

# Columns 1..7 of the 8 x 8 Sylvester-Hadamard matrix: +/-1, zero mean, mutually orthogonal,
# so every window of these 8 rows has covariance (8 / 7) * identity.
_H2 = np.array([[1.0, 1.0], [1.0, -1.0]])
HADAMARD = np.kron(np.kron(_H2, _H2), _H2)[:, 1:]


def test_turbulence_by_hand() -> None:
    out = cv.turbulence(np.vstack([HISTORY, TODAY]), window=4)
    assert np.isnan(out[:4]).all()
    assert out[4] == pytest.approx(7.5, rel=1e-12)


def test_turbulence_measures_from_the_window_mean() -> None:
    shift = np.array([0.01, -0.02])
    out = cv.turbulence(np.vstack([HISTORY, TODAY]) + shift, window=4)
    assert out[4] == pytest.approx(7.5, rel=1e-9)


def test_turbulence_uses_only_the_window_before_the_session() -> None:
    old = np.array([[50.0, -40.0]])  # outside the window: must not matter
    out = cv.turbulence(np.vstack([old, HISTORY, TODAY]), window=4)
    assert out[5] == pytest.approx(7.5, rel=1e-12)


def test_turbulence_singular_covariance_uses_the_pseudo_inverse() -> None:
    # Asset 2 is twice asset 1: one direction (1, 2) with variance 4/3 * 5; along it,
    # (1, 2) is one stdev-of-asset-1 move: 1 / (4/3) = 0.75. A move off that line has no
    # defined distance: NaN, not 0.
    history = np.array([[1.0, 2.0], [-1.0, -2.0], [1.0, 2.0], [-1.0, -2.0]])
    along = cv.turbulence(np.vstack([history, [[1.0, 2.0]]]), window=4)
    across = cv.turbulence(np.vstack([history, [[2.0, -1.0]]]), window=4)
    assert along[4] == pytest.approx(0.75, rel=1e-9)
    assert np.isnan(across[4])


def test_turbulence_of_a_forward_filled_asset_that_moves_is_nan() -> None:
    # Asset 2 is forward-filled (zero returns) through the window, then moves 10%.
    history = np.column_stack([HISTORY[:, 0], np.zeros(4)])
    moved = cv.turbulence(np.vstack([history, [[1.0, 0.10]]]), window=4)
    still = cv.turbulence(np.vstack([history, [[1.0, 0.0]]]), window=4)
    assert np.isnan(moved[4])
    assert still[4] == pytest.approx(0.75, rel=1e-9)  # 1 / var(asset 1) = 1 / (4/3)


def test_turbulence_with_more_assets_than_window_rows_is_nan() -> None:
    panel = np.random.default_rng(3).normal(size=(6, 5))  # 4 rows span at most 3 directions
    assert np.isnan(cv.turbulence(panel, window=4)[4:]).all()


def test_turbulence_of_a_constant_window() -> None:
    history = np.ones((4, 2))
    assert cv.turbulence(np.vstack([history, [[1.0, 1.0]]]), window=4)[4] == 0.0
    assert np.isnan(cv.turbulence(np.vstack([history, [[3.0, 3.0]]]), window=4)[4])


def test_turbulence_nan_in_the_window_or_the_session() -> None:
    panel = np.vstack([HISTORY, TODAY, TODAY, TODAY, TODAY, TODAY])
    panel[1, 0] = np.nan  # in the windows of sessions 4 and 5
    panel[7, 1] = np.nan  # session 7 itself, and the windows of 8
    out = cv.turbulence(panel, window=4)
    assert np.isnan(out[[4, 5, 7, 8]]).all()
    assert np.isfinite(out[6])


def test_absorption_of_a_perfectly_correlated_panel_is_one() -> None:
    base = np.random.default_rng(7).normal(size=30)
    panel = np.column_stack([base, 2 * base, -0.5 * base, 3 * base, base, base])
    out = cv.absorption_ratio(panel, window=10)
    assert np.isnan(out[:9]).all()
    np.testing.assert_allclose(out[9:], 1.0, rtol=1e-12)


def test_absorption_of_an_uncorrelated_panel_is_one_over_n() -> None:
    out = cv.absorption_ratio(HADAMARD[:, :4], window=8, components=1)
    assert out[-1] == pytest.approx(1 / 4, rel=1e-12)


def test_absorption_defaults_to_a_fifth_of_the_assets() -> None:
    panel = np.kron(np.kron(np.kron(_H2, _H2), _H2), _H2)[:, 1:11]  # 16 x 10, orthogonal
    out = cv.absorption_ratio(panel, window=16)
    assert out[-1] == pytest.approx(2 / 10, rel=1e-12)  # N // 5 = 2 of 10 equal eigenvalues


def test_absorption_by_hand_on_two_assets() -> None:
    # Covariance [[4/3, 2/3], [2/3, 2/3]]: eigenvalues 1 +/- sqrt(5)/3, trace 2.
    out = cv.absorption_ratio(HISTORY, window=4)
    assert out[3] == pytest.approx((1 + 5**0.5 / 3) / 2, rel=1e-12)


def test_absorption_with_exponential_weights() -> None:
    panel = np.random.default_rng(11).normal(size=(30, 4))
    panel[20:, 1] += 2 * panel[20:, 0]  # the last rows are more correlated
    out = cv.absorption_ratio(panel, window=20, components=1, half_life=5)
    rows = panel[10:30]
    weights = 0.5 ** (np.arange(19, -1, -1) / 5)
    mean = weights @ rows / weights.sum()
    cov = (rows - mean).T @ ((rows - mean) * weights[:, None])  # the scale cancels in a share
    values = np.linalg.eigvalsh(cov)
    assert out[-1] == pytest.approx(values[-1] / values.sum(), rel=1e-10)
    equal = cv.absorption_ratio(panel, window=20, components=1)
    assert out[-1] > equal[-1]  # recent rows, more correlated, weigh more
    flat = cv.absorption_ratio(panel, window=20, components=1, half_life=1e12)
    np.testing.assert_allclose(flat, equal, rtol=1e-9)


def test_absorption_nan_window_and_zero_variance() -> None:
    panel = np.vstack([HADAMARD[:, :4], HADAMARD[:, :4]])
    panel[2, 3] = np.nan
    out = cv.absorption_ratio(panel, window=8)
    assert np.isnan(out[7:10]).all() and np.isfinite(out[10:]).all()
    assert np.isnan(cv.absorption_ratio(np.ones((5, 3)), window=3)[2:]).all()


def test_absorption_shift_by_hand() -> None:
    ar = np.array([0.50, 0.52, 0.55, 0.51, 0.60, 0.70])
    out = cv.absorption_shift(ar, short=2, long=4)
    assert np.isnan(out[:3]).all()
    for t in range(3, 6):
        window = list(ar[t - 3 : t + 1])
        expected = (statistics.fmean(window[-2:]) - statistics.fmean(window)) / statistics.stdev(
            window
        )
        assert out[t] == pytest.approx(expected, rel=1e-12)


def test_absorption_shift_nan_and_constant_windows() -> None:
    ar = np.array([0.5, 0.5, 0.5, 0.5, np.nan, 0.6, 0.7, 0.8, 0.9])
    out = cv.absorption_shift(ar, short=1, long=4)
    assert np.isnan(out[:8]).all()  # constant window, then windows holding the NaN
    assert np.isfinite(out[8])


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: cv.turbulence(np.ones(5), 3), "2-d"),
        (lambda: cv.turbulence(np.ones((5, 2)), 1), "window"),
        (lambda: cv.absorption_ratio(np.ones((5, 0)), 3), "2-d"),
        (lambda: cv.absorption_ratio(np.ones((5, 2)), 3, components=3), "components"),
        (lambda: cv.absorption_ratio(np.ones((5, 2)), 3, components=0), "components"),
        (lambda: cv.absorption_ratio(np.ones((5, 2)), 3, half_life=0), "half_life"),
        (lambda: cv.absorption_shift(np.ones((5, 2))), "1-d"),
        (lambda: cv.absorption_shift(np.ones(5), short=5, long=4), "short"),
        (lambda: cv.absorption_shift(np.ones(5), short=0, long=4), "short"),
        (lambda: cv.absorption_shift(np.ones(5), short=1, long=1), "short"),
    ],
)
def test_input_errors(call: Callable[[], object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()
