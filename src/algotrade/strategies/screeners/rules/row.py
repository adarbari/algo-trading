"""One instrument's rule-screen result: decision, score, rank, criterion results,
flags and display columns (what ``results/rule_screen*`` store)."""

from dataclasses import dataclass

from algotrade.core.model.predicates import FieldValue
from algotrade.strategies.screeners.base import Decision, ScreenRow
from algotrade.strategies.screeners.rules.criteria import CriterionResult
from algotrade.strategies.screeners.rules.groups import Gate


@dataclass(frozen=True)
class RuleRow:
    instrument_id: str
    decision: Decision
    score: float | None
    rank: int  # 1 = best: score, then the tie-break, then instrument id
    reasons: tuple[str, ...]
    results: tuple[CriterionResult, ...]  # one per criterion, in spec order
    tie_break: float | None = None
    flags: tuple[str, ...] = ()
    columns: tuple[tuple[str, FieldValue], ...] = ()  # (display name, value)
    gates: tuple[Gate, ...] | None = None  # ADR 0071: with groups, what decided; else ``results``

    @property
    def gate_results(self) -> tuple[Gate, ...]:
        """The gates in funnel order: ungrouped criteria and top-level groups (``results``
        themselves when the screen has no groups)."""
        return self.results if self.gates is None else self.gates

    def screen_row(self) -> ScreenRow:
        """This row under the shared screener contract (values keyed by field)."""
        values = {r.criterion.field: r.value for r in self.results}
        return ScreenRow(self.instrument_id, self.decision, self.score, self.reasons, values)

    def only_near_misses(self) -> bool:
        """Missed only within tolerance: every gating miss is NEAR (a narrow miss)."""
        misses = [
            g.verdict
            for g in self.gate_results
            if g.verdict.rejects or g.verdict.near or g.verdict.missing
        ]
        return bool(misses) and all(v.near for v in misses)
