"""Position-level fields (ADR 0088, design 2.4a) hand-computed on a short put fixture, the running
``max_adverse``, and the point-in-time property: shifting later closes never changes an earlier
row."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from algotrade.engines.structures.position_fields import (
    CloseFacts,
    EntryFacts,
    Short,
    max_adverse,
    walk_fields,
)

ENTRY = EntryFacts(date(2026, 10, 5), 100.0, -2.0, collateral=90.0,
                   shorts=(Short(95.0, "P"),), expiry=date(2026, 11, 6))  # fmt: skip


def closes(values: list[float | None], spots: list[float]) -> list[CloseFacts]:
    return [
        CloseFacts(date(2026, 10, 6 + i), i + 1, spots[i], v, -0.2) for i, v in enumerate(values)
    ]


def test_every_field_hand_computed() -> None:
    row = walk_fields(ENTRY, closes([-1.0, -3.0], [102.0, 94.0]))
    assert row[0]["position.days_held"] == 1
    assert row[0]["position.move_since_entry_pct"] == pytest.approx(0.02)
    assert row[0]["position.profit_share_of_credit"] == pytest.approx(0.5)  # (-1 - -2) / 2
    assert row[0]["position.mark_loss_share_of_collateral"] == 0.0
    assert row[0]["position.position_delta"] == -0.2
    assert row[0]["position.distance_to_strike_pct"] == pytest.approx(-7 / 102)  # OTM: negative
    assert row[0]["position.dte"] == 31
    assert row[1]["position.profit_share_of_credit"] == pytest.approx(-0.5)
    assert row[1]["position.mark_loss_share_of_collateral"] == pytest.approx(1 / 90)
    assert row[1]["position.distance_to_strike_pct"] == pytest.approx(1 / 94)  # ITM: positive


def test_max_adverse_is_the_running_worst_and_missing_mark_carries() -> None:
    cs = closes([-4.0, None, -2.5], [99.0, 99.0, 99.0])
    assert max_adverse(ENTRY, cs) == pytest.approx(2.0 / 90)
    assert walk_fields(ENTRY, cs)[1]["position.profit_share_of_credit"] is None


def test_no_credit_no_collateral_are_none() -> None:
    long = EntryFacts(date(2026, 10, 5), 10.0, 3.0)
    row = walk_fields(long, closes([4.0], [11.0]))[0]
    assert row["position.profit_share_of_credit"] is None
    assert row["position.mark_loss_share_of_collateral"] is None
    assert row["position.dte"] is None and row["position.position_delta"] is None
    assert row["position.move_since_entry_pct"] == pytest.approx(0.1)


@given(
    st.lists(st.floats(-6, 0), min_size=3, max_size=6),
    st.floats(-6, 0),
)
def test_later_quotes_leave_earlier_fields_unchanged(values: list[float], shifted: float) -> None:
    spots = [100.0 + i for i in range(len(values))]
    base = walk_fields(ENTRY, closes(list(values), spots))
    later = [*values[:-1], shifted]
    assert walk_fields(ENTRY, closes(later, spots))[:-1] == base[:-1]


def test_nan_mark_is_missing_not_zero() -> None:
    nan = float("nan")
    assert max_adverse(ENTRY, closes([nan], [99.0])) is None
    cs = closes([-4.0, nan, -3.0], [99.0] * 3)
    rows = walk_fields(ENTRY, cs)
    assert rows[1]["position.mark_loss_share_of_collateral"] == pytest.approx(2.0 / 90)
    assert rows[1]["position.profit_share_of_credit"] is None
