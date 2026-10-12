"""A reading keeps only numbers the part holds: a value, a tolerance, a number in a field name;
a percent sign reads as a fraction, ``M`` / ``k`` / ``B`` as their multiple."""

import pytest

from algotrade.services.drafting.parts.consistency import (
    names_numbers,
    reading_consistent,
    stated,
    values_of,
)


@pytest.mark.parametrize(
    ("reading", "allowed", "ok"),
    [
        ("IV rank of 50% or more", [0.5], True),
        ("IV rank of 50 or more", [50.0], True),  # a percent field holds 50
        ("IV rank of 60% or more", [0.5], False),
        ("About $50M traded a day", [50_000_000.0], True),
        ("Over 1,500 shares", [1500.0], True),
        ("Over 2.5B in value", [2.5e9], True),
        ("A positive 20-day return", [20.0], True),  # from ret_20d
        ("A positive 20-day return", [0.0], False),
        ("Highest IV rank first", [], True),  # no number, nothing to contradict
        ("Within 10% of the low, 5% more shown", [0.1, 0.05], True),
        ("Within 10% of the low, 7% more shown", [0.1, 0.05], False),
        ("Needs 3 of 5 things", [3.0], False),
        ("Fell more than 10%", [-0.1], True),  # ret_20d lt -0.1: the reading drops the sign
        ("Lost over 10% in 20 days", [-0.1, 20.0], True),
        ("Over $50 million a day", [50_000_000.0], True),
        ("Over 2 billion in value", [2e9], True),
        ("Over 3 thousand shares", [3000.0], True),
        ("Over $60 million a day", [50_000_000.0], False),
    ],
)
def test_a_reading_states_only_numbers_the_part_holds(
    reading: str, allowed: list[float], ok: bool
) -> None:
    assert reading_consistent(reading, allowed) is ok


def test_numbers_come_from_values_tolerances_and_field_names() -> None:
    assert values_of([1, 2.5]) == [1.0, 2.5]
    assert values_of({"relative": 0.2}) == [0.2]
    assert values_of(True) == [] and values_of("ETF") == [] and values_of(None) == []
    assert names_numbers(["rollup.price_stats@v2.ret_20d", "feature.pct_from_low_52w"]) == [
        2.0, 20.0, 52.0,
    ]  # fmt: skip
    assert stated("50% and $2M") == [50.0, 0.5, 2.0, 2_000_000.0]
