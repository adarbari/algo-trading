"""The golden scorer: a part with its criterion passes within tolerance; a missing, wrong or
extra criterion, or a field invented for a part that must stay empty, fails."""

import json
from pathlib import Path

from algotrade.services.drafting.golden import GoldenCase, load_cases, mark_recorded, score

A = {
    "span": "p",
    "bucket": "A",
    "fields": ["f.x", "f.y"],
    "op": ["gt", "gte"],
    "value": 100,
    "tolerance": 0.1,
}
C = {"span": "q", "bucket": "C", "fields": []}


def case(*parts: dict) -> GoldenCase:
    return GoldenCase("c", "s", "train", parts, frozenset({"scope"}))


def crit(field: str, op: str = "gt", value: object = 100) -> dict:
    return {"field": field, "op": op, "value": value}


def test_a_matching_criterion_within_tolerance_passes_with_scope_tolerated() -> None:
    kept = {"a": crit("f.y", "gte", 95), "s": crit("scope", "eq", "ACTIVE")}
    assert score(case(A), kept).passed


def test_missing_wrong_and_extra_are_named() -> None:
    assert score(case(A), {}).missing == ("p",)
    assert score(case(A), {"a": crit("f.x", "lt")}).wrong == ("p",)
    assert score(case(A), {"a": crit("f.x", value=150)}).wrong == ("p",)
    assert score(case(A), {"a": crit("f.x"), "b": crit("f.z")}).extra == ("f.z",)


def test_a_c_part_wants_nothing_and_invented_fields_count_as_extra() -> None:
    assert score(case(C), {}).passed
    assert score(case(C), {"a": crit("f.x")}).extra == ("f.x",)
    assert score(case(C), {}, ("made.up",)).extra == ("made.up",)


B = {"span": "b", "bucket": "B", "fields": [], "expr": "a.x / a.y"}
MISSING = {"span": "m", "bucket": "C", "fields": [], "key": "support_history"}
ASK = {"span": "l", "bucket": "ask", "fields": [], "term": "liquid"}


def test_buckets_are_scored_only_when_given_and_only_for_parts_that_expect_something() -> None:
    wanted = case(B, MISSING, ASK, C)
    assert score(wanted, {}).passed  # an answer of the old shape: unchecked
    assert score(case(C), {}, formulas=[], missing_keys=[], terms=[]).passed  # nothing expected


def test_a_formula_matches_by_fingerprint_not_by_text() -> None:
    wanted = case(B)
    assert score(wanted, {}, formulas=[("a.y", None)]).missing == ("b",)
    assert score(wanted, {}, formulas=[("a.x / a.y", None)]).passed
    assert score(wanted, {}, formulas=[("(a.x)/(a.y)", None)]).passed  # spacing and brackets
    assert score(wanted, {}, formulas=[("a.x / a.y", None), ("a.z", None)]).extra == (
        "formula a.z",
    )
    assert score(case(C), {}, formulas=[("a.z", None)]).extra == (
        "formula a.z",
    )  # none was expected
    assert score(wanted, {}, formulas=[("a.x /", None)]).missing == (
        "b",
    )  # does not parse: no match


def test_a_missing_key_and_an_unresolved_term_are_looked_for_by_name() -> None:
    wanted = case(MISSING, ASK)
    assert score(wanted, {}, missing_keys=[], terms=[]).missing == ("m", "l")
    assert score(wanted, {}, missing_keys=["support_history"], terms=["Liquid"]).passed
    assert score(wanted, {}, missing_keys=["other"], terms=["liquid"]).missing == ("m",)


def test_a_formula_with_the_right_expr_and_the_wrong_criterion_is_wrong() -> None:
    wanted = case({**B, "op": "gte", "value": 0.95, "tolerance": 0.02})
    right = {"op": "gte", "value": 0.95}
    assert score(wanted, {}, formulas=[("a.x / a.y", right)]).passed
    assert score(wanted, {}, formulas=[("a.x / a.y", {"op": "gte", "value": 0.9})]).wrong == ("b",)
    assert score(wanted, {}, formulas=[("a.x / a.y", {"op": "lt", "value": 0.95})]).wrong == ("b",)
    assert score(wanted, {}, formulas=[("a.x / a.y", None)]).wrong == ("b",)


