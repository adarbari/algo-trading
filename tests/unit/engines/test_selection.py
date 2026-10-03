import itertools
from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from algotrade.config.strategy.schema import Group, Rule, Selection
from algotrade.core.views.feature_view import FeatureView
from algotrade.engines.selection.evaluate import evaluate_group, evaluate_rule, evaluate_selection

DAY = date(2026, 10, 2)
ROWS = {
    "EQ:A": {"instrument.status": "ACTIVE", "instrument.optionable": True, "rollup.x@v1.adv": 9.0},
    "EQ:B": {"instrument.status": "ACTIVE", "instrument.optionable": False, "rollup.x@v1.adv": 5.0},
    "EQ:C": {"instrument.status": "DELISTED", "instrument.optionable": True},
    "EQ:D": {"instrument.status": "ACTIVE", "rollup.x@v1.adv": 7.0},  # optionable unknown
}
ACTIVE = Rule("instrument.status", "eq", "ACTIVE")
OPTIONABLE = Rule("instrument.optionable", "eq", True)


def sel(*children: Rule | Group, kind: str = "all", **kw: object) -> Selection:
    return Selection("t", Group(kind, children), **kw)  # type: ignore[arg-type]


def test_selection_audit_and_fail_closed() -> None:
    result = evaluate_selection(sel(ACTIVE, OPTIONABLE), FeatureView(DAY, ROWS))
    assert result.instruments == ("EQ:A",)
    assert result.base == 4
    assert result.unknown_excluded == 1  # D: optionable unknown -> excluded, not passed
    status, optionable = result.audit
    assert (status.passed, status.failed, status.unknown, status.remaining) == (3, 1, 0, 3)
    assert (optionable.passed, optionable.failed, optionable.unknown, optionable.remaining) == (
        2,
        1,
        1,
        1,
    )
    assert result.as_dict()["selected"] == 1


def test_any_and_not_groups_have_no_funnel() -> None:
    result = evaluate_selection(sel(ACTIVE, OPTIONABLE, kind="any"), FeatureView(DAY, ROWS))
    assert result.instruments == ("EQ:A", "EQ:B", "EQ:C", "EQ:D")
    assert all(a.remaining is None for a in result.audit)
    negated = sel(Group("not", (OPTIONABLE,)))
    assert evaluate_selection(negated, FeatureView(DAY, ROWS)).instruments == ("EQ:B",)
    nested = sel(Group("any", (OPTIONABLE,)))
    assert evaluate_selection(nested, FeatureView(DAY, ROWS)).audit[0].rule == "<any group>"


def test_top_n_by_order_field() -> None:
    top = sel(ACTIVE, max_instruments=2, order_by="rollup.x@v1.adv")
    result = evaluate_selection(top, FeatureView(DAY, ROWS))
    assert result.instruments == ("EQ:A", "EQ:D")  # adv 9 and 7; B (5) truncated
    assert result.truncated == 1
    assert evaluate_selection(sel(ACTIVE), FeatureView(DAY, {})).empty


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
