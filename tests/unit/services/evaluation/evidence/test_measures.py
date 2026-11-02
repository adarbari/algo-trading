"""The evidence measures over a series of sessions: hand-computed on a small fixture, null where
nothing is measured, the block correction for overlapping windows, and a seed that is a function of
the trial identity alone."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

from algotrade.config.edges.verdict import TailsVerdict
from algotrade.quant.edges.tails import stationary_bootstrap
from algotrade.services.evaluation.cross_section.legs import key
from algotrade.services.evaluation.evidence.measures import (
    TailMeasures,
    bootstrap_seed,
    mean_block,
    tail_measures,
)

NAN = float("nan")
TAILS = TailsVerdict(bootstrap_draws=200)
ONE_TAIL = TailsVerdict(bootstrap_draws=200, min_tail_windows=1)


def _weekdays(n: int) -> list[date]:
    out, day = [], date(2025, 1, 6)  # a Monday
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def _measures(
    roc: list[float],
    base: list[float],
    bootstrap: bool = False,
    horizon: int = 1,
    tails: TailsVerdict = TAILS,
):
    return tail_measures(
        _weekdays(len(roc)), roc, base, horizon, "trial", "all:all:1", tails, bootstrap
    )


def test_hand_computed_measures_with_the_pairs_kept_where_both_are_known() -> None:
    roc = [0.02, 0.01, NAN, -0.03, 0.04]
    base = [0.01, NAN, 0.00, -0.01, 0.01]
    got = _measures(roc, base, tails=ONE_TAIL)
    assert got.roc_sessions == 4  # the sessions with a return on capital
    assert got.mean_roc == pytest.approx(0.01)
    assert got.excess_roc == pytest.approx((0.01 - 0.02 + 0.03) / 3)  # pairs 0, 3 and 4
    assert (got.cvar_5, got.cvar_5_n, got.cvar_1, got.cvar_1_n) == (-0.03, 1, -0.03, 1)
    assert got.worst_window == -0.03
    assert got.base_cvar_5 == pytest.approx(-0.01)  # the base's lowest over the 3 paired sessions
    assert got.psr is not None and 0 < got.psr < 1
    assert (got.mean_roc_lo, got.mean_roc_hi, got.excess_roc_t) == (
        None,
        None,
        None,
    )  # no bootstrap


def test_cvar_counts_the_windows_in_the_tail() -> None:
    roc = [float(i) for i in range(-30, 30)]  # 60 sessions: ceil(0.05 * 60) = 3, ceil(0.6) = 1
    got = _measures(roc, [0.0] * 60, tails=ONE_TAIL)
    assert (got.cvar_5, got.cvar_5_n) == (-29.0, 3) and (got.cvar_1, got.cvar_1_n) == (-30.0, 1)
    assert got.base_cvar_5 == 0.0


def test_the_base_cvar_is_over_the_paired_sessions_not_the_bases_own() -> None:
    """The base's worst window lies on a session the setup has no return for: it is not in the
    ratio's denominator (own and base tails must cover the same sessions)."""
    roc = [0.01, NAN, 0.02, 0.01]
    base = [-0.01, -0.50, -0.02, -0.01]
    got = _measures(roc, base, tails=ONE_TAIL)
    assert got.base_cvar_5 == pytest.approx(-0.02)  # not -0.50


def test_a_base_tail_under_min_tail_windows_is_not_measured() -> None:
    roc = [float(i) / 100 for i in range(-30, 30)]
    base = [-0.01] * 60  # 3 windows in the 5% tail, the setting asks for 5
    assert _measures(roc, base).base_cvar_5 is None
    assert _measures(roc, base, tails=ONE_TAIL).base_cvar_5 == pytest.approx(-0.01)
    long_enough = _measures([0.0] * 100, [-0.01] * 100)  # 5 windows
    assert long_enough.base_cvar_5 == pytest.approx(-0.01)


def test_fewer_than_two_sessions_measure_nothing_and_no_series_is_all_null() -> None:
    assert _measures([0.01], [0.0]) == TailMeasures(roc_sessions=1)
    assert _measures([], []) == TailMeasures()
    assert _measures([NAN, NAN, NAN], [0.0] * 3) == TailMeasures()  # nothing known: never 0
    one_pair = _measures([0.02, 0.01, 0.03], [0.01, NAN, NAN])  # a single pair is no excess
    assert one_pair.excess_roc is None and one_pair.roc_sessions == 3


def test_an_unknown_base_gives_a_null_excess_and_a_null_base_cvar() -> None:
    got = _measures([0.02, 0.01, -0.03, 0.04], [NAN] * 4, bootstrap=True)
    assert got.excess_roc is None and got.excess_roc_t is None and got.base_cvar_5 is None
    assert got.cvar_5 == -0.03 and got.mean_roc_lo is not None  # the setup's own figures stand


def test_the_bootstrap_is_the_seeded_stationary_bootstrap_of_the_series() -> None:
    rng = np.random.default_rng(2)
    roc = list(rng.normal(0.01, 0.05, 80))
    base = list(rng.normal(0.0, 0.04, 80))
    got = _measures(roc, base, bootstrap=True)
    want = stationary_bootstrap(roc, 3.0, 200, bootstrap_seed("trial", "all:all:1:roc"))
    assert (got.mean_roc_lo, got.mean_roc_hi) == (want.lo, want.hi)
    diff = np.array(roc) - np.array(base)
    t = stationary_bootstrap(diff, 3.0, 200, bootstrap_seed("trial", "all:all:1:excess")).t
    assert got.excess_roc_t == t and got.excess_roc == pytest.approx(float(diff.mean()))
    assert got == _measures(roc, base, bootstrap=True)  # the same inputs, the same output


def test_overlapping_windows_raise_the_mean_block_to_the_window() -> None:
    days = _weekdays(60)
    assert mean_block(days, 1, TAILS) == 3.0  # spaced a window apart: the setting
    assert mean_block(days, 20, TAILS) == pytest.approx(20.0, rel=0.05)  # daily starts, 20 held
    assert mean_block(days, 2, TAILS) == 3.0  # the larger of the two
    wide = TailsVerdict(bootstrap_mean_block=30.0)
    assert mean_block(days, 20, wide) == 30.0


def test_the_seed_is_the_trial_and_the_label_and_nothing_that_moves_with_the_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = bootstrap_seed("abc", "all:all:5:roc")
    assert seed == bootstrap_seed("abc", "all:all:5:roc")
    assert seed != bootstrap_seed("abc", "all:all:5:excess")
    assert seed != bootstrap_seed("abd", "all:all:5:roc")
    assert seed == 8071256762998494151  # FROZEN with BOOTSTRAP_SEED_VERSION: a change re-seeds all
    monkeypatch.setattr(key, "LEG_VERSION", key.LEG_VERSION + 1)  # E6a's lesson
    assert bootstrap_seed("abc", "all:all:5:roc") == seed
    assert bootstrap_seed("abc", "all:all:1:roc") != seed and math.isfinite(seed)
