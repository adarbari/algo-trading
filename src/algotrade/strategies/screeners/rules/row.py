"""One instrument's rule-screen result: decision, score, rank, criterion results, tier,
class, flags and display columns (what ``results/rule_screen*`` store)."""

from dataclasses import dataclass

from algotrade.core.model.predicates import FieldValue
from algotrade.strategies.screeners.base import Decision, ScreenRow
from algotrade.strategies.screeners.rules.criteria import CriterionResult, Outcome


@dataclass(frozen=True)
class RuleRow:
    instrument_id: str
    decision: Decision
    score: float | None
    rank: int  # 1 = best: score, then the tie-break, then instrument id
    reasons: tuple[str, ...]
    results: tuple[CriterionResult, ...]  # one per criterion, in spec order
    tie_break: float | None = None
    tier: str | None = None
    klass: str | None = None
    flags: tuple[str, ...] = ()
    columns: tuple[tuple[str, FieldValue], ...] = ()  # (display name, value)

    def screen_row(self) -> ScreenRow:
        """This row under the shared screener contract (values keyed by field)."""
        values = {r.criterion.field: r.value for r in self.results}
        return ScreenRow(self.instrument_id, self.decision, self.score, self.reasons, values)

    def only_near_misses(self) -> bool:
        """Missed only within tolerance: every gating miss is NEAR (a narrow miss)."""
        misses = [r for r in self.results if r.gating and r.outcome is not Outcome.PASS]
        return bool(misses) and all(r.outcome is Outcome.NEAR for r in misses)
