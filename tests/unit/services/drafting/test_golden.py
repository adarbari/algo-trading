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
