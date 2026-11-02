"""CVaR with its tail count, the worst window, the stationary block bootstrap and PSR: hand-computed
values, determinism, and a bootstrap that does not depend on the chunk size."""

import math

import numpy as np
import pytest

from algotrade.quant.edges import tails
from algotrade.quant.edges.statistics import deflated_sharpe
from algotrade.quant.edges.tails import (
    Bootstrap,
    bootstrap_summary,
    cvar,
    psr,
    stationary_bootstrap,
    stationary_indices,
    tail_count,
    worst,
)

X = [-3, -1, 0, 2, 4, 1, -2, 5, 3, 6]


def test_cvar_is_the_mean_of_the_lowest_with_the_count() -> None:
    assert cvar(X, 0.2) == (-2.5, 2)
    assert cvar(X, 0.05) == (-3.0, 1)  # ceil(0.5) = 1
    assert cvar([float("nan"), *X, float("inf")], 0.2) == (-2.5, 2)  # missing is dropped
    assert cvar([], 0.05) == (None, 0)
    assert cvar([float("nan")], 0.05) == (None, 0)


def test_the_tail_count_guards_the_float_and_is_at_least_one() -> None:
    assert 0.07 * 100 > 7.0 and math.ceil(0.07 * 100) == 8  # the float a bare ceil gets wrong
    assert tail_count(100, 0.07) == 7
    assert tail_count(60, 0.05) == 3 and tail_count(100, 0.05) == 5 and tail_count(100, 0.01) == 1
    assert tail_count(1, 0.01) == 1 and tail_count(0, 0.05) == 0
    assert cvar(np.arange(60.0), 0.05) == (1.0, 3)


def test_worst_is_the_lowest_finite_value() -> None:
    assert worst(X) == -3.0 and worst([float("nan"), 2.0]) == 2.0 and worst([]) is None


def test_no_jumps_make_every_draw_a_circular_run_of_the_series() -> None:
    boot = stationary_bootstrap([1, 2, 3, 4], 1e9, 600, 7)
    assert boot == Bootstrap(2.5, 2.5, 2.5, None, 600)


def test_a_mean_block_of_one_is_the_plain_bootstrap() -> None:
    u = np.random.default_rng(11).random((50, 8))
    idx = stationary_indices(u, 1.0)
    assert (idx == np.minimum((u * 8).astype(np.int64), 7)).all()
    assert idx.shape == (50, 8) and idx.min() >= 0 and idx.max() < 8


def test_a_block_continues_circularly_and_a_jump_restarts() -> None:
    u = np.array([[0.30, 0.9, 0.9, 0.9, 0.001, 0.9]])  # p = 0.5: jumps at 0 and at 4 only
    idx = stationary_indices(u, 2.0)
    first = int(0.30 * 6)  # the first start is u itself
    assert idx[0, :4].tolist() == [(first + k) % 6 for k in range(4)]
    restart = int(0.001 / 0.5 * 6)  # a jump's start is u / p
    assert idx[0, 4:].tolist() == [restart, restart + 1]


def test_the_summary_of_injected_draw_means_is_hand_computed() -> None:
    v = np.array([1.0, 2.0, 3.0, 4.0])
    idx = np.array([[0, 0, 0, 0], [3, 3, 3, 3]])
    means = v[idx].mean(axis=1)
    assert means.tolist() == [1.0, 4.0]
    got = bootstrap_summary(2.5, means)
    assert got.lo == pytest.approx(1.15) and got.hi == pytest.approx(3.85)
    assert got.t == pytest.approx(2.5 / math.sqrt(4.5)) and got.draws == 2


def test_same_seed_same_output_and_a_constant_series_has_no_t() -> None:
    v = np.random.default_rng(3).normal(0.01, 0.05, 80)
    a = stationary_bootstrap(v, 3.0, 400, 99)
    assert a == stationary_bootstrap(v, 3.0, 400, 99) and a != stationary_bootstrap(v, 3.0, 400, 98)
    assert a.lo is not None and a.hi is not None and a.lo < a.mean < a.hi  # type: ignore[operator]
    assert a.t == pytest.approx(a.mean / np.std(_means(v, 3.0, 400, 99), ddof=1))
    assert stationary_bootstrap([0.02] * 30, 3.0, 300, 1).t is None


def _means(v: np.ndarray, block: float, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return v[stationary_indices(rng.random((draws, v.size)), block)].mean(axis=1)


def test_the_chunk_size_does_not_change_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    v = np.random.default_rng(5).normal(0, 1, 60)
    whole = stationary_bootstrap(v, 4.0, 1000, 5)
    monkeypatch.setattr(tails, "CHUNK", 7)
    assert stationary_bootstrap(v, 4.0, 1000, 5) == whole
    assert whole.t == pytest.approx(v.mean() / np.std(_means(v, 4.0, 1000, 5), ddof=1))


def test_null_and_short_series_give_a_null_bootstrap() -> None:
    assert stationary_bootstrap([], 3.0, 100, 1) == Bootstrap()
    assert stationary_bootstrap([1.0], 3.0, 100, 1) == Bootstrap()
    assert stationary_bootstrap([float("nan"), 1.0], 3.0, 100, 1) == Bootstrap()
    assert stationary_bootstrap([float("nan"), 1.0, 2.0], 1e9, 100, 1).mean == 1.5


def test_psr_is_the_deflated_sharpe_of_one_trial() -> None:
    v = np.random.default_rng(8).normal(0.01, 0.04, 120)
    assert psr(v) == deflated_sharpe(v, 1, 0.0) and psr(v) is not None
    assert psr([1.0, 2.0]) is None
