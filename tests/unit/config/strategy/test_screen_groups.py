"""Boolean groups of a rule screen (ADR 0071): parsing and every validation rule."""

from typing import Any

import pytest

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.screen_spec import CriterionGroup


def crit(field: str, **extra: Any) -> dict[str, Any]:
    return {"field": field, "op": "gte", "value": 1, **extra}


def doc(groups: dict[str, Any], **criteria: Any) -> dict[str, Any]:
    base = {name: crit(name) for name in ("a", "b", "c", "d")}
    return {"criteria": {**base, **criteria}, "groups": groups}


def parse(groups: dict[str, Any], **criteria: Any) -> Any:
    return parse_screen_spec("s", doc(groups, **criteria), "s")


def refused(groups: dict[str, Any], message: str, **criteria: Any) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse(groups, **criteria)


def test_a_tree_by_reference_parses_in_the_files_order() -> None:
    spec = parse(
        {
            "oversold": {"any": ["dip", "c"]},
            "dip": {"all": ["a", "b"]},
            "calm": {"none": ["d"]},
        }
    )
    assert spec.groups == (
        CriterionGroup("oversold", "any", ("dip", "c")),
        CriterionGroup("dip", "all", ("a", "b")),
        CriterionGroup("calm", "none", ("d",)),
    )
    assert [c.id for c in spec.criteria] == ["a", "b", "c", "d"]  # criteria stay flat
    assert spec.fields() == ("a", "b", "c", "d")


def test_no_groups_is_the_empty_default() -> None:
    assert parse({}).groups == ()
    assert parse_screen_spec("s", {"criteria": {"a": crit("a")}}, "s").groups == ()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({}, "exactly one of 'all', 'any' or 'none'"),
        ({"any": ["a", "b"], "none": ["c"]}, "exactly one of"),
        ({"any": ["a", "b"], "extra": 1}, "unknown keys"),
        ({"any": "a"}, "list of distinct"),
        ({"any": ["a", "a"]}, "list of distinct"),
        ({"any": ["a", 3]}, "list of distinct"),
        ({"any": ["a", "b"], "enabled": "yes"}, "true or false"),
        ({"any": ["a"]}, "needs at least 2"),
        ({"none": []}, "needs at least 1"),
        ({"any": ["a", "ghost"]}, "unknown criterion or group 'ghost'"),
        ({"any": ["g", "a"]}, "cannot contain itself"),
        ({"all": ["a", "b"]}, "top-level 'all'"),
    ],
)
def test_a_malformed_group_is_refused_with_its_path(body: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message) as error:
        parse({"g": body})
    assert "s.groups.g" in str(error.value)


def test_a_nested_all_needs_two_members() -> None:
    refused({"top": {"any": ["g", "b"]}, "g": {"all": ["a"]}}, "needs at least 2")


def test_a_group_table_is_a_table() -> None:
    with pytest.raises(ConfigurationError, match="expected a table"):
        parse_screen_spec("s", {"criteria": {"a": crit("a")}, "groups": ["x"]}, "s")
    refused({"g": ["a", "b"]}, "expected a table")


def test_group_ids_pass_validate_id_and_share_the_criteria_key_space() -> None:
    refused({"Bad Id": {"any": ["a", "b"]}}, "invalid group id")
    refused({"a": {"any": ["b", "c"]}}, "shares one key space")
    refused({"score": {"any": ["a", "b"]}}, "shares one key space")
    refused({"x": {"any": ["b", "c"]}}, "shares one key space", x={**crit("x"), "enabled": False})


def test_every_criterion_and_group_has_at_most_one_parent() -> None:
    refused(
        {"g1": {"any": ["a", "b"]}, "g2": {"any": ["a", "c"]}}, "'a' is already a member of 'g1'"
    )
    refused(
        {"top": {"any": ["g1", "g2"]}, "g1": {"any": ["a", "b"]}, "g2": {"none": ["g1"]}},
        "'g1' is already a member",
    )


def test_groups_are_acyclic() -> None:
    refused({"g1": {"any": ["g2", "a"]}, "g2": {"any": ["g1", "b"]}}, "form a cycle")
    refused(
        {"g1": {"any": ["g2", "g3"]}, "g2": {"none": ["g3"]}, "g3": {"none": ["g2"]}}, "already"
    )


def chain(depth: int) -> dict[str, Any]:
    """``depth`` nested groups of criteria a..: top any, each below it an any with a sibling."""
    groups: dict[str, Any] = {}
    for level in range(depth):
        below = [f"g{level + 1}"] if level + 1 < depth else ["a"]
        groups[f"g{level}"] = {"any": [*below, f"s{level}"]}
    return groups


def test_nesting_is_at_most_four_deep() -> None:
    siblings = {f"s{n}": crit(f"s{n}") for n in range(6)}
    assert len(parse(chain(4), **siblings).groups) == 4
    refused(chain(5), "at most 4 deep \\(this one has 5\\)", **siblings)


def test_a_group_has_at_most_twelve_members() -> None:
    many = {f"m{n}": crit(f"m{n}") for n in range(13)}
    assert len(parse({"g": {"any": list(many)[:12]}}, **many).groups[0].members) == 12
    refused({"g": {"any": list(many)}}, "at most 12 members", **many)


def test_a_disabled_member_drops_out_before_the_size_rules() -> None:
    off = {"enabled": False}
    spec = parse({"g": {"any": ["a", "b", "c"]}}, c={**crit("c"), **off})
    assert spec.groups == (CriterionGroup("g", "any", ("a", "b")),)
    refused({"g": {"any": ["a", "b"]}}, "needs at least 2 enabled members", b={**crit("b"), **off})
    spec = parse({"g": {"none": ["a", "b"]}}, b={**crit("b"), **off})  # one is enough for none
    assert spec.groups[0].members == ("a",)


def test_a_disabled_group_leaves_its_parent_and_takes_its_members_out() -> None:
    groups = {
        "top": {"any": ["inner", "c", "d"]},
        "inner": {"all": ["a", "b"], "enabled": False},
    }
    spec = parse(groups)
    assert spec.groups == (CriterionGroup("top", "any", ("c", "d")),)
    assert [c.id for c in spec.criteria] == ["c", "d"]  # a and b were the group's alone


def test_a_screen_with_nothing_left_is_refused() -> None:
    groups = {"g": {"any": ["a", "b"], "enabled": False}}
    with pytest.raises(ConfigurationError, match="at least one enabled criterion"):
        parse_screen_spec(
            "s", {"criteria": {"a": crit("a"), "b": crit("b")}, "groups": groups}, "s"
        )


def test_a_model_screen_keeps_its_score_gate_beside_groups() -> None:
    spec = parse_screen_spec(
        "m",
        {
            "criteria": {"a": crit("a"), "b": crit("b")},
            "groups": {"g": {"any": ["a", "b"]}},
            "score": "feature.edge_score_x",
        },
        "m",
    )
    assert [c.id for c in spec.criteria] == ["a", "b", "score"]
    refused({"g": {"any": ["a", "score"]}}, "unknown criterion or group 'score'")
