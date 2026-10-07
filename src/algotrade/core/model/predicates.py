"""Three-valued predicates over named fields: ``Rule`` / ``Group`` and their evaluation.

A missing value is UNKNOWN (``None``), never a pass or a fail. UNKNOWN propagates (Kleene
logic): AND with a FALSE child is FALSE, otherwise UNKNOWN beats TRUE; OR with a TRUE child
is TRUE, otherwise UNKNOWN beats FALSE; ``not`` keeps UNKNOWN. A value of the wrong type for
the op, or a float NaN, is UNKNOWN too. Selections (``engines/selection``) and rule screens
(``strategies/screeners/rules``) share this one evaluator.
"""

import math
import operator
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

OPS = frozenset(
    {"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "between", "is_null", "not_null"}
)
NO_VALUE_OPS = frozenset({"is_null", "not_null"})
NUMERIC_OPS = frozenset({"gt", "gte", "lt", "lte", "between"})

type Scalar = str | int | float | bool
type RuleValue = Scalar | tuple[Scalar, ...] | None
type FieldValue = float | int | str | bool | None
type Truth = bool | None  # None == UNKNOWN


@dataclass(frozen=True)
class Rule:
    field: str
    op: str
    value: RuleValue = None

    def describe(self) -> str:
        return f"{self.field} {self.op}" + ("" if self.op in NO_VALUE_OPS else f" {self.value!r}")


@dataclass(frozen=True)
class Group:
    """``all`` (AND), ``any`` (OR) or ``not`` over rules and nested groups."""

    kind: str  # "all" | "any" | "not"
    children: tuple["Rule | Group", ...]

    def rules(self) -> list[Rule]:
        out: list[Rule] = []
        for child in self.children:
            out.extend([child] if isinstance(child, Rule) else child.rules())
        return out


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


def is_missing(value: FieldValue) -> bool:
    """``None`` or a float NaN: the value is not known."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def evaluate_rule(rule: Rule, value: FieldValue) -> Truth:
    if rule.op == "is_null":
        return is_missing(value)
    if rule.op == "not_null":
        return not is_missing(value)
    if is_missing(value):
        return None
    if rule.op in NUMERIC_OPS and isinstance(value, bool):
        return None  # a boolean is not a number here
    try:
        return bool(_OPS[rule.op](value, rule.value))
    except TypeError:  # data of the wrong type for the rule: not knowable
        return None


def passing(rule: Rule, values: Iterable[FieldValue]) -> list[FieldValue]:
    """The ``values`` that pass ``rule``; a missing, NaN or wrong-typed value never does (the
    population counts of the field guide's criteria, ADR 0038)."""
    return [v for v in values if evaluate_rule(rule, v) is True]


def evaluate_group(group: Group, row: Mapping[str, FieldValue]) -> Truth:
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
