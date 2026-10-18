"""A row's decision and score from its gates (ADR 0029, 0071): the criterion results, or with
boolean groups the ungrouped criteria and the top-level groups (a group's verdict combines its
members', ``rules.groups``).

Order: a gating FAIL or a HARD criterion MISSING (reason ``no <field>``) -> REJECT; else a near
miss -> the most severe near-miss ``on_miss`` (EVENT_RISK > LIQUIDITY_RISK > WATCH); else
QUALIFIED. A SOFT criterion MISSING only costs points (ADR 0030) and is listed in the reasons.
The score is 100 minus every penalty, clipped to [0, 100] (never negative; many hard fails tie
at 0 and sort by the tie-break column, then instrument id).
"""

from collections.abc import Sequence

from algotrade.core.model.screen_spec import NEAR_MISS_DECISIONS
from algotrade.strategies.screeners.base import Decision
from algotrade.strategies.screeners.rules.groups import Gate

FULL_SCORE = 100.0
_DIGITS = 9  # rounding keeps scores identical however the penalties were summed


def decide(gates: Sequence[Gate]) -> tuple[Decision, tuple[str, ...]]:
    failed = [g for g in gates if g.verdict.rejects]
    near = [g for g in gates if g.verdict.near]
    soft_missing = [
        g for g in gates if g.verdict.missing and not g.verdict.rejects and not g.verdict.near
    ]
    reasons = tuple(g.describe() for g in (*failed, *near, *soft_missing))
    if failed:
        return Decision.REJECT, reasons
    if near:
        worst = min(NEAR_MISS_DECISIONS.index(g.verdict.on_miss or "") for g in near)
        return Decision(NEAR_MISS_DECISIONS[worst]), reasons
    return Decision.QUALIFIED, reasons


def score(gates: Sequence[Gate]) -> float:
    total = FULL_SCORE - sum(g.verdict.penalty for g in gates)
    return round(min(FULL_SCORE, max(0.0, total)), _DIGITS) + 0.0  # + 0.0: never -0.0
