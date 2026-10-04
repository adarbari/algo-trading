"""One criterion against one value: outcome, distance, penalty (HARD / SOFT / SCORE)."""

import math

import pytest

from algotrade.core.model.predicates import Rule
from algotrade.core.model.screen_spec import Criterion, Mode, Tolerance
from algotrade.strategies.screeners.rules.criteria import (
    FAIL_PENALTY,
    NEAR_MISS_PENALTY,
    Outcome,
    distance,
    evaluate_criterion,
)

GTE = Rule("f", "gte", 0.10)
BAND = Tolerance(0.02)


def soft(rule: Rule = GTE, tolerance: Tolerance = BAND) -> Criterion:
    return Criterion("c", rule, Mode.SOFT, tolerance)


def test_hard_is_strict() -> None:
    hard = Criterion("c", GTE)
    assert evaluate_criterion(hard, 0.10).outcome is Outcome.PASS
    miss = evaluate_criterion(hard, 0.0999)
    assert miss.outcome is Outcome.FAIL and miss.penalty == FAIL_PENALTY
    assert miss.distance == pytest.approx(0.0001)


def test_soft_tolerance_band() -> None:
    near = evaluate_criterion(soft(), 0.09)
    assert near.outcome is Outcome.NEAR
    assert near.normalised == pytest.approx(0.5)
    assert near.penalty == pytest.approx(NEAR_MISS_PENALTY * 0.5)
    edge = evaluate_criterion(soft(), 0.08)
    assert edge.outcome is Outcome.NEAR and edge.normalised == pytest.approx(1.0)
    beyond = evaluate_criterion(soft(), 0.07)
    assert beyond.outcome is Outcome.FAIL and beyond.penalty == FAIL_PENALTY
    assert beyond.normalised == pytest.approx(1.5)


def test_relative_tolerance_and_lt_between() -> None:
    relative = soft(Rule("f", "lte", 50.0), Tolerance(0.1, relative=True))  # band 5
    assert evaluate_criterion(relative, 54.0).outcome is Outcome.NEAR
    assert evaluate_criterion(relative, 56.0).outcome is Outcome.FAIL
    between = soft(Rule("f", "between", (1.0, 2.0)), Tolerance(0.5))
    low, high = evaluate_criterion(between, 0.75), evaluate_criterion(between, 2.6)
    assert (low.outcome, low.threshold(), low.distance) == (Outcome.NEAR, 1.0, 0.25)
    assert (high.outcome, high.threshold()) == (Outcome.FAIL, 2.0)


@pytest.mark.parametrize("value", [None, math.nan, "text", True])
def test_missing_or_wrong_type_never_passes(value: object) -> None:
    for mode in (Mode.HARD, Mode.SOFT):
        crit = Criterion("c", GTE, mode, Tolerance(0.02) if mode is Mode.SOFT else None)
        result = evaluate_criterion(crit, value)  # type: ignore[arg-type]
        assert result.outcome is Outcome.MISSING and result.describe() == "no f"
        # never a pass, never skipped: a HARD miss is a fail, a SOFT one costs points
        assert result.penalty == (FAIL_PENALTY if mode is Mode.HARD else NEAR_MISS_PENALTY)
    score = Criterion("c", GTE, Mode.SCORE, Tolerance(0.02))
    assert evaluate_criterion(score, None).penalty == NEAR_MISS_PENALTY


def test_score_mode_penalties_are_capped() -> None:
    with_band = Criterion("c", GTE, Mode.SCORE, Tolerance(0.02))
    assert evaluate_criterion(with_band, 0.09).penalty == pytest.approx(5.0)
    assert evaluate_criterion(with_band, 0.0).penalty == NEAR_MISS_PENALTY
    no_band = Criterion("c", Rule("f", "eq", "HIGH"), Mode.SCORE)
    result = evaluate_criterion(no_band, "LOW")
    assert result.outcome is Outcome.FAIL and result.penalty == NEAR_MISS_PENALTY
    assert result.distance is None and result.threshold() is None


def test_distance_is_none_for_non_numeric() -> None:
    assert distance(Criterion("c", Rule("f", "eq", 1)), 2) is None
    assert distance(Criterion("c", GTE), "x") is None
    assert distance(Criterion("c", Rule("f", "gt", "a")), 1.0) is None


def test_describe_reasons() -> None:
    assert (
        evaluate_criterion(soft(), 0.09).describe() == "c near miss: 0.09, needs gte 0.1 (by 0.01)"
    )
    assert evaluate_criterion(Criterion("c", GTE), 0.0).describe() == "c fail: 0.0, needs gte 0.1"
