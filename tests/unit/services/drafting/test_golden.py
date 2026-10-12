"""The golden scorer: a part with its criterion passes within tolerance; a missing, wrong or
extra criterion, or a field invented for a part that must stay empty, fails."""

from algotrade.services.drafting.golden import GoldenCase, score

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
