"""Boolean groups in the rule engine (ADR 0071): the verdict of ``all`` / ``any`` / ``none``,
negation by operator with tolerance, missing data per mode, the gates the decision reads and
the reason lines naming the deciding member."""

from datetime import date
from typing import Any

import pytest

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.model.predicates import Rule
from algotrade.core.model.screen_spec import Criterion, Mode, Tolerance
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import Outcome, RuleRow, evaluate_screen
from algotrade.strategies.screeners.rules.groups import negate

DAY = date(2026, 10, 2)


def hard(field: str, op: str = "lt", value: Any = 30) -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


def soft(
    field: str, op: str = "lt", value: Any = 30, tol: float = 2, **extra: Any
) -> dict[str, Any]:
    return {**hard(field, op, value), "mode": "soft", "tolerance": tol, **extra}


def score(field: str, op: str = "lt", value: Any = 30) -> dict[str, Any]:
    return {**hard(field, op, value), "mode": "score", "tolerance": 2}


def run(criteria: dict[str, Any], groups: dict[str, Any], **values: Any) -> RuleRow:
    spec = parse_screen_spec("s", {"criteria": criteria, "groups": groups}, "s")
    (row,) = evaluate_screen(spec, FeatureView(DAY, {"EQ:X": values})).rows
    return row


def test_any_takes_the_best_member_a_near_miss_beats_a_hard_fail() -> None:
    criteria = {"a": soft("a"), "b": hard("b")}
    row = run(criteria, {"g": {"any": ["a", "b"]}}, a=31, b=99)
    assert row.decision is Decision.WATCH
    assert row.reasons == ("g near miss via a (31; tolerance 2)",)
    assert row.score == 95.0  # the near miss costs 10 x (1 / 2); the failed b costs nothing
    (gate,) = row.gate_results
    assert gate.decided_by == "a" and gate.outcome is Outcome.NEAR


def test_any_passes_on_one_passing_member_and_costs_nothing() -> None:
    row = run({"a": hard("a"), "b": hard("b")}, {"g": {"any": ["a", "b"]}}, a=99, b=1)
    assert row.decision is Decision.QUALIFIED and row.score == 100.0 and row.reasons == ()
    assert row.gate_results[0].decided_by == "b"


def test_any_with_every_member_failing_rejects_and_names_them_all() -> None:
    criteria = {"rsi_low": hard("rsi"), "near_low": hard("low", "gt", 0.5), "x": hard("x")}
    groups = {"oversold": {"any": ["momentum", "near_low"]}, "momentum": {"all": ["rsi_low", "x"]}}
    row = run(criteria, groups, rsi=41, low=0.12, x=1)
    assert row.decision is Decision.REJECT and row.score == 0.0
    assert row.reasons == ("oversold fail: neither momentum (rsi_low 41) nor near_low (0.12)",)


def test_a_score_member_makes_any_non_rejecting_and_only_costs_points() -> None:
    row = run({"a": hard("a"), "s": score("s")}, {"g": {"any": ["a", "s"]}}, a=99, s=99)
    assert row.decision is Decision.QUALIFIED
    assert row.score == 90.0 and row.reasons == ()  # the score member's full miss, no reason line


def test_all_rejects_on_any_member_sums_penalties_and_takes_the_worst_on_miss() -> None:
    criteria = {
        "a": soft("a", on_miss="LIQUIDITY_RISK"),
        "b": soft("b", on_miss="EVENT_RISK"),
        "c": hard("c"),
        "d": hard("d"),
    }
    groups = {"top": {"any": ["g", "d"]}, "g": {"all": ["a", "b", "c"]}}
    row = run(criteria, groups, a=31, b=31, c=1, d=99)
    assert row.decision is Decision.EVENT_RISK  # the more severe of the two near misses
    assert row.score == 90.0  # 5 + 5 off through the all
    row = run(criteria, groups, a=31, b=31, c=99, d=99)  # c fails: the all rejects, and d too
    assert row.decision is Decision.REJECT


def test_nested_groups_are_a_tree_and_a_gate_beside_ungrouped_criteria() -> None:
    criteria = {"u": hard("u"), "a": hard("a"), "b": hard("b"), "c": hard("c")}
    groups = {"top": {"any": ["inner", "c"]}, "inner": {"all": ["a", "b"]}}
    ok = run(criteria, groups, u=1, a=1, b=1, c=99)
    assert ok.decision is Decision.QUALIFIED
    assert [g.id for g in ok.gate_results] == ["u", "top"]  # funnel order: first criterion
    assert run(criteria, groups, u=1, a=1, b=99, c=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, u=1, a=1, b=99, c=99).decision is Decision.REJECT
    assert run(criteria, groups, u=99, a=1, b=1, c=1).decision is Decision.REJECT  # ungrouped


