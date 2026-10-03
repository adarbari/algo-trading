"""Evaluate a selection with three-valued logic and a per-rule audit.

A missing value is UNKNOWN, never a pass or a fail. UNKNOWN propagates (Kleene logic): AND
with a FALSE child is FALSE, otherwise UNKNOWN beats TRUE; ``not`` keeps UNKNOWN. An
instrument is selected only when its result is TRUE, so missing data excludes it (fail
closed) and is counted separately in the audit.
"""

import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.strategy.schema import Group, Rule, Selection
from algotrade.core.views.feature_view import FeatureValue, FeatureView

type Truth = bool | None  # None == UNKNOWN

_OPS: Mapping[str, Callable[[Any, Any], Any]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "in": lambda value, expected: value in expected,
    "not_in": lambda value, expected: value not in expected,
    "between": lambda value, expected: expected[0] <= value <= expected[1],
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def evaluate_rule(rule: Rule, value: FeatureValue) -> Truth:
    if rule.op == "is_null":
        return value is None
    if rule.op == "not_null":
        return value is not None
    if value is None:
        return None
    try:
        return bool(_OPS[rule.op](value, rule.value))
    except TypeError:  # data of the wrong type for the rule: not knowable
        return None


def evaluate_group(group: Group, row: Mapping[str, FeatureValue]) -> Truth:
    results = [
        evaluate_group(c, row) if isinstance(c, Group) else evaluate_rule(c, row.get(c.field))
        for c in group.children
    ]
    if group.kind == "not":
        return None if results[0] is None else not results[0]
    if group.kind == "all":
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True
    if any(r is True for r in results):
        return True
    return None if any(r is None for r in results) else False


@dataclass(frozen=True)
class RuleAudit:
    rule: str
    passed: int  # evaluated independently over the whole base
    failed: int
    unknown: int
    remaining: int | None = None  # funnel: still selected after this top-level rule (AND only)


@dataclass(frozen=True)
class SelectionResult:
    selection: str
    base: int
    instruments: tuple[str, ...]
    unknown_excluded: int
    truncated: int
    audit: tuple[RuleAudit, ...]
    missing_tables: tuple[str, ...] = ()  # rollups with no data for the session (UNKNOWN)
    pre_snapshot: bool = False  # the reference snapshot is after the session (survivorship)

    @property
    def empty(self) -> bool:
        return not self.instruments

    def as_dict(self) -> dict[str, object]:
        return {
            "selection": self.selection,
            "base": self.base,
            "selected": len(self.instruments),
            "unknown_excluded": self.unknown_excluded,
            "truncated": self.truncated,
            "rules": [a.__dict__ for a in self.audit],
            "missing_tables": list(self.missing_tables),
        }


def _audit(selection: Selection, view: FeatureView) -> tuple[RuleAudit, ...]:
    top = selection.where
    funnel = top.kind == "all"
    remaining = list(view)
    audits: list[RuleAudit] = []
    for child in top.children:

        def truth(i: str, child: Rule | Group = child) -> Truth:
            row = view.row(i)
            if isinstance(child, Group):
                return evaluate_group(child, row)
            return evaluate_rule(child, row.get(child.field))

        results = [truth(i) for i in view]
        if funnel:
            remaining = [i for i in remaining if truth(i) is True]
        label = child.describe() if isinstance(child, Rule) else f"<{child.kind} group>"
        audits.append(
            RuleAudit(
                label,
                results.count(True),
                results.count(False),
                results.count(None),
                len(remaining) if funnel else None,
            )
        )
    return tuple(audits)


def evaluate_selection(selection: Selection, view: FeatureView) -> SelectionResult:
    """``view`` rows are keyed by field name (``instrument.x``, ``rollup.y@v1.z``)."""
    truths = {i: evaluate_group(selection.where, view.row(i)) for i in view}
    chosen = [i for i, t in truths.items() if t is True]
    truncated = 0
    if selection.max_instruments is not None and selection.order_by is not None:
        key = selection.order_by

        def rank(i: str) -> tuple[bool, float, str]:
            value = view.get(i, key)
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            return (not numeric, -float(value) if numeric else 0.0, i)  # type: ignore[arg-type]

        chosen.sort(key=rank)
        truncated = max(0, len(chosen) - selection.max_instruments)
        chosen = chosen[: selection.max_instruments]
    return SelectionResult(
        selection=selection.name,
        base=len(truths),
        instruments=tuple(sorted(chosen)),
        unknown_excluded=sum(1 for t in truths.values() if t is None),
        truncated=truncated,
        audit=_audit(selection, view),
    )
