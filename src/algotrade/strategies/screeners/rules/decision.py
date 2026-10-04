"""A row's decision and score from its criterion results (ADR 0029).

Order: a gating FAIL or a HARD criterion MISSING (reason ``no <field>``) -> REJECT; else a near
miss -> the most severe near-miss ``on_miss`` (EVENT_RISK > LIQUIDITY_RISK > WATCH); else
QUALIFIED. A SOFT criterion MISSING only costs points (ADR 0030) and is listed in the reasons.
The score is 100 minus every penalty, clipped to [0, 100] (never negative; many hard fails tie
at 0 and sort by the tie-break column, then instrument id).
"""

from collections.abc import Sequence

from algotrade.core.model.screen_spec import NEAR_MISS_DECISIONS, Mode
from algotrade.strategies.screeners.base import Decision
from algotrade.strategies.screeners.rules.criteria import CriterionResult, Outcome

FULL_SCORE = 100.0
_DIGITS = 9  # rounding keeps scores identical however the penalties were summed


def decide(results: Sequence[CriterionResult]) -> tuple[Decision, tuple[str, ...]]:
    gating = [r for r in results if r.gating]
    failed = [
        r
        for r in gating
        if r.outcome is Outcome.FAIL
        or (r.outcome is Outcome.MISSING and r.criterion.mode is Mode.HARD)
    ]
    near = [r for r in gating if r.outcome is Outcome.NEAR]
    soft_missing = [r for r in gating if r.outcome is Outcome.MISSING and r not in failed]
    reasons = tuple(r.describe() for r in (*failed, *near, *soft_missing))
    if failed:
        return Decision.REJECT, reasons
    if near:
        worst = min(NEAR_MISS_DECISIONS.index(r.criterion.on_miss) for r in near)
        return Decision(NEAR_MISS_DECISIONS[worst]), reasons
    return Decision.QUALIFIED, reasons


def score(results: Sequence[CriterionResult]) -> float:
    total = FULL_SCORE - sum(r.penalty for r in results)
    return round(min(FULL_SCORE, max(0.0, total)), _DIGITS) + 0.0  # + 0.0: never -0.0
