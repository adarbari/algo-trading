"""Boolean groups of criteria (ADR 0071): the verdict of a group from its members' verdicts, the
tree walk, and the nested ``GroupResult`` the decision reads.

A criterion's ``Verdict`` is (rejects, penalty, on_miss). ``all`` rejects if any member rejects,
sums the penalties and takes the most severe ``on_miss``; ``any`` takes the verdict of its best
member (not rejecting first, then the lowest penalty, then criteria order); ``none`` is ``all``
over its members negated, pushed down to the criteria (De Morgan), a criterion being negated by
its operator and keeping its mode, tolerance and ``on_miss``. Missing data keeps its mode's rule.
The screen is the implicit ``all`` of its gates (the ungrouped criteria and the top-level
groups), placed at their first criterion's position, so a spec with no groups changes nothing.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from algotrade.core.model.screen_spec import (
    NEAR_MISS_DECISIONS,
    Criterion,
    CriterionGroup,
    ScreenSpec,
)
from algotrade.strategies.screeners.rules.criteria import CriterionResult, Outcome, Verdict

# Each operator and the one that holds exactly when it does not (``between`` has two sides).
_NEGATED = {
    "lt": "gte", "gte": "lt", "gt": "lte", "lte": "gt", "eq": "ne", "ne": "eq",
    "in": "not_in", "not_in": "in", "is_null": "not_null", "not_null": "is_null",
}  # fmt: skip

type Gate = CriterionResult | GroupResult
type Lookup = Callable[[Criterion], CriterionResult]  # the row's result of a criterion


def negate(criterion: Criterion) -> tuple[Criterion, ...]:
    """The criteria whose best result is the negation of ``criterion``'s (one, or two for
    ``between``: below the low bound or above the high one), mode, tolerance and on_miss kept."""
    rule = criterion.rule
    if rule.op == "between" and isinstance(rule.value, tuple):
        low, high = rule.value
        return (
            replace(criterion, rule=replace(rule, op="lt", value=low)),
            replace(criterion, rule=replace(rule, op="gt", value=high)),
        )
    return (replace(criterion, rule=replace(rule, op=_NEGATED[rule.op])),)


def _shown(result: CriterionResult) -> str:
    return "no value" if result.outcome is Outcome.MISSING else repr(result.value)


def _tolerance(result: CriterionResult) -> str:
    tolerance = result.criterion.tolerance
    if tolerance is None:
        return ""
    return f"; tolerance {tolerance.amount:g}" + (" x threshold" if tolerance.relative else "")


def _part(member: Gate) -> str:
    """``near_low (0.12)`` for a criterion, ``momentum_dip (rsi_low 41)`` for a group."""
    if isinstance(member, CriterionResult):
        return f"{member.id} ({_shown(member)})"
    leaf = member.leaf
    return f"{member.id} ({leaf.id} {_shown(leaf)})"


@dataclass(frozen=True)
class GroupResult:
    """One group for one row. ``members`` are in criteria order; under ``none`` (and a negated
    group) they hold the negated criteria's results. ``effective`` is ``all`` or ``any`` after
    De Morgan; ``decided_by`` the member whose verdict decided the group's (``None``: none did)."""

    group: CriterionGroup
    verdict: Verdict
    decided_by: str | None
    members: tuple[Gate, ...]
    effective: str = "all"
    written: "GroupResult | None" = None  # under a negation: this group as written (storage)

    @property
    def as_written(self) -> "GroupResult":
        """The group as the config states it, whatever negation its parents push down: what
        a stored group row and a trace show (the gating tree keeps the negated one)."""
        return self if self.written is None else self.written

    @property
    def id(self) -> str:
        return self.group.id

    @property
    def gating(self) -> bool:
        return any(m.gating for m in self.members)

    @property
    def outcome(self) -> Outcome:
        """The gate's outcome as the funnel counts it."""
        if self.verdict.near:
            return Outcome.NEAR
        if self.verdict.rejects:
            return Outcome.MISSING if self.leaf.outcome is Outcome.MISSING else Outcome.FAIL
        return Outcome.MISSING if self.verdict.missing else Outcome.PASS

    @property
    def leaf(self) -> CriterionResult:
        """The criterion result that decided this group (the first member's when none did)."""
        by_id = {m.id: m for m in self.members}
        return by_id.get(self.decided_by or "", self.members[0]).leaf

    def describe(self) -> str:
        """A reason line naming the deciding member (ADR 0071)."""
        if self.verdict.rejects and self.effective == "any":
            return f"{self.id} fail: neither " + " nor ".join(_part(m) for m in self.members)
        if self.verdict.near:
            leaf = self.leaf
            return f"{self.id} near miss via {leaf.id} ({leaf.value!r}{_tolerance(leaf)})"
        decider = {m.id: m for m in self.members}.get(self.decided_by or "", self.members[0])
        if (
            self.group.kind == "none"
            and self.verdict.rejects
            and isinstance(decider, CriterionResult)
            and decider.outcome is Outcome.FAIL  # the excluded condition held
        ):
            return f"{self.id} fail: {decider.id} matched ({decider.value!r})"
        return f"{self.id}: {decider.describe()}"