def test_a_group_sits_at_its_first_criterions_position_and_members_in_criteria_order() -> None:
    criteria = {"a": hard("a"), "b": hard("b"), "c": hard("c"), "d": hard("d")}
    groups = {"g": {"any": ["d", "b"]}}  # listed d first: reported in criteria order
    row = run(criteria, groups, a=1, b=1, c=1, d=1)
    assert [g.id for g in row.gate_results] == ["a", "g", "c"]
    assert [m.id for m in row.gate_results[1].members] == ["b", "d"]
    assert row.gate_results[1].decided_by == "b"  # a tie goes to criteria order
    assert [r.criterion.id for r in row.results] == ["a", "b", "c", "d"]  # flat results as ever


def test_none_is_all_over_the_negated_members() -> None:
    criteria = {"a": hard("a", "gt", 5), "b": hard("b", "gt", 5)}
    groups = {"calm": {"none": ["a", "b"]}}
    assert run(criteria, groups, a=1, b=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, a=1, b=9).decision is Decision.REJECT  # one hit is enough
    assert run(criteria, groups, a=9, b=9).decision is Decision.REJECT


def test_none_negates_a_soft_criterion_keeping_its_tolerance() -> None:
    """ "except RSI < 30" with tolerance 2 is a near miss at RSI 29 (the negation is gte 30)."""
    criteria = {"rsi": soft("rsi", "lt", 30, 2), "ok": hard("ok", "gt", 0)}
    groups = {"not_oversold": {"none": ["rsi"]}}
    near = run(criteria, groups, rsi=29, ok=1)
    assert near.decision is Decision.WATCH
    assert near.reasons == ("not_oversold near miss via rsi (29; tolerance 2)",)
    assert near.gate_results[0].leaf.criterion.rule == Rule("rsi", "gte", 30)
    assert run(criteria, groups, rsi=31, ok=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, rsi=20, ok=1).decision is Decision.REJECT  # beyond the band


def test_none_over_between_is_below_or_above() -> None:
    criteria = {"px": hard("px", "between", [10, 20]), "ok": hard("ok", "gt", 0)}
    groups = {"outside": {"none": ["px"]}}
    assert run(criteria, groups, px=5, ok=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, px=25, ok=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, px=15, ok=1).decision is Decision.REJECT
    assert run(criteria, groups, px=10, ok=1).decision is Decision.REJECT  # bounds are inside
    assert run(criteria, groups, ok=1).decision is Decision.REJECT  # no value never passes


def test_none_over_a_soft_between_is_a_near_miss_on_the_nearer_side() -> None:
    criteria = {"px": soft("px", "between", [10, 20], 3), "ok": hard("ok", "gt", 0)}
    groups = {"outside": {"none": ["px"]}}
    near = run(criteria, groups, px=11, ok=1)  # 1 inside the low bound: lt 10 misses by 1
    assert near.decision is Decision.WATCH
    assert near.gate_results[0].leaf.criterion.rule == Rule("px", "lt", 10)
    assert run(criteria, groups, px=15, ok=1).decision is Decision.REJECT  # 5 from either bound


def test_a_none_group_nested_in_none_double_negates() -> None:
    criteria = {"a": hard("a", "gt", 5), "b": hard("b", "gt", 5), "c": hard("c", "gt", 5)}
    groups = {"outer": {"none": ["inner", "c"]}, "inner": {"none": ["a", "b"]}}
    # outer = not(not(a or b) or c) = (a or b) and not c
    assert run(criteria, groups, a=9, b=1, c=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, a=1, b=1, c=1).decision is Decision.REJECT
    assert run(criteria, groups, a=9, b=1, c=9).decision is Decision.REJECT


def test_none_inside_any_negates_only_its_own_members() -> None:
    criteria = {"a": hard("a", "gt", 5), "b": hard("b", "gt", 5), "c": hard("c", "gt", 5)}
    groups = {"top": {"any": ["a", "g"]}, "g": {"none": ["b", "c"]}}
    assert run(criteria, groups, a=9, b=9, c=9).decision is Decision.QUALIFIED
    assert run(criteria, groups, a=1, b=1, c=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, a=1, b=9, c=1).decision is Decision.REJECT


@pytest.mark.parametrize("mode", ["hard", "soft", "score"])
def test_missing_data_keeps_each_modes_rule_inside_any_and_none(mode: str) -> None:
    make = {"hard": hard, "soft": soft, "score": score}[mode]
    criteria = {"a": make("a"), "b": hard("b")}
    row = run(criteria, {"g": {"any": ["a", "b"]}}, b=99)  # a has no value, b fails
    if mode == "hard":
        assert row.decision is Decision.REJECT  # nothing known passes: never a pass
        assert row.reasons == ("g fail: neither a (no value) nor b (99)",)
    else:  # a soft or score member costs its full 10 and does not reject
        assert row.decision is Decision.QUALIFIED and row.score == 90.0
    gone = run({"a": make("a"), "b": hard("b", "gt", 0)}, {"g": {"none": ["a"]}}, b=1)  # no a
    if mode == "hard":
        assert gone.decision is Decision.REJECT and gone.reasons == ("g: no a",)
    else:
        assert gone.decision is Decision.QUALIFIED and gone.score == 90.0


