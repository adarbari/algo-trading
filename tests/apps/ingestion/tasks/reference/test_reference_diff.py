"""``reference_diff``: id changes merge into one event per id; one event per table key."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade_ingestion.tasks.reference import reference_diff
from algotrade_ingestion.tasks.reference.reference_diff import id_change_rows, one_per_key

D = date(2026, 10, 2)
TS = pd.Timestamp(D, tz="UTC")


def known(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, tzinfo=UTC)


def upgrades(rows: list[tuple[str, str, str, datetime]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["old_id", "new_id", "symbol", "known_at"])


def test_two_changes_into_one_id_are_one_event_from_the_first_old_id() -> None:
    """The 2026-10-02 store: DFAC upgraded at 05:05, then moved back by the owner's override
    at 16:23 from the id a vendor flip had given it."""
    rows = id_change_rows(
        upgrades([
            ("EQ:BBG0132J6C32", "EQ:BBG011DXY5J0", "DFAC", known(16, 23)),
            ("EQ:DFAC", "EQ:BBG011DXY5J0", "DFAC", known(5, 5)),
            ("EQ:MMED", "EQ:BBG01Z6N2YW2", "MMED", known(5, 5)),
        ]),
        D,
    )  # fmt: skip
    assert rows.to_dict("records") == [
        {"instrument_id": "EQ:BBG011DXY5J0", "symbol": "DFAC", "change": "id_changed",
         "old": "EQ:DFAC", "new": "EQ:BBG011DXY5J0", "ts": TS},
        {"instrument_id": "EQ:BBG01Z6N2YW2", "symbol": "MMED", "change": "id_changed",
         "old": "EQ:MMED", "new": "EQ:BBG01Z6N2YW2", "ts": TS},
    ]  # fmt: skip


def test_id_change_rows_ties_and_empty() -> None:
    same = upgrades([("EQ:B", "EQ:N", "X", known(5)), ("EQ:A", "EQ:N", "X", known(5))])
    assert id_change_rows(same, D)["old"].tolist() == ["EQ:A"]
    empty = id_change_rows(upgrades([]), D)
    assert empty.empty and "instrument_id" in empty.columns


def clashing() -> pd.DataFrame:
    return pd.DataFrame([
        {"instrument_id": "EQ:N", "symbol": "X", "change": "id_changed", "old": "EQ:B",
         "new": "EQ:N", "ts": TS},
        {"instrument_id": "EQ:N", "symbol": "X", "change": "added", "old": None, "new": "X Co",
         "ts": TS},
        {"instrument_id": "EQ:N", "symbol": "X", "change": "id_changed", "old": "EQ:A",
         "new": "EQ:N", "ts": TS},
    ])  # fmt: skip


def test_a_duplicate_event_fails_loudly_in_tests() -> None:
    assert reference_diff.STRICT  # tests/conftest.py
    with pytest.raises(DataValidationError, match="two events for one key"):
        one_per_key(clashing())


def test_production_keeps_one_row_per_key_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reference_diff, "STRICT", False)
    kept, dropped = one_per_key(clashing())
    assert dropped == 1
    assert kept["change"].tolist() == ["added", "id_changed"]
    assert kept["old"].iloc[1] == "EQ:A"  # the smallest old of the clashing rows
    reversed_kept, _ = one_per_key(clashing().iloc[::-1].reset_index(drop=True))
    assert sorted(reversed_kept["old"].dropna()) == ["EQ:A"]  # same row whatever the order
    unique = clashing().iloc[:2]
    out, none = one_per_key(unique)
    assert none == 0 and out is unique
