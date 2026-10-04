"""The run summary every rule-screen run reports, preview and nightly (ADR 0029): how many
passed, the count of each decision and the narrow misses (rows that missed only within
tolerance: which criterion, the value, the threshold and by how much)."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from algotrade.core.model.predicates import FieldValue
from algotrade.strategies.screeners.base import Decision
from algotrade.strategies.screeners.rules.criteria import Outcome
from algotrade.strategies.screeners.rules.row import RuleRow


@dataclass(frozen=True)
class NarrowMiss:
    instrument_id: str
    criterion_id: str
    field: str
    value: FieldValue
    threshold: float | None
    distance: float | None
    normalised: float | None  # distance / tolerance, 0..1

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RunSummary:
    rows: int
    passed: int  # QUALIFIED
    decisions: tuple[tuple[str, int], ...]  # sorted by decision
    narrow_misses: tuple[NarrowMiss, ...]  # in rank order, then criterion order

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "passed": self.passed,
            "decisions": dict(self.decisions),
            "narrow_misses": [m.as_dict() for m in self.narrow_misses],
        }


def summarise(rows: Sequence[RuleRow]) -> RunSummary:
    decisions = Counter(r.decision.value for r in rows)
    narrow = tuple(
        NarrowMiss(
            row.instrument_id,
            result.criterion.id,
            result.criterion.field,
            result.value,
            result.threshold(),
            result.distance,
            result.normalised,
        )
        for row in rows
        if row.only_near_misses()
        for result in row.results
        if result.gating and result.outcome is Outcome.NEAR
    )
    return RunSummary(
        rows=len(rows),
        passed=decisions.get(Decision.QUALIFIED.value, 0),
        decisions=tuple(sorted(decisions.items())),
        narrow_misses=narrow,
    )
