"""The diff of a saved screen against the draft the model returned (ADR 0066): criteria added,
removed and changed by id (field, op, value), the unchanged count and a changed tie-break."""

from algotrade.services.feedback.diff import criteria_diff

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
