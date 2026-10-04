"""Evaluate a rule screen over a ``FeatureView``: one ``RuleRow`` per instrument, ranked, plus
the run summary. Pure and deterministic: the same spec and view give the same rows in the
same order (preview and nightly call this one function, ADR 0029).

``memo`` (the preview's warm path): results by criterion (and by the spec's display part:
flags, columns, tie-break) and instrument, valid for one view. Each depends
only on its part of the spec and the instrument's values, so an edit to one criterion
re-evaluates only that one; the rows are the same either way."""

from collections.abc import Hashable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.predicates import FieldValue, evaluate_group, is_missing
from algotrade.core.model.screen_spec import ScreenSpec
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


type _Display = tuple[float | None, tuple[str, ...], tuple[tuple[str, FieldValue], ...]]


def _display(spec: ScreenSpec, row: Mapping[str, FieldValue]) -> _Display:
    """What a row shows besides its criteria: tie-break, flags, columns."""
    return (
        _number(row.get(spec.tie_break)) if spec.tie_break else None,
        tuple(n for n, g in spec.flags if evaluate_group(g, row) is True),
        tuple((name, _known(row.get(f))) for name, f in spec.columns),
    )


def _display_key(spec: ScreenSpec) -> tuple[object, ...]:
    return ("display", spec.flags, spec.columns, spec.tie_break)


def _results(
    spec: ScreenSpec,
    instrument: str,
    row: Mapping[str, FieldValue],
    known: list[dict[str, Any]] | None,
) -> tuple[CriterionResult, ...]:
    if known is None:
        return tuple(evaluate_criterion(c, row.get(c.field)) for c in spec.criteria)
    out = []
    for c, done in zip(spec.criteria, known, strict=False):  # known ends with the display
        found = done.get(instrument)
        if found is None:
            found = done[instrument] = evaluate_criterion(c, row.get(c.field))
        out.append(found)
    return tuple(out)


def _shown(
    spec: ScreenSpec,
    instrument: str,
    row: Mapping[str, FieldValue],
    known: list[dict[str, Any]] | None,
) -> _Display:
    if known is None:
        return _display(spec, row)
    done = known[-1]
    found: _Display | None = done.get(instrument)
    if found is None:
        found = done[instrument] = _display(spec, row)
    return found


def _row(
    spec: ScreenSpec,
    instrument: str,
    row: Mapping[str, FieldValue],
    known: list[dict[str, Any]] | None,
) -> RuleRow:
    """``known``: memo tables, one per criterion then one for the display (or ``None``)."""
    results = _results(spec, instrument, row, known)
    decision, reasons = decide(results)
    tie_break, flags, columns = _shown(spec, instrument, row, known)
    return RuleRow(
        instrument_id=instrument,
        decision=decision,
        score=score(results),
        rank=0,
        reasons=reasons,
        results=results,
        tie_break=tie_break,
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


def _ranked(r: RuleRow, rank: int) -> RuleRow:
    """``r`` with its rank (built directly: ``dataclasses.replace`` costs 3x per row)."""
    return RuleRow(
        r.instrument_id, r.decision, r.score, rank, r.reasons, r.results,
        r.tie_break, r.flags, r.columns,
    )  # fmt: skip


def evaluate_screen(
    spec: ScreenSpec, view: FeatureView, memo: ScreenMemo | None = None
) -> RuleScreenResult:
    """Every instrument of ``view`` once (``view`` rows are keyed by catalogue field)."""
    keys: list[Hashable] = [*spec.criteria, _display_key(spec)]
    known = None if memo is None else [memo.setdefault(k, {}) for k in keys]
    rows = sorted((_row(spec, i, view.row(i), known) for i in view), key=lambda r: _order(spec, r))
    ranked = tuple(_ranked(r, n) for n, r in enumerate(rows, start=1))
    return RuleScreenResult(spec, ranked, summarise(ranked))
