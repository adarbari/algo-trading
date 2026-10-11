"""The drafting answer schema (ADR 0041, amended 2026-10-11): the shape providers are asked for
and the local check every answer passes, whatever the provider did with the schema."""

import json
from typing import Any

import pytest

from algotrade.services.drafting.answer_schema import (
    ANSWER_SCHEMA,
    check_answer,
    check_criterion,
)

GOOD = {
    "criteria": [
        {"id": "p", "field": "x.y", "op": "gt", "value": 5, "mode": "soft", "tolerance": 0.1},
        {"field": "x.z", "op": "in", "value": ["a", "b"], "tolerance": {"relative": 0.2}},
        {"field": "x.w", "op": "is_null"},  # no value, no id: optional, left out
    ],
    "tie_break": {"field": "x.y", "descending": True},
    "notes": ["assumed"],
}


def test_a_good_answer_fits_with_optional_keys_left_out_or_null() -> None:
    assert check_answer(GOOD, ANSWER_SCHEMA) is None
    assert check_answer({"criteria": []}, ANSWER_SCHEMA) is None  # tie_break and notes are optional
    nulls = {"criteria": [{"id": None, "field": "f", "op": "gt", "value": 1, "mode": None,
                           "tolerance": None, "on_miss": None, "why": None}],
             "tie_break": None, "notes": None}  # fmt: skip
    assert check_answer(nulls, ANSWER_SCHEMA) is None


@pytest.mark.parametrize(
    ("answer", "named"),
    [
        ({"criteria": "none"}, "answer.criteria: expected array"),
        ({"criteria": [5]}, "answer.criteria[0]: expected object"),
        ({"criteria": [{"op": "gt"}]}, "answer.criteria[0]: missing 'field'"),
        ({"criteria": [{"field": "f"}]}, "answer.criteria[0]: missing 'op'"),
        ({"criteria": [{"field": 1, "op": "gt"}]}, "answer.criteria[0].field: expected string"),
        ({"criteria": [{"field": "f", "op": "gt", "value": {"n": 1}}]}, "criteria[0].value"),
        ({"criteria": [{"field": "f", "op": "in", "value": [[1]]}]}, "criteria[0].value"),
        ({"criteria": [{"field": "f", "op": "gt", "value": True, "tolerance": "x"}]}, "tolerance"),
        ({"criteria": [], "notes": [1]}, "answer.notes[0]: expected string"),
        ({"criteria": [], "tie_break": {"descending": True}}, "tie_break"),
    ],
)
def test_a_wrong_shape_names_where(answer: dict[str, Any], named: str) -> None:
    assert named in (check_answer(answer, ANSWER_SCHEMA) or "")


def test_a_bool_is_not_a_number_and_extra_keys_are_tolerated() -> None:
    assert (
        check_answer({"criteria": [{"field": "f", "op": "gt", "tolerance": True}]}, ANSWER_SCHEMA)
        is not None
    )
    assert check_answer({"criteria": [], "thinking": "..."}, ANSWER_SCHEMA) is None


def test_the_schema_is_strict_form_json_every_property_listed_and_nothing_extra() -> None:
    json.dumps(ANSWER_SCHEMA)  # serialisable: it goes to the provider and to --json-schema

    def objects(node: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(node, dict):
            if node.get("type") == "object":
                found.append(node)
            for value in node.values():
                found += objects(value)
        elif isinstance(node, list):
            for value in node:
                found += objects(value)
        return found

    for obj in objects(ANSWER_SCHEMA):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_an_answer_is_refused_for_its_top_level_shape_only() -> None:
    assert check_answer({"criteria": [], "tie_break": "x", "notes": 3}) is None  # read leniently
    assert check_answer({"criteria": [{"field": 1, "tolerance": "x"}]}) is None  # per criterion
    assert "criteria" in (check_answer({"criteria": "none"}) or "")
    assert "missing 'criteria'" in (check_answer({}) or "")
    assert "expected object" in (check_answer([1]) or "")


def test_one_criterion_is_checked_on_its_own() -> None:
    assert check_criterion({"field": "f", "op": "gt", "value": 1}) is None
    assert "tolerance" in (check_criterion({"field": "f", "op": "gt", "tolerance": "x"}) or "")
    assert "value" in (check_criterion({"field": "f", "op": "gt", "value": {"n": 1}}) or "")
