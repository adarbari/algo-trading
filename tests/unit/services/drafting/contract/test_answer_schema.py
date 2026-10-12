"""The drafting answer schema (ADR 0041, amended 2026-10-11): the shape providers are asked for
and the local check every answer passes, whatever the provider did with the schema."""

import json
from typing import Any

import pytest

from algotrade.services.drafting.contract.answer_schema import (
    ANSWER_SCHEMA,
    CRITERION,
    FORMULA,
    MISSING,
    PART,
    SUGGESTION,
    TIE_BREAK,
    UNRESOLVED,
    check_answer,
    check_criterion,
    check_item,
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


NEW = {
    **GOOD,
    "formulas": [
        {
            "name": "draft_x", "expr": "a.b + 1", "dtype": "float", "unit": "ratio",
            "description": "d", "null_meaning": "n", "inputs": ["a.b"],
            "criterion": {"op": "gt", "value": 1, "mode": None, "tolerance": None},
        },
        {"name": "draft_y", "expr": "a.b", "dtype": "float", "unit": "ratio", "description": "d",
         "null_meaning": "n", "inputs": ["a.b"], "criterion": None},
    ],
    "missing": [
        {"key": None, "new_key_slug": "s", "span": "x", "description": "d", "why_needed": "w",
         "closest": [], "feasibility": "UNCLEAR"},
    ],
    "unresolved": [
        {"term": "liquid", "span": "liquid", "default_index": 0,
         "alternatives": [{"label": "a", "criterion": {"field": "f", "op": "gt", "value": 1}}]},
    ],
}  # fmt: skip


def test_the_contract_keys_are_optional_and_nullable_so_an_old_answer_still_fits() -> None:
    assert check_answer(NEW, ANSWER_SCHEMA) is None
    for key in ("formulas", "missing", "unresolved"):
        assert check_answer({**GOOD, key: None}, ANSWER_SCHEMA) is None
        assert check_answer({"criteria": []}, ANSWER_SCHEMA) is None
        assert key in ANSWER_SCHEMA["required"]  # strict form: listed, nullable
    assert ANSWER_SCHEMA["additionalProperties"] is False


@pytest.mark.parametrize(
    ("answer", "named"),
    [
        ({**GOOD, "formulas": "x"}, "answer.formulas: expected array or null"),
        ({**GOOD, "formulas": [{"name": "draft_x"}]}, "formulas[0]: missing 'expr'"),
        ({**GOOD, "missing": [{"span": 1}]}, "answer.missing[0]"),
        ({**GOOD, "unresolved": [{"term": "t", "span": "s", "default_index": "0",
                                  "alternatives": []}]}, "default_index: expected integer"),
        ({**GOOD, "unresolved": [{"term": "t", "span": "s", "default_index": True,
                                  "alternatives": []}]}, "default_index"),
    ],
)  # fmt: skip
def test_a_contract_key_of_the_wrong_shape_names_where(answer: dict[str, Any], named: str) -> None:
    why = check_answer(answer, ANSWER_SCHEMA)
    assert why is not None and named in why


def test_check_item_types_one_item_with_its_name() -> None:
    assert check_item(NEW["formulas"][0], FORMULA, "formula") is None
    assert check_item({}, FORMULA, "formula") == "formula: missing 'name'"


SUGGESTION_ITEM = {
    "field": "feature.trend_state", "op": "ne", "value": "DOWNTREND", "mode": "score",
    "tolerance": None, "on_miss": None, "why": "a falling price", "source": None,
}  # fmt: skip


def test_suggestions_are_optional_nullable_and_typed() -> None:
    assert "suggestions" in ANSWER_SCHEMA["required"]
    assert check_answer({**GOOD, "suggestions": None}, ANSWER_SCHEMA) is None
    assert check_answer({"criteria": []}, ANSWER_SCHEMA) is None  # an old answer
    assert check_answer({**GOOD, "suggestions": [SUGGESTION_ITEM]}, ANSWER_SCHEMA) is None
    assert check_item(SUGGESTION_ITEM, SUGGESTION, "suggestion") is None
    assert check_item({**SUGGESTION_ITEM, "why": None}, SUGGESTION, "suggestion") is not None
    why = check_answer({**GOOD, "suggestions": [{"field": "x"}]}, ANSWER_SCHEMA)
    assert why is not None and "suggestions[0]: missing" in why


def test_the_explained_parts_are_optional_nullable_and_a_part_tag_is_read_leniently() -> None:
    assert "parts" in ANSWER_SCHEMA["required"]
    for schema in (CRITERION, FORMULA, MISSING, UNRESOLVED, SUGGESTION):
        assert "part" in schema["properties"] and "part" in schema["required"]
    assert "part" in TIE_BREAK["anyOf"][0]["required"]
    alternative = UNRESOLVED["properties"]["alternatives"]["items"]["properties"]["criterion"]
    assert "part" not in alternative["properties"]  # the term has the part, not its readings
    assert PART["required"] == ["id", "words", "reading"]
    part = {"id": "p1", "words": "over $5", "reading": None}
    assert check_answer({**GOOD, "parts": [part]}, ANSWER_SCHEMA) is None
    assert check_answer({**GOOD, "parts": None}, ANSWER_SCHEMA) is None
    # a malformed tag never refuses its item: the server reads it with ``part_tag``
    odd = {"field": "x.y", "op": "gt", "value": 5, "part": 7}
    assert check_criterion(odd) is None
    assert check_item({**SUGGESTION_ITEM, "part": ["p1"]}, SUGGESTION, "suggestion") is None
