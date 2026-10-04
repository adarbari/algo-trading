"""One criterion against one value: PASS, NEAR (within tolerance), FAIL or MISSING, the
distance from the threshold and the score penalty (ADR 0029, ``docs/screeners/rules.md``).

Penalties: a near miss (SOFT or SCORE within tolerance) costs ``NEAR_MISS_PENALTY x
distance / tolerance``; a SCORE miss beyond its tolerance (or without one, or missing) the
full ``NEAR_MISS_PENALTY``; a HARD fail or a SOFT fail beyond tolerance ``FAIL_PENALTY``.
Missing data on a gating criterion has no penalty: the row is SKIPPED, never scored.
"""

from dataclasses import dataclass
from enum import StrEnum

from algotrade.core.model.predicates import FieldValue, evaluate_rule, is_missing
from algotrade.core.model.screen_spec import Criterion, Mode

NEAR_MISS_PENALTY = 10.0
FAIL_PENALTY = 100.0
_DIGITS = 12  # distances are rounded so a value on the band's edge is inside it (0.08 vs 0.1)


class Outcome(StrEnum):
    PASS = "PASS"
    NEAR = "NEAR"  # missed, but within the tolerance band
    FAIL = "FAIL"
    MISSING = "MISSING"  # no value, NaN or the wrong type: never a pass
    INFO = "INFO"  # a display column, not a criterion


@dataclass(frozen=True)
class CriterionResult:
    criterion: Criterion
    value: FieldValue
    outcome: Outcome
    distance: float | None = None  # how far from the threshold (numeric ops, on a miss)
    normalised: float | None = None  # distance / tolerance width
    penalty: float = 0.0

    @property
    def gating(self) -> bool:
        return self.criterion.mode.gating

    def threshold(self) -> float | None:
        """The threshold this value missed (the nearer bound for ``between``)."""
        rule, value = self.criterion.rule, self.value
        if rule.op == "between" and isinstance(rule.value, tuple) and _number(value):
            low, high = rule.value
            return float(low if value < low else high)  # type: ignore[operator]
        return float(rule.value) if _number(rule.value) else None  # type: ignore[arg-type]

    def describe(self) -> str:
        """A reason line, e.g. ``spread near miss: 0.09, needs gte 0.1 (by 0.01)``."""
        if self.outcome is Outcome.MISSING:
            return f"no {self.criterion.field}"
        rule = self.criterion.rule
        text = f"{self.value!r}, needs {rule.op} {rule.value!r}"
        if self.outcome is Outcome.NEAR:
            return f"{self.criterion.id} near miss: {text} (by {self.distance:.6g})"
        return f"{self.criterion.id} {self.outcome.value.lower()}: {text}"


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def distance(criterion: Criterion, value: FieldValue) -> float | None:
    """How far ``value`` is from passing a numeric comparison (0 at the threshold), or
    ``None`` for non-numeric ops and values."""
    rule = criterion.rule
    if not _number(value):
        return None
    v = float(value)  # type: ignore[arg-type]
    if rule.op == "between" and isinstance(rule.value, tuple):
        low, high = (float(b) for b in rule.value)
        return round(max(low - v, v - high, 0.0), _DIGITS)
    if not _number(rule.value):
        return None
    t = float(rule.value)  # type: ignore[arg-type]
    if rule.op in ("gt", "gte"):
        return round(max(t - v, 0.0), _DIGITS)
    if rule.op in ("lt", "lte"):
        return round(max(v - t, 0.0), _DIGITS)
    return None


def evaluate_criterion(criterion: Criterion, value: FieldValue) -> CriterionResult:
    value = None if is_missing(value) else value  # NaN is recorded as missing (None)
    truth = evaluate_rule(criterion.rule, value)
    if truth is True:
        return CriterionResult(criterion, value, Outcome.PASS)
    if truth is None:
        penalty = 0.0 if criterion.mode.gating else NEAR_MISS_PENALTY
        return CriterionResult(criterion, value, Outcome.MISSING, penalty=penalty)
    gap = distance(criterion, value)
    if criterion.mode is Mode.HARD:
        return CriterionResult(criterion, value, Outcome.FAIL, gap, penalty=FAIL_PENALTY)
    tolerance = criterion.tolerance
    result = CriterionResult(criterion, value, Outcome.FAIL, gap)
    threshold = result.threshold()
    if tolerance is not None and gap is not None and threshold is not None:
        width = tolerance.width(threshold)
        normalised = round(gap / width, _DIGITS) if width > 0 else float("inf")
        if normalised <= 1.0:
            penalty = NEAR_MISS_PENALTY * normalised
            return CriterionResult(criterion, value, Outcome.NEAR, gap, normalised, penalty)
        result = CriterionResult(criterion, value, Outcome.FAIL, gap, normalised)
    penalty = FAIL_PENALTY if criterion.mode is Mode.SOFT else NEAR_MISS_PENALTY
    return CriterionResult(
        criterion, value, Outcome.FAIL, result.distance, result.normalised, penalty
    )
