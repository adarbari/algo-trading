"""Evaluate a rule screen over a ``FeatureView``: one ``RuleRow`` per instrument, ranked, plus
the run summary. Pure and deterministic: the same spec and view give the same rows in the
same order (preview and nightly call this one function, ADR 0029)."""

from collections.abc import Mapping
from dataclasses import dataclass, replace

from algotrade.core.model.predicates import FieldValue, Group, evaluate_group, is_missing
from algotrade.core.model.screen_spec import ScreenSpec
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners.rules.criteria import evaluate_criterion
from algotrade.strategies.screeners.rules.decision import decide, score
from algotrade.strategies.screeners.rules.row import RuleRow
from algotrade.strategies.screeners.rules.summary import RunSummary, summarise


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


def _row(spec: ScreenSpec, instrument: str, row: Mapping[str, FieldValue]) -> RuleRow:
    results = tuple(evaluate_criterion(c, row.get(c.field)) for c in spec.criteria)
    decision, reasons = decide(results)
    klass = row.get(spec.classify) if spec.classify else None
    return RuleRow(
        instrument_id=instrument,
        decision=decision,
        score=score(decision, results),
        rank=0,
        reasons=reasons,
        results=results,
        tie_break=_number(row.get(spec.tie_break)) if spec.tie_break else None,
        tier=_first_true(spec.tiers, row),
        klass=klass if isinstance(klass, str) else None,
        flags=tuple(n for n, g in spec.flags if evaluate_group(g, row) is True),
        columns=tuple((name, _known(row.get(f))) for name, f in spec.columns),
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


def evaluate_screen(spec: ScreenSpec, view: FeatureView) -> RuleScreenResult:
    """Every instrument of ``view`` once (``view`` rows are keyed by catalogue field)."""
    rows = sorted((_row(spec, i, view.row(i)) for i in view), key=lambda r: _order(spec, r))
    ranked = tuple(replace(r, rank=n) for n, r in enumerate(rows, start=1))
    return RuleScreenResult(spec, ranked, summarise(ranked))
