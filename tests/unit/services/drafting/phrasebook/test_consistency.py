"""``compatible``: whether the criteria on one field leave any value."""

from typing import Any

import pytest

from algotrade.services.drafting.phrasebook.consistency import compatible


def c(op: str, value: Any = None, field: str = "feature.x") -> dict[str, Any]:
    return {"field": field, "op": op, **({} if value is None else {"value": value})}


@pytest.mark.parametrize(
    "criteria",
    [
        [c("lt", 30), c("gt", 70)],
        [c("lt", 5), c("gte", 5)],
        [c("lt", 5), c("eq", 9)],
        [c("between", [1, 2]), c("gt", 3)],
        [c("eq", "A"), c("eq", "B")],
        [c("in", ["ETF"]), c("in", ["ADR", "COMMON_STOCK"])],
        [c("eq", "A"), c("ne", "A")],
        [c("in", ["A", "B"]), c("not_in", ["A", "B"])],
        [c("is_null"), c("not_null")],
        [c("is_null"), c("gt", 1)],
        [c("gte", 3), c("lte", 3), c("ne", 3)],
    ],
)
def test_criteria_with_no_common_value_are_incompatible(criteria) -> None:
    assert not compatible(criteria)


@pytest.mark.parametrize(
    "criteria",
    [
        [c("gt", 1), c("lt", 5)],
        [c("gte", 3), c("lte", 3)],
        [c("in", ["A", "B"]), c("eq", "B")],
        [c("eq", "A"), c("ne", "B")],
        [c("not_null"), c("gt", 1)],
        [c("eq", True), c("eq", True)],
        [c("lt", 30, "feature.x"), c("gt", 70, "feature.y")],  # different fields
    ],
)
def test_criteria_with_a_common_value_are_compatible(criteria) -> None:
    assert compatible(criteria)
