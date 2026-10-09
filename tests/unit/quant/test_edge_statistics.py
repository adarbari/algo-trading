"""Edge statistics: hand-computed values, the PSR identity and the PBO limits."""

import math

import numpy as np
import pytest

from algotrade.quant import edge_statistics as es
from algotrade.quant.black_scholes import norm_cdf


def test_lift() -> None:
    assert es.lift(0.6, 0.5) == pytest.approx(1.2)
    assert es.lift(0.6, 0.0) is None
    assert es.lift(None, 0.5) is None
    assert es.lift(0.5, None) is None


def test_standardised_effect_hand_computed() -> None:
    # means 2 vs 1, both var 1, n 3+3: d = 1, J = 1 - 3/15
    assert es.standardised_effect([1, 2, 3], [0, 1, 2]) == pytest.approx(0.8)


def test_standardised_effect_undefined() -> None:
    assert es.standardised_effect([1.0], [1.0, 2.0]) is None
    assert es.standardised_effect([1.0, 2.0], [3.0]) is None
    assert es.standardised_effect([1.0, 1.0], [2.0, 2.0]) is None
    assert es.standardised_effect([1.0, 2.0, float("nan")], [0.0, 1.0]) is not None


def test_decile_spread() -> None:
    assert es.decile_spread(list(range(20, 0, -1)), buckets=10) == pytest.approx(
        (20 + 19) / 2 - (2 + 1) / 2
    )
    assert es.decile_spread([3.0, 1.0], buckets=2) == pytest.approx(2.0)
    assert es.decile_spread([1.0, 2.0, 3.0], buckets=10) is None
    assert es.decile_spread([1.0, 2.0], buckets=1) is None
    assert es.decile_spread([1.0, float("nan")], buckets=2) is None


def test_spread_summary() -> None:
    mean, sd, t, n = es.spread_summary([1.0, 2.0, 3.0, 4.0])
    assert (mean, n) == (2.5, 4)
    assert sd == pytest.approx(math.sqrt(5 / 3))
    assert t == pytest.approx(2.5 / (math.sqrt(5 / 3) / 2))
    assert es.spread_summary([]) == (None, None, None, 0)
    assert es.spread_summary([2.0]) == (2.0, None, None, 1)
    assert es.spread_summary([2.0, 2.0]) == (2.0, 0.0, None, 2)
    assert es.spread_summary([1.0, float("nan"), 3.0])[3] == 2


def test_sharpe() -> None:
    assert es.sharpe([1.0, 2.0, 3.0]) == pytest.approx(2.0)
    assert es.sharpe([1.0]) is None
    assert es.sharpe([1.0, 1.0]) is None


@pytest.mark.parametrize("p", [1e-9, 0.001, 0.02, 0.3, 0.5, 0.9, 0.975, 0.999, 1 - 1e-9])
def test_inverse_normal_round_trips(p: float) -> None:
    assert float(norm_cdf(es.inverse_normal_cdf(p))) == pytest.approx(p, rel=1e-9)


def test_inverse_normal_known_values() -> None:
    assert es.inverse_normal_cdf(0.975) == pytest.approx(1.959963984540054, abs=1e-9)
    assert es.inverse_normal_cdf(0.5) == pytest.approx(0.0, abs=1e-12)


def _series() -> np.ndarray:
    return np.random.default_rng(7).normal(0.001, 0.01, 250)


def test_deflated_sharpe_one_trial_is_psr() -> None:
    x = _series()
    sr = es.sharpe(x)
    assert sr is not None
    z = (x - x.mean()) / x.std()
    skew, kurt = float(np.mean(z**3)), float(np.mean(z**4))
    psr = float(norm_cdf(sr * math.sqrt(249) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)))
    assert es.deflated_sharpe(x, 1, 0.5) == pytest.approx(psr)


def test_deflated_sharpe_falls_with_trials() -> None:
    x = _series()
    one, ten, thousand = (es.deflated_sharpe(x, n, 0.01) for n in (1, 10, 1000))
    assert one is not None and ten is not None and thousand is not None
    assert one > ten > thousand


def test_deflated_sharpe_benchmark_hand_computed() -> None:
    # SR0 for N=10, V=1: (1-g) * Phi^-1(0.9) + g * Phi^-1(1 - 1/(10e))
    sr0 = (1 - es._EULER_GAMMA) * 1.2815515655446004 + es._EULER_GAMMA * es.inverse_normal_cdf(
        1 - 1 / (10 * math.e)
    )
    assert sr0 == pytest.approx(1.5746, abs=1e-3)  # Bailey-Lopez de Prado's table value
    # a flat-return-like series with SR far above SR0 deflates to ~1
    x = np.array([0.02, 0.01, 0.03, 0.02, 0.015, 0.025] * 10)
    assert es.deflated_sharpe(x, 10, 1.0) == pytest.approx(1.0, abs=1e-6)


def test_deflated_sharpe_undefined() -> None:
    assert es.deflated_sharpe([0.1, 0.2], 5, 0.1) is None
    assert es.deflated_sharpe([0.1, 0.1, 0.1, 0.1], 5, 0.1) is None
    assert es.deflated_sharpe(_series(), 0, 0.1) is None
    assert es.deflated_sharpe(_series(), 5, -1.0) is None


