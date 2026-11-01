"""``resolve_case`` (ADR 0088, design 2.4): the first TRUE case gives its value, all FALSE gives
the default, and a case that is UNKNOWN before a TRUE one gives ``CASE_UNKNOWN``, never the
default (missing data never chooses a branch). Pure and deterministic."""

from algotrade.config.edges.positions.cases import Case, CaseValue
from algotrade.config.strategy.schema import parse_group
from algotrade.engines.selection.cases import CASE_UNKNOWN, resolve_case

HIGH = parse_group({"all": [{"field": "x", "op": "gte", "value": 0.8}]}, "case")
MID = parse_group({"all": [{"field": "x", "op": "gte", "value": 0.5}]}, "case")
TENOR = CaseValue("tenor_days", (Case(HIGH, 30), Case(MID, 38)), 45)


def test_the_first_true_case_gives_its_value() -> None:
    assert resolve_case(TENOR, {"x": 0.9}).value == 30
    assert resolve_case(TENOR, {"x": 0.6}).value == 38


def test_every_case_false_gives_the_default() -> None:
    result = resolve_case(TENOR, {"x": 0.1})
    assert (result.value, result.selectable, result.reason) == (45, True, None)


def test_an_unknown_case_makes_the_name_unselectable_never_the_default() -> None:
    for row in ({}, {"x": None}, {"x": float("nan")}, {"x": "high"}):
        result = resolve_case(TENOR, row)
        assert (result.value, result.reason, result.unknown_at) == (None, CASE_UNKNOWN, 0)
        assert not result.selectable


def test_an_unknown_case_before_a_true_one_is_unknown_and_a_true_one_before_it_wins() -> None:
    other = parse_group({"all": [{"field": "y", "op": "gt", "value": 0}]}, "case")
    cv = CaseValue("tenor_days", (Case(other, 30), Case(MID, 38)), 45)
    assert resolve_case(cv, {"x": 0.9}).reason == CASE_UNKNOWN  # y missing, decided first
    assert resolve_case(cv, {"x": 0.9, "y": 1}).value == 30  # a TRUE case first never reads on
    assert resolve_case(cv, {"x": 0.9, "y": -1}).value == 38


def test_resolution_is_deterministic() -> None:
    row = {"x": 0.7}
    assert [resolve_case(TENOR, row) for _ in range(3)] == [resolve_case(TENOR, row)] * 3


def test_a_label_outside_the_declared_domain_is_unknown_not_a_branch() -> None:
    ne = parse_group({"all": [{"field": "label", "op": "ne", "value": "contango"}]}, "case")
    cv = CaseValue("tenor_days", (Case(ne, 30),), 45)
    domains = {"label": ("contango", "backwardation")}
    assert resolve_case(cv, {"label": "FOO"}, domains).reason == CASE_UNKNOWN
    assert resolve_case(cv, {"label": "backwardation"}, domains).value == 30
    assert resolve_case(cv, {"label": "contango"}, domains).value == 45