def _all(members: Sequence[Gate]) -> tuple[Verdict, str | None]:
    verdicts = [m.verdict for m in members]
    rejecting = next((m for m in members if m.verdict.rejects), None)
    near = [m for m in members if m.verdict.on_miss is not None]
    on_miss = (
        NEAR_MISS_DECISIONS[min(NEAR_MISS_DECISIONS.index(m.verdict.on_miss or "") for m in near)]
        if near
        else None
    )
    missing = next((m for m in members if m.verdict.missing), None)
    verdict = Verdict(
        rejecting is not None, sum(v.penalty for v in verdicts), on_miss, missing is not None
    )
    if rejecting is not None:
        return verdict, rejecting.id
    if near:
        worst = [m for m in near if m.verdict.on_miss == on_miss]
        return verdict, worst[0].id
    return verdict, missing.id if missing is not None else None


def _best(members: Sequence[Gate]) -> Gate:
    """Not rejecting before rejecting, then the lowest penalty, a pass before a near miss (a
    strict threshold gives a near miss at 0 penalty), a value before none, then criteria order."""
    return min(
        members,
        key=lambda m: (m.verdict.rejects, m.verdict.penalty, m.verdict.near, m.verdict.missing),
    )  # min is stable


def _any(members: Sequence[Gate]) -> tuple[Verdict, str | None]:
    best = _best(members)
    return best.verdict, best.id


@dataclass(frozen=True)
class Plan:
    """The shape of a spec's gates: criteria and groups by id, each group's members in criteria
    order, and the gates (ungrouped criteria and top-level groups) in funnel order."""

    criteria: Mapping[str, Criterion]
    groups: Mapping[str, CriterionGroup]
    members: Mapping[str, tuple[str, ...]]
    gates: tuple[str, ...]

    @property
    def grouped(self) -> bool:
        return bool(self.groups)


def plan(spec: ScreenSpec) -> Plan:
    criteria = {c.id: c for c in spec.criteria}
    groups = {g.id: g for g in spec.groups}
    first = {c.id: i for i, c in enumerate(spec.criteria)}

    def position(gid: str) -> int:
        if gid not in first:
            first[gid] = min(position(m) for m in groups[gid].members)
        return first[gid]

    members = {gid: tuple(sorted(g.members, key=position)) for gid, g in groups.items()}
    inside = {m for ms in members.values() for m in ms}
    gates = sorted((i for i in (*criteria, *groups) if i not in inside), key=position)
    return Plan(criteria, groups, members, tuple(gates))


@dataclass(frozen=True)
class GateSlot:
    """A gate as the funnel and the readers list it: a criterion, or a group (``mode`` "group",
    ``field`` its kind)."""

    id: str
    field: str
    mode: str
    gating: bool


def gate_slots(spec: ScreenSpec) -> tuple[GateSlot, ...]:
    p = plan(spec)

    def gating(gid: str) -> bool:
        if gid in p.criteria:
            return p.criteria[gid].mode.gating
        return any(gating(m) for m in p.members[gid])

    return tuple(
        GateSlot(c.id, c.field, c.mode.value, c.mode.gating)
        if (c := p.criteria.get(gid))
        else GateSlot(gid, p.groups[gid].kind, "group", gating(gid))
        for gid in p.gates
    )


def _leaf(criterion: Criterion, negated: bool, lookup: Lookup) -> CriterionResult:
    if not negated:
        return lookup(criterion)
    # ``between`` negated is "below or above": the better side is its result
    best = _best([lookup(c) for c in negate(criterion)])
    assert isinstance(best, CriterionResult)
    return best


def _node(p: Plan, gid: str, negated: bool, lookup: Lookup) -> Gate:
    if gid in p.criteria:
        return _leaf(p.criteria[gid], negated, lookup)
    group = p.groups[gid]
    below = negated != (group.kind == "none")  # De Morgan: none negates its members
    members = tuple(_node(p, m, below, lookup) for m in p.members[gid])
    effective = "any" if (group.kind == "any") != negated else "all"
    verdict, decided_by = (_any if effective == "any" else _all)(members)
    written = _node(p, gid, False, lookup) if negated else None
    assert written is None or isinstance(written, GroupResult)
    return GroupResult(group, verdict, decided_by, members, effective, written)


def evaluate_gates(p: Plan, lookup: Lookup) -> tuple[Gate, ...]:
    """The row's gates, in funnel order: ``lookup`` gives a criterion's result."""
    return tuple(_node(p, gid, False, lookup) for gid in p.gates)
