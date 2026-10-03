"""Type checking: operators and functions get the types they take, labels are compared
with their own categories, and every error points at the offending position."""

import pytest

from algotrade.features.expressions.checker import check_formula
from algotrade.features.expressions.functions import BOOL, DATE, NUM, OPEN_STR, Type
from algotrade.features.expressions.nodes import ExpressionError, Pos
from algotrade.features.expressions.parser import parse_formula

TIER = Type("str", frozenset({"A", "B", "C", "D"}))
TYPES = {"g.x": NUM, "g.y": NUM, "g.ok": BOOL, "g.tier": TIER, "g.name": OPEN_STR, "g.day": DATE}


class Scope:
    def ref_type(self, name: str, pos: Pos) -> Type:
        if name not in TYPES:
            raise ExpressionError("w", pos, f"unknown name {name!r}")
        return TYPES[name]

    def is_group(self, name: str) -> bool:
        return name == "g"


def typed(text: str) -> Type:
    return check_formula(parse_formula(text, "w"), Scope(), "w")


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("g.x + g.y * 2", "num"),
        ("-g.x", "num"),
        ("g.x > 1 and not g.ok", "bool"),
        ("g.tier == 'A' or g.name != 'x'", "bool"),
        ("g.tier <= 'B'", "bool"),
        ("g.day < g.day", "bool"),
        ("if(g.ok, g.x, null)", "num"),
        ("if(g.ok, null, 'HIGH')", "str"),
        ("coalesce(g.x, g.y, 0)", "num"),
        ("max(g.tier, 'B')", "str"),
        ("min(g.x, 1, g.y)", "num"),
        ("abs(g.x) + sqrt(g.y) + log(g.x) + clip(g.x, 0, 1)", "num"),
        ("is_null(g.name)", "bool"),
        ("one_of(g.tier, 'A', 'B')", "bool"),
        ("one_of(g.x, 1, 2)", "bool"),
        ("exists(g)", "bool"),
        ("g.x + null", "num"),
    ],
)
def test_types(text: str, kind: str) -> None:
    assert typed(text).kind == kind


def test_label_categories_flow_through() -> None:
    assert typed("if(g.ok, 'HIGH', 'LOW')") == Type("str", frozenset({"HIGH", "LOW"}))
    assert typed("max(coalesce(g.tier, 'D'), 'B')") == TIER
    assert typed("coalesce(g.name, 'x')") == OPEN_STR
    assert str(TIER) == "str (one of A, B, C, D)" and str(NUM) == "num"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("g.x + 'a'", "col 7: + takes num, not str (one of a)"),
        ("-g.ok", "unary - takes num"),
        ("not g.x", "not takes bool"),
        ("g.x and g.ok", "and takes bool, not num"),
        ("g.x == g.name", "cannot compare num with str"),
        ("g.ok < g.ok", "< orders numbers, strings or dates, not bool"),
        ("g.x == null", "use is_null(x)"),
        ("g.tier == 'E'", "col 11: 'E' is never a value here: one of ['A', 'B', 'C', 'D']"),
        ("'E' != g.tier", "'E' is never a value here"),
        ("if(g.x, 1, 2)", "if (condition) takes bool"),
        ("if(g.ok, 1, 'a')", "if branches must have one type, got num, str (one of a)"),
        ("if(g.ok, null, null)", "if branches are all null"),
        ("max(g.ok, g.ok)", "max takes num or str"),
        ("coalesce(g.x, 'a')", "coalesce must have one type"),
        ("abs(g.name)", "abs takes num"),
        ("one_of(g.tier, 'A', g.name)", "one_of takes literal values"),
        ("one_of(g.tier, 'Z')", "'Z' is never a value here"),
        ("one_of(g.x, 'A')", "one_of: 'A' is not a num"),
        ("one_of(g.ok, true)", "one_of takes num or str"),
        ("exists(g.x)", "exists takes a feature group name"),
        ("exists(h)", "exists takes a feature group name"),
        ("nope(1)", "unknown function 'nope'"),
        ("eval('1')", "unknown function 'eval'"),
        ("abs(1, 2)", "abs takes 1 arguments, got 2"),
        ("coalesce(1)", "coalesce takes at least 2 arguments, got 1"),
        ("g.missing + 1", "col 1: unknown name 'g.missing'"),
    ],
)
def test_errors(text: str, message: str) -> None:
    with pytest.raises(ExpressionError) as info:
        typed(text)
    assert message in str(info.value)
