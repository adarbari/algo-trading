"""One criterion over a column of values at once: the same ``CriterionResult`` per value as
``evaluate_criterion`` gives (bit for bit; the property test in ``tests/unit`` compares them),
for the numeric comparisons (``gt gte lt lte between``) of a column holding only numbers and
missing values. The pass / fail / missing split and the gaps come from numpy; every rounding is
Python's ``round`` (numpy's differs in the last place) and a column of anything else (strings,
booleans, huge integers, ``in``, ``is_null``) goes through the scalar function value by value.

Each result carries its ``verdict`` already (the cached property's own function, so the two
cannot differ), which spares a screen a descriptor call and a recomputation per row."""

import math
from collections.abc import Sequence

import numpy as np

from algotrade.core.model.predicates import FieldValue, is_missing
from algotrade.core.model.screen_spec import Criterion, Mode
from algotrade.strategies.screeners.rules.criteria import (
    FAIL_PENALTY,
    NEAR_MISS_PENALTY,
    CriterionResult,
    Outcome,
    Verdict,
    evaluate_criterion,
    verdict_of,
)

_ORDERED = ("gt", "gte", "lt", "lte", "between")
_EXACT = 2**53  # a float64 holds every integer up to here: beyond it the comparison could differ
_DIGITS = 12  # criteria.py's rounding of distances


def _plain(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _bounds(criterion: Criterion) -> tuple[float, float] | float | None:
    """The threshold(s) when the vector path may compare this criterion exactly, else None."""
    rule = criterion.rule
    if rule.op not in _ORDERED:
        return None
    if rule.op == "between":
        pair = rule.value
        if not (isinstance(pair, tuple) and len(pair) == 2 and all(_plain(b) for b in pair)):
            return None
        if any(abs(b) > _EXACT for b in pair):  # type: ignore[arg-type]
            return None
        return float(pair[0]), float(pair[1])
    if not _plain(rule.value) or abs(rule.value) > _EXACT:  # type: ignore[arg-type]
        return None
    return float(rule.value)  # type: ignore[arg-type]


def _column(values: Sequence[FieldValue]) -> np.ndarray | None:
    """The values as float64 (NaN where missing), or None when one is not a plain number."""
    out = np.empty(len(values), dtype=np.float64)
    for n, v in enumerate(values):
        if v is None:
            out[n] = np.nan
        elif isinstance(v, float):
            out[n] = v
        elif isinstance(v, int) and not isinstance(v, bool) and abs(v) <= _EXACT:
            out[n] = float(v)
        else:
            return None
    return out


def _floored(gap: np.ndarray) -> np.ndarray:
    """``max(g, 0.0)`` as Python takes it: a negative becomes 0.0, a -0.0 stays -0.0
    (``np.maximum`` may turn it into 0.0, and ``repr`` would then differ)."""
    return np.where(gap < 0.0, 0.0, gap)


def _scalar_column(criterion: Criterion, values: Sequence[FieldValue]) -> list[CriterionResult]:
    """The scalar function per value, once per distinct value (a result is immutable and
    depends only on the value: a categorical or boolean column has a handful). Keyed by type
    and sign too, so ``1``, ``1.0``, ``True``, ``0.0`` and ``-0.0`` stay apart; an unhashable
    value is just evaluated."""
    seen: dict[tuple[type, object, float], CriterionResult] = {}
    out: list[CriterionResult] = []
    for v in values:
        key = (
            None
            if is_missing(v)
            else (type(v), v, math.copysign(1.0, v) if isinstance(v, float) else 1.0)
        )
        try:
            found = seen.get(key)  # type: ignore[arg-type]
        except TypeError:
            out.append(evaluate_criterion(criterion, v))
            continue
        if found is None:
            found = seen[key] = evaluate_criterion(criterion, v)  # type: ignore[index]
        out.append(found)
    return out


def _result(
    criterion: Criterion,
    verdicts: dict[tuple[Outcome, float], Verdict],
    value: FieldValue,
    outcome: Outcome,
    distance: float | None = None,
    normalised: float | None = None,
    penalty: float = 0.0,
) -> CriterionResult:
    found = CriterionResult(criterion, value, outcome, distance, normalised, penalty)
    key = (outcome, penalty)
    verdict = verdicts.get(key)
    if verdict is None:
        verdict = verdicts[key] = verdict_of(criterion, outcome, penalty)
    found.__dict__["verdict"] = verdict  # the cached property's slot
    return found


def _split(
    criterion: Criterion, column: np.ndarray, bounds: tuple[float, float] | float
) -> tuple[np.ndarray, np.ndarray]:
    """Which values pass, and each value's gap to passing (meaningful where it does not)."""
    if isinstance(bounds, tuple):
        low, high = bounds
        first, second = low - column, column - high
        return (low <= column) & (column <= high), _floored(np.where(second > first, second, first))
    op = criterion.rule.op
    if op in ("gt", "gte"):
        return (column > bounds if op == "gt" else column >= bounds), _floored(bounds - column)
    return (column < bounds if op == "lt" else column <= bounds), _floored(column - bounds)


def _threshold(bounds: tuple[float, float] | float, value: float) -> float:
    """The threshold a value missed (``between``: the bound it is beyond)."""
    if isinstance(bounds, tuple):
        return bounds[0] if value < bounds[0] else bounds[1]
    return bounds


def _miss(
    criterion: Criterion,
    verdicts: dict[tuple[Outcome, float], Verdict],
    widths: dict[float, float],
    value: FieldValue,
    gap: float,
    threshold: float,
) -> CriterionResult:
    """A SOFT or SCORE value that failed: NEAR within its band, else FAIL."""
    tolerance = criterion.tolerance
    normalised: float | None = None
    if tolerance is not None:
        width = widths.get(threshold)
        if width is None:
            width = widths[threshold] = tolerance.width(threshold)
        normalised = round(gap / width, _DIGITS) if width > 0 else float("inf")
        if normalised <= 1.0:
            near = NEAR_MISS_PENALTY * normalised
            return _result(criterion, verdicts, value, Outcome.NEAR, gap, normalised, near)
    penalty = FAIL_PENALTY if criterion.mode is Mode.SOFT else NEAR_MISS_PENALTY
    return _result(criterion, verdicts, value, Outcome.FAIL, gap, normalised, penalty)


def evaluate_column(criterion: Criterion, values: Sequence[FieldValue]) -> list[CriterionResult]:
    """``[evaluate_criterion(criterion, v) for v in values]``."""
    bounds = _bounds(criterion)
    column = _column(values) if bounds is not None and values else None
    if bounds is None or column is None:
        return _scalar_column(criterion, values)
    missing = np.isnan(column)
    passed, gap = _split(criterion, column, bounds)
    passed &= ~missing
    hard = criterion.mode is Mode.HARD
    missing_penalty = FAIL_PENALTY if hard else NEAR_MISS_PENALTY
    widths: dict[float, float] = {}
    verdicts: dict[tuple[Outcome, float], Verdict] = {}
    out: list[CriterionResult] = []
    for n, value in enumerate(values):
        if passed[n]:
            found = _result(criterion, verdicts, value, Outcome.PASS)
        elif missing[n]:
            found = _result(criterion, verdicts, None, Outcome.MISSING, penalty=missing_penalty)
        else:
            gap_n = round(float(gap[n]), _DIGITS)
            if hard:
                found = _result(
                    criterion, verdicts, value, Outcome.FAIL, gap_n, penalty=FAIL_PENALTY
                )
            else:
                threshold = _threshold(bounds, float(column[n]))
                found = _miss(criterion, verdicts, widths, value, gap_n, threshold)
        out.append(found)
    return out
