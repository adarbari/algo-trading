"""Edge statistics: hand-computed values, the PSR identity and the PBO limits."""

import math

import numpy as np
import pytest

from algotrade.quant.black_scholes import norm_cdf
from algotrade.quant.edges import statistics as es


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


def test_percentile_of_counts_ties_half_and_is_none_without_a_value_or_sample() -> None:
    assert es.percentile_of(2.5, [1.0, 2.0, 3.0, 4.0]) == 0.5
    assert es.percentile_of(2.0, [1.0, 2.0, 3.0, 4.0]) == pytest.approx(0.375)  # 1 below, 1 tie
    assert es.percentile_of(9.0, [1.0, float("nan"), 3.0]) == 1.0  # a NaN is not a draw
    assert es.percentile_of(0.0, [1.0, 2.0]) == 0.0
    assert es.percentile_of(None, [1.0]) is None and es.percentile_of(1.0, []) is None


def test_random_pick_sums_are_without_replacement_uniform_and_reproducible() -> None:
    values, hits = np.arange(20, dtype=float), (np.arange(20) % 2).astype(float)
    a = es.random_pick_sums(values, hits, 5, 400, np.random.default_rng(7))
    b = es.random_pick_sums(values, hits, 5, 400, np.random.default_rng(7))
    assert a is not None and b is not None
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])
    assert a[0].min() >= 0 + 1 + 2 + 3 + 4 and a[0].max() <= 15 + 16 + 17 + 18 + 19  # 5 distinct
    assert a[0].mean() == pytest.approx(5 * 9.5, abs=1.0)  # uniform: the mean pick is the mean
    assert a[1].mean() == pytest.approx(2.5, abs=0.3)


def test_random_pick_sums_with_k_at_or_above_the_names_take_every_name() -> None:
    sums = es.random_pick_sums([1.0, 2.0, 3.0], [1, 0, 1], 5, 3, np.random.default_rng(0))
    assert sums is not None
    np.testing.assert_array_equal(sums[0], [6.0, 6.0, 6.0])
    np.testing.assert_array_equal(sums[1], [2.0, 2.0, 2.0])
    assert es.random_pick_sums([], [], 5, 3, np.random.default_rng(0)) is None
    assert es.random_pick_sums([1.0], [1], 1, 0, np.random.default_rng(0)) is None


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


def test_haircut_sharpe_matches_the_papers_illustration() -> None:
    # Harvey and Liu (2015): a t-ratio of 3.0 whose p-value is adjusted to 0.05 is a t-ratio of
    # about 2.0, a haircut of about a third. 18 trials take p = 0.0027 to 0.0486.
    n = 100
    h = es.haircut_sharpe(3.0 / math.sqrt(n), n, 18)
    assert h is not None
    assert h.t == pytest.approx(3.0)
    assert h.p == pytest.approx(math.erfc(3.0 / math.sqrt(2.0)))  # 0.0026998
    assert h.p_adjusted == pytest.approx(18 * h.p)
    t_adjusted = h.sharpe * math.sqrt(n)
    assert math.erfc(t_adjusted / math.sqrt(2.0)) == pytest.approx(h.p_adjusted)  # 0.0486
    assert t_adjusted == pytest.approx(1.9721, abs=1e-3)
    assert h.cut == pytest.approx(1.0 - t_adjusted / 3.0)
    assert h.cut == pytest.approx(1.0 / 3.0, abs=0.03)


def test_haircut_sharpe_one_trial_leaves_the_sharpe_ratio() -> None:
    h = es.haircut_sharpe(0.3, 50, 1)
    assert h is not None
    assert h.cut == pytest.approx(0.0, abs=1e-6)
    assert h.sharpe == pytest.approx(0.3, abs=1e-6)


def test_haircut_sharpe_grows_with_trials_and_caps_at_everything() -> None:
    cuts = [es.haircut_sharpe(0.3, 50, m) for m in (1, 10, 100, 100000)]
    values = [c.cut for c in cuts if c is not None]
    assert values == sorted(values)
    assert values[-1] == 1.0  # the adjusted p-value reached 1: nothing is left
    assert cuts[-1] is not None
    assert cuts[-1].sharpe == 0.0


@pytest.mark.parametrize(
    ("sr", "n", "trials"),
    [
        (None, 50, 3),
        (0.3, None, 3),
        (0.3, 50, None),
        (0.0, 50, 3),
        (-0.2, 50, 3),
        (0.3, 1, 3),
        (0.3, 50, 0),
    ],
)
def test_haircut_sharpe_is_undefined_without_a_positive_sharpe_periods_or_trials(
    sr: float | None, n: int | None, trials: int | None
) -> None:
    assert es.haircut_sharpe(sr, n, trials) is None


def test_sharpe_t_is_the_sharpe_ratios_t_ratio_the_one_haircut_sharpe_reads() -> None:
    x = [1.0, 2.0, 3.0, 2.0, 1.5]
    n, sr = len(x), es.sharpe(x)
    assert sr is not None
    assert es.sharpe_t(x) == pytest.approx(sr * math.sqrt(n))
    h = es.haircut_sharpe(sr, n, 1)
    assert h is not None and es.sharpe_t(x) == pytest.approx(h.t)
    assert es.sharpe_t([-1.0, -2.0, -3.0]) < 0  # signed: a losing series has a negative t
    assert es.sharpe_t([1.0]) is None and es.sharpe_t([1.0, 1.0]) is None