def test_a_soft_missing_member_is_listed_by_its_group() -> None:
    row = run({"a": soft("a"), "b": hard("b")}, {"g": {"any": ["a", "b"]}}, b=99)
    assert row.reasons == ("g: no a",)


def test_a_hard_any_passes_on_one_known_passing_member_despite_a_missing_one() -> None:
    row = run({"a": hard("a"), "b": hard("b")}, {"g": {"any": ["a", "b"]}}, b=1)
    assert row.decision is Decision.QUALIFIED  # the Kleene result: TRUE or UNKNOWN is TRUE


def test_a_null_check_negates_to_its_pair() -> None:
    criteria = {"gap": {"field": "gap", "op": "is_null"}, "ok": hard("ok", "gt", 0)}
    groups = {"known": {"none": ["gap"]}}
    assert run(criteria, groups, gap=1.0, ok=1).decision is Decision.QUALIFIED
    assert run(criteria, groups, ok=1).decision is Decision.REJECT


def test_a_spec_without_groups_has_no_gates_and_its_results_decide() -> None:
    criteria = {"a": hard("a"), "b": soft("b")}
    spec = parse_screen_spec("s", {"criteria": criteria}, "s")
    (row,) = evaluate_screen(spec, FeatureView(DAY, {"EQ:X": {"a": 1, "b": 31}})).rows
    assert row.gates is None and row.gate_results is row.results


def test_the_memo_gives_the_same_rows_as_a_cold_run() -> None:
    criteria = {"rsi": soft("rsi"), "ok": hard("ok", "gt", 0), "b": hard("b")}
    spec = parse_screen_spec(
        "s",
        {"criteria": criteria, "groups": {"g": {"none": ["rsi"]}, "h": {"any": ["ok", "b"]}}},
        "s",
    )
    view = FeatureView(DAY, {"EQ:A": {"rsi": 29, "ok": 1, "b": 1}, "EQ:B": {"rsi": 50, "ok": 0}})
    memo: dict[Any, dict[str, Any]] = {}
    cold = evaluate_screen(spec, view)
    assert evaluate_screen(spec, view, memo).rows == cold.rows
    assert evaluate_screen(spec, view, memo).rows == cold.rows  # warm


def test_a_near_miss_inside_a_group_is_the_summarys_narrow_miss() -> None:
    criteria = {"a": soft("a"), "b": hard("b")}
    spec = parse_screen_spec("s", {"criteria": criteria, "groups": {"g": {"any": ["a", "b"]}}}, "s")
    result = evaluate_screen(spec, FeatureView(DAY, {"EQ:X": {"a": 31, "b": 99}}))
    (miss,) = result.summary.narrow_misses
    assert (miss.criterion_id, miss.value, miss.threshold, miss.distance) == ("a", 31, 30.0, 1.0)


def test_a_passing_member_of_an_any_is_not_a_narrow_miss() -> None:
    criteria = {"a": soft("a"), "b": hard("b")}
    spec = parse_screen_spec("s", {"criteria": criteria, "groups": {"g": {"any": ["a", "b"]}}}, "s")
    result = evaluate_screen(spec, FeatureView(DAY, {"EQ:X": {"a": 31, "b": 1}}))
    assert result.summary.narrow_misses == ()  # b passes, so the gate passes
    assert result.rows[0].decision is Decision.QUALIFIED


def test_negate_pairs_every_operator() -> None:
    def neg(op: str, value: Any = 3) -> list[tuple[str, Any]]:
        rule = Rule("f", op, value)
        c = Criterion("c", rule, Mode.SOFT, Tolerance(1), "EVENT_RISK")
        out = negate(c)
        assert all(x.mode is Mode.SOFT and x.tolerance == Tolerance(1) for x in out)
        assert all(x.on_miss == "EVENT_RISK" and x.id == "c" for x in out)
        return [(x.rule.op, x.rule.value) for x in out]

    assert neg("lt") == [("gte", 3)] and neg("gte") == [("lt", 3)]
    assert neg("gt") == [("lte", 3)] and neg("lte") == [("gt", 3)]
    assert neg("eq") == [("ne", 3)] and neg("ne") == [("eq", 3)]
    assert neg("in", (1, 2)) == [("not_in", (1, 2))] and neg("not_in", (1,)) == [("in", (1,))]
    assert neg("is_null", None) == [("not_null", None)] and neg("not_null", None) == [
        ("is_null", None)
    ]
    assert neg("between", (1, 2)) == [("lt", 1), ("gt", 2)]