def test_two_parts_with_the_same_formula_each_need_one() -> None:
    twin = {**B, "span": "b2"}
    wanted = case(B, twin)
    assert score(wanted, {}, formulas=[("a.x / a.y", None)]).missing == ("b2",)
    assert score(wanted, {}, formulas=[("a.x / a.y", None), ("a.x/a.y", None)]).passed


def test_missing_and_unresolved_items_nothing_asked_for_are_extra() -> None:
    wanted = case(MISSING, ASK)
    got = score(
        wanted, {}, missing_keys=["support_history", "new:other"], terms=["liquid", "recent"]
    )
    assert got.extra == ("missing new:other", "unresolved recent")
    assert score(case(B), {}, missing_keys=["k"], terms=["t"]).extra == (
        "missing k",
        "unresolved t",
    )


def test_a_c_part_without_a_key_tolerates_any_missing_item() -> None:
    assert score(case(C), {}, missing_keys=["new:whatever"]).passed


def test_a_new_slug_never_passes_for_the_curated_key() -> None:
    wanted = case(MISSING)
    assert score(wanted, {}, missing_keys=["new:support_history"]).missing == ("m",)


def test_a_curated_case_loads_the_criteria_in_force_and_its_recording_state(
    tmp_path: Path,
) -> None:
    force = {"criteria": {"c1": {"field": "f.a", "op": "gt", "value": 1}}, "rank": None}
    raw = {"id": "c", "sentence": "two", "sentences": ["one", "two"], "split": "train",
           "criteria_in_force": [{"criteria": {}}, force], "recorded": False,
           "curated": "2026-10-11", "expect": {"parts": []}}  # fmt: skip
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "c.json").write_text(json.dumps(raw))
    (loaded,) = load_cases(tmp_path)
    assert loaded.sentences == ("one", "two") and loaded.current == force
    assert (loaded.recorded, loaded.curated) == (False, "2026-10-11")
    mark_recorded(tmp_path, "c")
    assert "recorded" not in json.loads((tmp_path / "cases" / "c.json").read_text())
    assert load_cases(tmp_path)[0].recorded is True
    mark_recorded(tmp_path, "missing")  # no case file: nothing to do


def test_an_old_case_has_one_sentence_and_nothing_in_force() -> None:
    old = case(A)
    assert old.sentences == () and old.current is None and old.recorded


def test_an_equivalent_op_passes_at_the_same_value_only() -> None:
    part = {**A, "op": "gt", "value": 100, "tolerance": 0, "equivalent_ops": ["gte"]}
    assert score(case(part), {"a": crit("f.x", "gte", 100)}).passed
    assert score(case(part), {"a": crit("f.x", "gte", 101)}).wrong == ("p",)  # not the value
    assert score(case(part), {"a": crit("f.x", "lt", 100)}).wrong == ("p",)  # not an equivalent
    assert score(case({**part, "equivalent_ops": []}), {"a": crit("f.x", "gte")}).wrong == ("p",)


ETF_FLAG = {"span": "ETFs", "bucket": "A", "fields": ["instrument.is_etf"], "op": "eq",
            "value": True}  # fmt: skip
ETF_TYPE = {"span": "ETFs", "bucket": "A", "fields": ["instrument.security_type"], "op": "in",
            "value": ["ETF"]}  # fmt: skip


def test_an_etf_flag_and_the_etf_security_type_read_the_same_either_way() -> None:
    as_type = {"a": crit("instrument.security_type", "in", ["ETF"])}
    as_flag = {"a": crit("instrument.is_etf", "eq", True)}
    assert score(case(ETF_FLAG), as_type).passed and score(case(ETF_FLAG), as_flag).passed
    assert score(case(ETF_TYPE), as_flag).passed and score(case(ETF_TYPE), as_type).passed


def test_the_equivalence_is_only_for_the_named_readings() -> None:
    stock = {"a": crit("instrument.security_type", "in", ["COMMON_STOCK"])}
    assert score(case(ETF_FLAG), stock).missing == ("ETFs",)
    assert score(case(ETF_FLAG), {"a": crit("instrument.is_etf", "eq", False)}).wrong == ("ETFs",)
