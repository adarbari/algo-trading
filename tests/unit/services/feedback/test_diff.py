"""The diff of a saved screen against the draft the model returned (ADR 0066): criteria added,
removed and changed by id (field, op, value), the unchanged count and a changed tie-break."""

from algotrade.services.feedback.diff import (
    criteria_diff,
    criteria_snapshot,
    document_diff,
    groups_diff,
)

P = {"field": "rollup.price@v1.close", "op": "gt", "value": 5}
V = {"field": "rollup.vol@v1.hv20", "op": "lt", "value": 0.4}
RETURNED = {"id": "s", "criteria": {"price": P, "vol": V}, "rank": {"tie_break": "a"}}


def test_an_unchanged_save_has_an_empty_diff() -> None:
    diff = criteria_diff(RETURNED, dict(RETURNED))
    assert diff == {"added": [], "removed": [], "changed": [], "unchanged": 2}


def test_added_removed_and_changed_criteria() -> None:
    saved = {
        "id": "s",
        "criteria": {
            "price": {**P, "value": 10},  # changed
            "iv": {"field": "rollup.iv@v1.rank", "op": "gte", "value": 0.5},  # added
        },  # vol removed
        "rank": {"tie_break": "b"},
    }
    diff = criteria_diff(RETURNED, saved)
    assert diff["added"] == [{"id": "iv", "field": "rollup.iv@v1.rank", "op": "gte", "value": 0.5}]
    assert diff["removed"] == [{"id": "vol", **V}]
    assert diff["changed"] == [
        {"id": "price", "field": P["field"], "from": P, "to": {**P, "value": 10}}
    ]
    assert diff["unchanged"] == 0
    assert diff["rank"] == {"from": {"tie_break": "a"}, "to": {"tie_break": "b"}}


def test_a_malformed_document_is_an_empty_one() -> None:
    assert criteria_diff({"criteria": "no"}, {})["unchanged"] == 0


def test_document_diff_lists_added_removed_and_changed_top_level_keys() -> None:
    d = document_diff({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "d": 4})
    assert d == {"added": {"d": 4}, "removed": ["c"], "changed": {"b": {"from": 2, "to": 5}}}
    assert document_diff(None, {"a": 1})["added"] == {"a": 1}


def test_groups_added_removed_and_changed_are_in_the_diff() -> None:
    """ADR 0071: a save that changes the boolean groups of the draft says which."""
    returned = {
        **RETURNED,
        "groups": {"either": {"any": ["price", "vol"]}, "gone": {"none": ["vol"]}},
    }
    saved = {
        **RETURNED,
        "groups": {"either": {"any": ["price", "vol", "iv"]}, "fresh": {"all": ["price", "vol"]}},
    }
    diff = criteria_diff(returned, saved)
    assert diff["groups"] == {
        "added": [{"id": "fresh", "kind": "all", "members": ["price", "vol"]}],
        "removed": [{"id": "gone", "kind": "none", "members": ["vol"]}],
        "changed": [
            {
                "id": "either",
                "from": {"kind": "any", "members": ["price", "vol"]},
                "to": {"kind": "any", "members": ["price", "vol", "iv"]},
            }
        ],
    }


def test_the_same_groups_or_none_leave_no_groups_key() -> None:
    same = {**RETURNED, "groups": {"either": {"any": ["price", "vol"]}}}
    assert "groups" not in criteria_diff(same, dict(same))
    assert "groups" not in criteria_diff(RETURNED, dict(RETURNED))
    assert groups_diff({"groups": "no"}, {}) == {}


def test_the_snapshot_carries_groups_only_when_there_are_some() -> None:
    assert "groups" not in criteria_snapshot(RETURNED)
    held = {**RETURNED, "groups": {"either": {"any": ["price", "vol"]}}}
    assert criteria_snapshot(held)["groups"] == {"either": {"any": ["price", "vol"]}}