def test_pbo_dominant_strategy_is_near_zero() -> None:
    rng = np.random.default_rng(1)
    m = rng.normal(0.0, 0.01, (320, 6))
    m[:, 2] += 0.01
    assert es.pbo_cscv(m) == 0.0


def test_pbo_pure_noise_is_about_half() -> None:
    rng = np.random.default_rng(3)
    pbo = es.pbo_cscv(rng.normal(0.0, 0.01, (320, 20)))
    assert pbo is not None
    assert 0.2 < pbo < 0.8  # one fixed seed: the share is noisy


def test_pbo_is_deterministic() -> None:
    m = np.random.default_rng(5).normal(0.0, 0.01, (160, 5))
    assert es.pbo_cscv(m, splits=8) == es.pbo_cscv(m.copy(), splits=8)


def test_pbo_undefined() -> None:
    assert es.pbo_cscv(np.zeros((100, 1))) is None
    assert es.pbo_cscv(np.zeros((10, 4)), splits=16) is None
    assert es.pbo_cscv(np.zeros((100, 4)), splits=15) is None
    assert es.pbo_cscv(np.zeros(100)) is None
    bad = np.zeros((100, 3))
    bad[0, 0] = np.nan
    assert es.pbo_cscv(bad, splits=4) is None


def test_pbo_ties_and_flat_columns() -> None:
    # identical columns tie everywhere: the pick (lowest index) sits mid-rank, never below
    col = np.random.default_rng(9).normal(0.0, 0.01, (64, 1))
    assert es.pbo_cscv(np.hstack([col, col, col]), splits=4) is not None
    flat = np.hstack([np.zeros((64, 1)), col])
    assert es.pbo_cscv(flat, splits=4) is not None


def _old_effect(a: np.ndarray, b: np.ndarray) -> float | None:
    """The pre-running-moments formula, over the raw values."""
    nx, ny = a.size, b.size
    pooled = ((nx - 1) * a.var(ddof=1) + (ny - 1) * b.var(ddof=1)) / (nx + ny - 2)
    d = (a.mean() - b.mean()) / np.sqrt(pooled)
    return float(d * (1.0 - 3.0 / (4.0 * (nx + ny) - 9.0)))


def test_running_moments_equal_the_raw_formula_even_with_a_large_offset() -> None:
    rng = np.random.default_rng(7)
    for offset in (0.0, 1e6):  # a naive sum of squares loses the variance at 1e6
        a = rng.normal(offset, 0.02, 40)
        parts = [rng.normal(offset, 0.03, n) for n in (500, 1, 3000, 0, 250)]
        whole = np.concatenate(parts)
        n, mean, m2 = es.merge_moments([es.moments(p) for p in parts])
        assert n == whole.size
        assert math.isclose(mean, whole.mean(), rel_tol=1e-12)
        assert math.isclose(m2, ((whole - whole.mean()) ** 2).sum(), rel_tol=1e-9)
        got = es.effect_vs_moments(a, (n, mean, m2))
        assert got is not None and math.isclose(
            got, _old_effect(a, whole), rel_tol=1e-9 if offset == 0 else 1e-6
        )
        assert es.standardised_effect(a, whole) == pytest.approx(got, rel=1e-6)


def test_win_rate_pmf_is_the_binomial_and_sums_to_one() -> None:
    pmf = es.win_rate_pmf(0.5, 4)
    assert pmf is not None and pmf.tolist() == pytest.approx(
        [1 / 16, 4 / 16, 6 / 16, 4 / 16, 1 / 16]
    )
    big = es.win_rate_pmf(0.37, 300)
    assert big is not None and big.sum() == pytest.approx(1.0)


def test_win_rate_pmf_at_the_certain_ends_and_undefined_inputs() -> None:
    assert es.win_rate_pmf(0.0, 3).tolist() == [1.0, 0.0, 0.0, 0.0]  # type: ignore[union-attr]
    assert es.win_rate_pmf(1.0, 3).tolist() == [0.0, 0.0, 0.0, 1.0]  # type: ignore[union-attr]
    assert es.win_rate_pmf(0.5, 0) is None
    assert es.win_rate_pmf(1.2, 5) is None and es.win_rate_pmf(float("nan"), 5) is None


def test_win_rate_band_is_the_10th_to_90th_percentile_of_wins_over_n() -> None:
    # 10 trades at 50%: P(wins <= 2) = 5.5% < 10% <= P(<= 3) = 17.2%;
    # P(<= 6) = 82.8% < 90% <= P(<= 7)
    assert es.win_rate_band(0.5, 10) == (0.3, 0.7)
    assert es.win_rate_band(0.5, 10, 0.05, 0.95) == (0.2, 0.8)


def test_win_rate_band_narrows_with_more_trades_and_contains_the_true_rate() -> None:
    few, many = es.win_rate_band(0.6, 20), es.win_rate_band(0.6, 400)
    assert few is not None and many is not None
    assert many[1] - many[0] < few[1] - few[0] and many[0] < 0.6 < many[1]


def test_win_rate_band_is_undefined_without_trades_or_with_a_bad_quantile() -> None:
    assert es.win_rate_band(0.5, 0) is None
    assert es.win_rate_band(0.5, 10, 0.9, 0.1) is None
    assert es.win_rate_band(1.0, 5) == (1.0, 1.0)
