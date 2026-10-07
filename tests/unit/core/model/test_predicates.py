"""The three-valued predicate shared by selections and rule screens."""

import itertools
import math

from hypothesis import given
from hypothesis import strategies as st

from algotrade.core.model.predicates import (
    Group,
    Rule,
    evaluate_group,
    evaluate_rule,
    is_missing,
    passing,
)


def test_rule_ops() -> None:
    assert evaluate_rule(Rule("f", "in", ("a", "b")), "a")
    assert evaluate_rule(Rule("f", "not_in", ("a",)), "b")
    assert evaluate_rule(Rule("f", "between", (1, 3)), 3)
    assert evaluate_rule(Rule("f", "gt", 1), 2)
    assert evaluate_rule(Rule("f", "gte", 2), 2)
    assert evaluate_rule(Rule("f", "lt", 1), 0)
    assert evaluate_rule(Rule("f", "lte", 1), 1)
    assert evaluate_rule(Rule("f", "ne", "x"), "y")
    assert evaluate_rule(Rule("f", "is_null"), None) is True
    assert evaluate_rule(Rule("f", "not_null"), None) is False
    assert evaluate_rule(Rule("f", "gt", 1), None) is None
    assert evaluate_rule(Rule("f", "gt", 1), "text") is None  # wrong data type -> unknown


truth = st.sampled_from([True, False, None])


def as_rule(i: int, value: bool | None) -> tuple[Rule, dict[str, object]]:
    field = f"f{i}"
    return Rule(field, "eq", True), ({} if value is None else {field: value})


@given(st.lists(truth, min_size=1, max_size=5))
def test_rule_order_never_changes_the_result(values: list[bool | None]) -> None:
    pairs = [as_rule(i, v) for i, v in enumerate(values)]
    row: dict[str, object] = {}
    for _, part in pairs:
        row.update(part)
    rules = [r for r, _ in pairs]
    for kind in ("all", "any"):
        results = {
            evaluate_group(Group(kind, tuple(p)), row) for p in itertools.permutations(rules)
        }
        assert len(results) == 1


@given(st.lists(truth, min_size=1, max_size=5))
def test_not_is_the_complement_when_known(values: list[bool | None]) -> None:
    rules, row = [], {}
    for i, v in enumerate(values):
        rule, part = as_rule(i, v)
        rules.append(rule)
        row.update(part)
    group = Group("all", tuple(rules))
    inner = evaluate_group(group, row)
    outer = evaluate_group(Group("not", (group,)), row)
    assert outer is (None if inner is None else not inner)


def test_nan_and_wrong_types_are_unknown_never_a_pass() -> None:
    assert is_missing(math.nan) and is_missing(None) and not is_missing(0.0)
    assert evaluate_rule(Rule("f", "gt", 1), math.nan) is None
    assert evaluate_rule(Rule("f", "lt", 1), math.nan) is None
    assert evaluate_rule(Rule("f", "is_null"), math.nan) is True
    assert evaluate_rule(Rule("f", "not_null"), math.nan) is False
    assert evaluate_rule(Rule("f", "gt", 0), True) is None  # a boolean is not a number
    assert evaluate_rule(Rule("f", "eq", True), True) is True


def test_any_group_is_true_with_one_true_child_even_if_others_are_unknown() -> None:
    rules = (Rule("a", "eq", 1), Rule("b", "eq", 1))
    assert evaluate_group(Group("any", rules), {"a": 1}) is True
    assert evaluate_group(Group("any", rules), {"a": 2}) is None
    assert evaluate_group(Group("all", rules), {"a": 2}) is False


def test_passing_keeps_only_the_values_that_pass() -> None:
    values = [0.05, 0.2, None, math.nan, "x", 0.1]
    assert passing(Rule("f", "lte", 0.1), values) == [0.05, 0.1]
    assert passing(Rule("f", "between", (0.1, 0.3)), values) == [0.2, 0.1]
    assert len(passing(Rule("f", "is_null"), values)) == 2  # None and NaN are missing
    assert passing(Rule("f", "gte", 1), []) == []
