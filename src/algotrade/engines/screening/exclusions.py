"""Names left out of a screen run, with a reason (ADR 0054): the one step that rewrites a row to
``Decision.EXCLUDED``.

The screening engine applies it to a screener's rows, never the screener itself (like the
regime gate, ``gate.py``). Only a row that was NOT processed (UNKNOWN or SKIPPED: the screen
had no usable data for the name) and whose id is in the ``excluded`` map (instrument id ->
reason; the service builds it from the stale chains the chains gate tolerated) becomes
EXCLUDED, with the exclusion reason first and the screener's own reasons after it. A decided
row (a pick, a reject, PAUSED) is never rewritten: a name the screen could decide is decided.
EXCLUDED is never a pick and is out of the coverage denominator.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from algotrade.strategies.screeners.base import Decision, ScreenRow
from algotrade.strategies.screeners.rules import RuleScreenResult


def _excluded(
    decision: Decision, reasons: tuple[str, ...], reason: str | None
) -> tuple[Decision, tuple[str, ...]]:
    if reason is None or decision.processed:
        return decision, reasons
    return Decision.EXCLUDED, (reason, *reasons)


def exclude_rows(rows: Sequence[ScreenRow], excluded: Mapping[str, str]) -> list[ScreenRow]:
    """A screener's rows with its not-processed rows of ``excluded`` names rewritten."""
    if not excluded:
        return list(rows)
    out = []
    for row in rows:
        decision, reasons = _excluded(row.decision, row.reasons, excluded.get(row.instrument_id))
        out.append(replace(row, decision=decision, reasons=reasons))
    return out


def exclude_rule_result(result: RuleScreenResult, excluded: Mapping[str, str]) -> RuleScreenResult:
    """A rule screen's ranked rows through the same rule (ranks kept), its summary recounted."""
    if not excluded:
        return result
    rows = []
    for row in result.rows:
        decision, reasons = _excluded(row.decision, row.reasons, excluded.get(row.instrument_id))
        rows.append(replace(row, decision=decision, reasons=reasons))
    return result.with_rows(rows)
