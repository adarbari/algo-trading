"""Groups from the joins of a draft's parts (ADR 0071, "Describe it"): each phrasing's reading
(precedence is decided per phrasing; the golden cases pin the same ones end to end), the scope
parts that are no operand, the drafts that stay flat, and the shape ``prune_groups`` keeps."""

from algotrade.services.drafting.contract.groups import group_parts, prune_groups
from algotrade.services.drafting.parts.model import Part

SCOPE = {"field": "instrument.security_type", "op": "in", "value": ["COMMON_STOCK"]}
CRITERIA = {c: {"field": f"feature.{c}", "op": "gt", "value": 1} for c in "abcde"} | {
    "stocks": SCOPE,
    "active": {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
}


def part(
    pid: str,
    *criteria: str,
    join: str | None = None,
    words: str = "",
    kind: str = "applied",
    formulas: tuple[str, ...] = (),
    origin: str = "words",
) -> Part:
    return Part(
        pid,
        pid,
        0,
        0,
        None,
        "server",
        kind,
        origin,
        criteria,
        formulas=formulas,
        join=join,
        join_words=words or (join or ""),
    )


def groups(*parts: Part) -> dict[str, dict[str, list[str]]]:
    return group_parts(parts, CRITERIA).groups


def test_no_or_and_no_exclusion_is_no_group() -> None:
    assert groups(part("p1", "a"), part("p2", "b", join="and"), part("p3", "c")) == {}


def test_a_or_b_is_an_any() -> None:
    assert groups(part("p1", "a"), part("p2", "b", join="or")) == {"any_1": {"any": ["a", "b"]}}
    three = groups(part("p1", "a"), part("p2", "b", join="or"), part("p3", "c", join="or"))
    assert three == {"any_1": {"any": ["a", "b", "c"]}}


def test_and_binds_tighter_than_or() -> None:
    both = groups(part("p1", "a"), part("p2", "b", join="or"), part("p3", "c", join="and"))
    assert both == {"any_1": {"any": ["a", "all_1"]}, "all_1": {"all": ["b", "c"]}}
    first = groups(part("p1", "a"), part("p2", "b", join="and"), part("p3", "c", join="or"))
    assert first == {"any_1": {"any": ["all_1", "c"]}, "all_1": {"all": ["a", "b"]}}


def test_a_part_with_two_criteria_goes_together_in_its_alternative() -> None:
    got = groups(part("p1", "a", "b"), part("p2", "c", join="or"))
    assert got == {"any_1": {"any": ["all_1", "c"]}, "all_1": {"all": ["a", "b"]}}


def test_an_exclusion_is_a_none_and_an_or_or_and_extends_it() -> None:
    assert groups(part("p1", "a"), part("p2", "b", join="and_not")) == {"none_1": {"none": ["b"]}}
    either = groups(part("p1", "a"), part("p2", "b", join="and_not"), part("p3", "c", join="or"))
    assert either == {"none_1": {"none": ["b", "c"]}}
    plain_and = groups(
        part("p1", "a"), part("p2", "b", join="and_not"), part("p3", "c", join="and", words="and")
    )
    assert plain_and == {"none_1": {"none": ["b", "c"]}}


def test_but_after_an_exclusion_ends_it() -> None:
    got = groups(
        part("p1", "a"), part("p2", "b", join="and_not", words="except"),
        part("p3", "c", join="and", words="but"), part("p4", "d", join="or"),
    )  # fmt: skip
    assert got == {
        "none_1": {"none": ["b"]},
        "any_1": {"any": ["all_1", "d"]},
        "all_1": {"all": ["a", "c"]},
    }  # (A and C) or D, and not B: the "but" is an and, not part of the exclusion


def test_a_or_b_except_c_is_a_group_and_a_gate() -> None:
    got = groups(part("p1", "a"), part("p2", "b", join="or"), part("p3", "c", join="and_not"))
    assert got == {"none_1": {"none": ["c"]}, "any_1": {"any": ["a", "b"]}}


def test_a_part_with_no_connector_starts_a_new_condition() -> None:
    """ "A, ideally B or C": the or never reaches across the break: A and (B or C)."""
    got = groups(part("p1", "a"), part("p2", "b"), part("p3", "c", join="or"))
    assert got == {"any_1": {"any": ["b", "c"]}}
    after = groups(part("p1", "a"), part("p2", "b", join="or"), part("p3", "c"))
    assert after == {"any_1": {"any": ["a", "b"]}}


def test_a_part_that_names_the_kind_of_instrument_is_no_operand() -> None:
    got = groups(
        part("p1", "active", "stocks"), part("p2", "a", join="and"), part("p3", "b", join="or")
    )
    assert got == {"any_1": {"any": ["a", "b"]}}
    one = groups(part("p1", "active", "stocks", "a"), part("p2", "b", join="or"))
    assert one == {"any_1": {"any": ["a", "b"]}}  # its scope criteria stay top-level


def test_an_exclusion_of_a_kind_of_instrument_keeps_its_criteria() -> None:
    got = groups(part("p1", "a"), part("p2", "stocks", join="and_not"))
    assert got == {"none_1": {"none": ["stocks"]}}


def test_a_formula_part_next_to_an_or_keeps_the_draft_flat_and_is_blocked() -> None:
    parts = (
        part("p1", "a"),
        part("p2", join="or", kind="formula", formulas=("f",)),
    )
    got = group_parts(parts, CRITERIA)
    assert got.groups == {} and got.blocked == ("p2",)


def test_a_formula_with_no_or_around_it_changes_nothing() -> None:
    parts = (part("p1", "a"), part("p2", kind="formula", formulas=("f",), join="and"))
    assert group_parts(parts, CRITERIA) == group_parts((), CRITERIA)


def test_a_missing_or_not_understood_part_in_an_or_keeps_the_draft_flat_without_a_block() -> None:
    gap = part("g1", join="or", kind="not_understood", origin="gap")
    got = group_parts((part("p1", "a"), gap), CRITERIA)
    assert got.groups == {} and got.blocked == ()
    missing = part("p2", join="or", kind="not_available")
    assert group_parts((part("p1", "a"), missing), CRITERIA).groups == {}


def test_group_ids_never_take_a_criterion_id() -> None:
    criteria = {**CRITERIA, "any_1": {"field": "feature.z", "op": "gt", "value": 1}}
    got = group_parts((part("p1", "a"), part("p2", "b", join="or")), criteria)
    assert list(got.groups) == ["any_2"]


def test_without_criteria_every_named_id_is_an_operand() -> None:
    got = group_parts((part("p1", "x"), part("p2", "y", join="or")))
    assert got.groups == {"any_1": {"any": ["x", "y"]}}


def test_prune_drops_gone_members_and_groups_that_fall_under_their_size() -> None:
    table = {"g": {"any": ["a", "gone"]}, "h": {"none": ["gone"]}, "k": {"any": ["a", "b", "gone"]}}
    assert prune_groups(table, CRITERIA) == {"k": {"any": ["a", "b"]}}
    nested = {"outer": {"any": ["inner", "a"]}, "inner": {"all": ["b", "gone"]}}
    assert prune_groups(nested, CRITERIA) == {}  # inner dissolves, outer falls to one member
    assert prune_groups(None, CRITERIA) == {} and prune_groups({"g": "no"}, CRITERIA) == {}
