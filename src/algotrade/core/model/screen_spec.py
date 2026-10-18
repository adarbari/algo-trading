"""The rule-screen spec (ADR 0029, 0030, 0071): criteria, boolean groups of them, tolerance
bands, flags, columns and the tie-break, as frozen values. Parsed and validated by
``config.strategy.screen_spec``; evaluated by ``strategies.screeners.rules``."""

from dataclasses import dataclass
from enum import StrEnum

from algotrade.core.model.predicates import Group, Rule


class Mode(StrEnum):
    HARD = "hard"  # strict: FALSE -> REJECT
    SOFT = "soft"  # tolerance band: a near miss is WATCH at best, beyond it REJECT
    SCORE = "score"  # never gates: a miss only lowers the score

    @property
    def gating(self) -> bool:
        return self is not Mode.SCORE


MAX_NOTES = 10
MAX_NOTE_LENGTH = 200

# Decisions a near miss may give (most severe first); WATCH is the default.
NEAR_MISS_DECISIONS = ("EVENT_RISK", "LIQUIDITY_RISK", "WATCH")


@dataclass(frozen=True)
class Tolerance:
    """How far a value may miss a threshold and still be a near miss: ``amount`` in the
    field's unit, or ``amount`` x |threshold| when ``relative``."""

    amount: float
    relative: bool = False

    def width(self, threshold: float) -> float:
        return self.amount * abs(threshold) if self.relative else self.amount


@dataclass(frozen=True)
class Criterion:
    id: str
    rule: Rule
    mode: Mode = Mode.HARD
    tolerance: Tolerance | None = None
    on_miss: str = "WATCH"  # SOFT near miss only; one of NEAR_MISS_DECISIONS

    @property
    def field(self) -> str:
        return self.rule.field


GROUP_KINDS = ("all", "any", "none")  # AND, OR, NOT-ANY of the members


@dataclass(frozen=True)
class CriterionGroup:
    """A boolean group of criteria (ADR 0071) by reference: ``members`` are criterion or
    group ids, in the file's order. A group has no mode of its own; its members keep theirs."""

    id: str
    kind: str  # one of GROUP_KINDS
    members: tuple[str, ...]
    enabled: bool = True


@dataclass(frozen=True)
class ScreenSpec:
    """One rule screen. ``criteria`` keep the file's order (it is the funnel order)."""

    id: str
    criteria: tuple[Criterion, ...]
    version: int | None = None
    flags: tuple[tuple[str, Group], ...] = ()
    columns: tuple[tuple[str, str], ...] = ()  # display name -> field
    tie_break: str | None = None  # field sorting rows with equal scores
    tie_break_descending: bool = True
    notes: tuple[str, ...] = ()  # what the screen does not cover (data, shown as "Not covered")
    groups: tuple[CriterionGroup, ...] = ()  # ADR 0071; a group with no parent is a gate

    def fields(self) -> tuple[str, ...]:
        """Every field the screen reads, sorted (what the view must hold)."""
        names = {c.field for c in self.criteria}
        for _, group in self.flags:
            names.update(r.field for r in group.rules())
        names.update(f for _, f in self.columns)
        names.update(f for f in (self.tie_break,) if f)
        return tuple(sorted(names))
