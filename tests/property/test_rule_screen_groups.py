"""Boolean groups of hard criteria are the Kleene formula they spell, and evaluation is
deterministic (ADR 0071): for any tree and any data, the gate passes exactly when
``evaluate_group`` of the equivalent ``all / any / not`` is TRUE; a missing value never passes."""

import math
from datetime import date
from typing import Any

from hypothesis import assume, given
from hypothesis import strategies as st

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.model.predicates import Group, Rule, evaluate_group
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen

DAY = date(2026, 10, 2)
OPS: list[tuple[str, Any]] = [
    ("gt", 0.0), ("lte", 0.5), ("between", [-1.0, 1.0]), ("in", [1.0, 2.0]), ("ne", 0.0),
    ("not_in", [1.0]), ("lt", -1.0), ("gte", 1.0), ("eq", 1.0),
]  # fmt: skip
LEAVES = 6

# A tree over leaf slots: ("leaf",) or (kind, [children]); slots are numbered in reading order.
tree = st.recursive(
    st.just(("leaf",)),
    lambda inner: st.one_of(  # the sizes the spec accepts: all / any 2+, none 1+
        st.tuples(st.sampled_from(["all", "any"]), st.lists(inner, min_size=2, max_size=3)),
        st.tuples(st.just("none"), st.lists(inner, min_size=1, max_size=3)),
    ),
    max_leaves=LEAVES,
)
value = st.one_of(
    st.none(), st.floats(-3, 3), st.sampled_from([0.0, 1.0, 2.0, -1.0, 0.5, math.nan, "x", True])
)


class Build:
    """The spec's tables and the equivalent predicate for one drawn tree."""

    def __init__(self, ops: list[tuple[str, Any]]) -> None:
        self.ops, self.criteria, self.groups = ops, {}, {}
        self.depth = 0

    def node(self, shape: tuple[Any, ...], level: int = 0) -> tuple[str, Rule | Group]:
        if shape[0] == "leaf":
            n = len(self.criteria)
            op, bound = self.ops[n % len(self.ops)]
            self.criteria[f"c{n}"] = {"field": f"f{n}", "op": op, "value": bound}
            return f"c{n}", Rule(f"f{n}", op, tuple(bound) if isinstance(bound, list) else bound)
        kind, children = shape
        built = [self.node(c, level + 1) for c in children]
        self.depth = max(self.depth, level + 1)
        gid = f"g{len(self.groups)}"
        self.groups[gid] = {kind: [name for name, _ in built]}
        rules = tuple(p for _, p in built)
        formula = Group("not", (Group("any", rules),)) if kind == "none" else Group(kind, rules)
        return gid, formula


@given(tree, st.lists(st.sampled_from(OPS), min_size=LEAVES, max_size=LEAVES), st.data())
def test_a_group_of_hard_criteria_is_the_kleene_formula(
    shape: tuple[Any, ...], ops: list[tuple[str, Any]], data: st.DataObject
) -> None:
    assume(shape[0] != "leaf")
    build = Build(ops)
    root = build.node(shape)
    assume(build.depth <= 4 and root[0] in build.groups)
    top = build.groups[root[0]]
    assume("all" not in top)  # a top-level all is refused: it is the screen itself
    spec = parse_screen_spec("p", {"criteria": build.criteria, "groups": build.groups}, "p")
    row = {f"f{n}": data.draw(value) for n in range(len(build.criteria))}
    row = {k: v for k, v in row.items() if v is not None}
    (got,) = evaluate_screen(spec, FeatureView(DAY, {"EQ:A": row})).rows
    truth = evaluate_group(root[1], row)  # type: ignore[arg-type]
    assert (got.decision is Decision.QUALIFIED) == (truth is True)
    assert (got.decision is Decision.REJECT) == (truth is not True)  # hard: never a near miss
    # a gate in the funnel's single step; the flat results still list every criterion
    assert len(got.results) == len(build.criteria)


@given(tree, st.lists(st.sampled_from(OPS), min_size=LEAVES, max_size=LEAVES), st.data())
def test_group_evaluation_is_deterministic(
    shape: tuple[Any, ...], ops: list[tuple[str, Any]], data: st.DataObject
) -> None:
    assume(shape[0] != "leaf")
    build = Build(ops)
    root = build.node(shape)
    assume(build.depth <= 4 and root[0] in build.groups)
    assume("all" not in build.groups[root[0]])
    spec = parse_screen_spec("p", {"criteria": build.criteria, "groups": build.groups}, "p")
    rows = {
        f"EQ:{i}": {f"f{n}": data.draw(st.floats(-3, 3)) for n in range(len(build.criteria))}
        for i in range(4)
    }
    first = evaluate_screen(spec, FeatureView(DAY, rows))
    second = evaluate_screen(spec, FeatureView(DAY, dict(reversed(list(rows.items())))))
    assert first.rows == second.rows
    assert first.summary == second.summary
