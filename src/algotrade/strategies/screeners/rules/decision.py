"""A row's decision and score from its criterion results (ADR 0029).

Order: a gating criterion MISSING -> SKIPPED (reasons ``no <field>``); else a gating FAIL ->
REJECT; else a near miss -> the most severe near-miss ``on_miss`` (EVENT_RISK >
LIQUIDITY_RISK > WATCH); else QUALIFIED. The score is 100 minus every penalty, clipped to
[0, 100] (never negative; many hard fails tie at 0 and sort by the tie-break column, then
instrument id); SKIPPED rows have none.
"""

from collections.abc import Sequence

from algotrade.core.model.screen_spec import NEAR_MISS_DECISIONS
from algotrade.strategies.screeners.base import Decision
from algotrade.strategies.screeners.rules.criteria import CriterionResult, Outcome

FULL_SCORE = 100.0
_DIGITS = 9  # rounding keeps scores identical however the penalties were summed


def decide(results: Sequence[CriterionResult]) -> tuple[Decision, tuple[str, ...]]:
    gating = [r for r in results if r.gating]
    missing = [r for r in gating if r.outcome is Outcome.MISSING]
    if missing:
        return Decision.SKIPPED, tuple(r.describe() for r in missing)
    failed = [r for r in gating if r.outcome is Outcome.FAIL]
    near = [r for r in gating if r.outcome is Outcome.NEAR]
    reasons = tuple(r.describe() for r in (*failed, *near))
    if failed:
        return Decision.REJECT, reasons
    if near:
        worst = min(NEAR_MISS_DECISIONS.index(r.criterion.on_miss) for r in near)
        return Decision(NEAR_MISS_DECISIONS[worst]), reasons
    return Decision.QUALIFIED, ()


def score(decision: Decision, results: Sequence[CriterionResult]) -> float | None:
    if decision is Decision.SKIPPED:
        return None
    total = FULL_SCORE - sum(r.penalty for r in results)
    return round(min(FULL_SCORE, max(0.0, total)), _DIGITS) + 0.0  # + 0.0: never -0.0
