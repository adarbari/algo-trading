"""Evaluate a rule screen over a ``FeatureView``: one ``RuleRow`` per instrument, ranked, plus
the run summary. Pure and deterministic: the same spec and view give the same rows in the
same order (preview and nightly call this one function, ADR 0029).

``memo`` (the preview's warm path): results by criterion (and by the spec's display part:
tiers, flags, classify, columns, tie-break) and instrument, valid for one view. Each depends
only on its part of the spec and the instrument's values, so an edit to one criterion
re-evaluates only that one; the rows are the same either way."""

from collections.abc import Callable, Hashable, Mapping, MutableMapping
from dataclasses import dataclass, replace
from typing import Any

from algotrade.core.model.predicates import FieldValue, Group, evaluate_group, is_missing
from algotrade.core.model.screen_spec import Criterion, ScreenSpec
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners.rules.criteria import CriterionResult, evaluate_criterion
from algotrade.strategies.screeners.rules.decision import decide, score
from algotrade.strategies.screeners.rules.row import RuleRow
from algotrade.strategies.screeners.rules.summary import RunSummary, summarise

# Per view: results by criterion (or the display part of a spec), then by instrument.
type ScreenMemo = MutableMapping[Hashable, dict[str, Any]]


@dataclass(frozen=True)
class RuleScreenResult:
    spec: ScreenSpec
    rows: tuple[RuleRow, ...]  # ranked
    summary: RunSummary


def _number(value: FieldValue) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or is_missing(value):
        return None
    return float(value)


def _known(value: FieldValue) -> FieldValue:
    return None if is_missing(value) else value


def _first_true(groups: tuple[tuple[str, Group], ...], row: Mapping[str, FieldValue]) -> str | None:
    return next((n for n, g in groups if evaluate_group(g, row) is True), None)


type _Display = tuple[
    float | None, str | None, str | None, tuple[str, ...], tuple[tuple[str, FieldValue], ...]
]


def _display(spec: ScreenSpec, row: Mapping[str, FieldValue]) -> _Display:
    """What a row shows besides its criteria: tie-break, tier, class, flags, columns."""
    klass = row.get(spec.classify) if spec.classify else None
    return (
        _number(row.get(spec.tie_break)) if spec.tie_break else None,
        _first_true(spec.tiers, row),
        klass if isinstance(klass, str) else None,
        tuple(n for n, g in spec.flags if evaluate_group(g, row) is True),
        tuple((name, _known(row.get(f))) for name, f in spec.columns),
    )


def _display_key(spec: ScreenSpec) -> tuple[object, ...]:
    return ("display", spec.tiers, spec.flags, spec.classify, spec.columns, spec.tie_break)


def _memoised[T](done: dict[str, Any] | None, instrument: str, compute: Callable[[], T]) -> T:
    if done is None:
        return compute()
    found: T | None = done.get(instrument)
    if found is None:
        found = done[instrument] = compute()
    return found


def _criterion(c: Criterion, row: Mapping[str, FieldValue]) -> Callable[[], CriterionResult]:
    return lambda: evaluate_criterion(c, row.get(c.field))


def _row(
    spec: ScreenSpec,
    instrument: str,
    row: Mapping[str, FieldValue],
    known: list[dict[str, Any]] | None,
) -> RuleRow:
    """``known``: memo tables, one per criterion then one for the display (or ``None``)."""
    results = tuple(
        _memoised(known[n] if known else None, instrument, _criterion(c, row))
        for n, c in enumerate(spec.criteria)
    )
    decision, reasons = decide(results)
    tie_break, tier, klass, flags, columns = _memoised(
        known[-1] if known else None, instrument, lambda: _display(spec, row)
    )
    return RuleRow(
        instrument_id=instrument,
        decision=decision,
        score=score(decision, results),
        rank=0,
        reasons=reasons,
        results=results,
        tie_break=tie_break,
        tier=tier,
        klass=klass,
        flags=flags,
        columns=columns,
    )


def _order(spec: ScreenSpec, row: RuleRow) -> tuple[bool, float, bool, float, str]:
    sign = -1.0 if spec.tie_break_descending else 1.0
    return (
        row.score is None,
        -(row.score or 0.0),
        row.tie_break is None,
        sign * (row.tie_break or 0.0),
        row.instrument_id,
    )


def evaluate_screen(
    spec: ScreenSpec, view: FeatureView, memo: ScreenMemo | None = None
) -> RuleScreenResult:
    """Every instrument of ``view`` once (``view`` rows are keyed by catalogue field)."""
    keys: list[Hashable] = [*spec.criteria, _display_key(spec)]
    known = None if memo is None else [memo.setdefault(k, {}) for k in keys]
    rows = sorted((_row(spec, i, view.row(i), known) for i in view), key=lambda r: _order(spec, r))
    ranked = tuple(replace(r, rank=n) for n, r in enumerate(rows, start=1))
    return RuleScreenResult(spec, ranked, summarise(ranked))
