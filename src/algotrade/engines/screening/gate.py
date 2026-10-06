"""The regime gate (ADR 0049): a screener's picks held back in the market regimes it pauses in.

The screening engine applies it to a screener's rows, never the screener itself: when
``[regime]`` is enabled, a QUALIFIED or WATCH row becomes ``Decision.PAUSED`` with the reason
first (``regime=STRESS: vrp_scanner pauses in STRESS``) when the session's label is one the
screener pauses in, and with ``regime unknown`` when the label is unknown (null, or not a
known label) and the screener is gated (its ``pause_in`` is not empty): fail closed, never
read as CALM. A screener that pauses in no label is never paused. Other decisions are left as
they are. PAUSED is processed, so coverage is unchanged. Every row of the run carries the
session's ``regime`` and its ``size_multiplier``: the label's multiplier, 0 in a label the
screener pauses in, and ``unknown_multiplier`` when the label is unknown.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from algotrade.core.views.feature_view import FeatureValue
from algotrade.strategies.screeners.base import Decision, ScreenRow
from algotrade.strategies.screeners.rules import RuleScreenResult

GATED = frozenset({Decision.QUALIFIED, Decision.WATCH})
UNKNOWN = "regime unknown"


@dataclass(frozen=True)
class RegimeGate:
    """One run's gate: the session's label and the screener's rule."""

    screener: str  # the config id, named in the reason
    label: FeatureValue  # the session's label as stored (None: no value)
    multipliers: Mapping[str, float]  # known labels -> size multiplier
    pause_in: frozenset[str] = frozenset()
    unknown_multiplier: float = 0.0

    @property
    def regime(self) -> str | None:
        """The label as a result column records it (``None`` when there is none)."""
        return None if self.label is None else str(self.label)

    @property
    def known(self) -> bool:
        return isinstance(self.label, str) and self.label in self.multipliers

    @property
    def reason(self) -> str | None:
        """Why the gate pauses this run's picks (``None``: it lets them through)."""
        if not self.known:
            return UNKNOWN if self.pause_in else None
        if self.label in self.pause_in:
            return f"regime={self.label}: {self.screener} pauses in {self.label}"
        return None

    @property
    def size_multiplier(self) -> float:
        if not self.known:
            return self.unknown_multiplier
        if self.label in self.pause_in:
            return 0.0
        return float(self.multipliers[str(self.label)])

    def decision(
        self, decision: Decision, reasons: tuple[str, ...]
    ) -> tuple[Decision, tuple[str, ...]]:
        """A row's decision and reasons through the gate."""
        reason = self.reason
        if reason is None or decision not in GATED:
            return decision, reasons
        return Decision.PAUSED, (reason, *reasons)


def gate_rows(rows: Sequence[ScreenRow], gate: RegimeGate | None) -> list[ScreenRow]:
    """A screener's rows through ``gate`` (``None``: the gate is off)."""
    if gate is None or gate.reason is None:
        return list(rows)
    out = []
    for row in rows:
        decision, reasons = gate.decision(row.decision, row.reasons)
        out.append(replace(row, decision=decision, reasons=reasons))
    return out


def gate_rule_result(result: RuleScreenResult, gate: RegimeGate | None) -> RuleScreenResult:
    """A rule screen's ranked rows through ``gate`` (ranks kept), its summary recounted."""
    if gate is None or gate.reason is None:
        return result
    rows = []
    for row in result.rows:
        decision, reasons = gate.decision(row.decision, row.reasons)
        rows.append(replace(row, decision=decision, reasons=reasons))
    return result.with_rows(rows)
