"""How a partition's runs combine (``TableSpec.runs``): every backend must agree.

Snapshot tables: the latest run known at ``as_of`` replaces the others. Merge tables
(``events/*``): the union of the runs known at ``as_of``, the latest run's row winning per
table key, starting from the latest restating run (``restates=True``).
"""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

DAY = date(2026, 10, 2)
DIVIDENDS = "events/dividend"
ROLLUP = "rollups/instrument/demo@v1"
NIGHTLY = T0 + timedelta(hours=5)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def dividend(iid: str, day: date, amount: float) -> dict[str, object]:
    return {"instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "cash_amount": amount}


def write(
    backend: Backend, run: str, rows: list[dict[str, object]], at: object, restates: bool = False
) -> None:
    frame = stamped(rows, DAY, run, at)  # type: ignore[arg-type]
    StoreWriter(backend).write_table(DIVIDENDS, DAY, run, frame, restates=restates)


def history(iid: str, amount: float = 0.25) -> list[dict[str, object]]:
    """A quarterly backfill: eight dividends ending before the nightly window."""
    return [dividend(iid, DAY - timedelta(days=91 * q), amount) for q in range(1, 9)]


def keys(frame: pd.DataFrame | None) -> list[tuple[str, date]]:
    assert frame is not None
    pairs = zip(frame["instrument_id"], pd.to_datetime(frame["ts"]).dt.date, strict=True)
    return sorted((str(i), d) for i, d in pairs)


def test_a_later_window_run_does_not_hide_the_backfill(backend: Backend) -> None:
    write(backend, "backfill", history("EQ:A") + history("EQ:B"), T0)
    write(backend, "nightly", [dividend("EQ:C", DAY + timedelta(days=3), 0.1)], NIGHTLY)
    merged = backend.tables.read(DIVIDENDS, DAY)
    assert merged is not None and len(merged) == 17
    assert set(merged["run_id"]) == {"backfill", "nightly"}
    only_a = backend.tables.read(DIVIDENDS, DAY, instruments=["EQ:A"])
    assert only_a is not None and len(only_a) == 8 and set(only_a["instrument_id"]) == {"EQ:A"}


def test_the_latest_run_wins_per_key_and_as_of_pins_the_version(backend: Backend) -> None:
    last = DAY - timedelta(days=91)
    write(backend, "backfill", history("EQ:A"), T0)
    write(backend, "nightly", [dividend("EQ:A", last, 0.3)], NIGHTLY)  # a revision
    merged = backend.tables.read(DIVIDENDS, DAY)
    assert merged is not None and len(merged) == 8
    revised = merged[pd.to_datetime(merged["ts"]).dt.date == last]
    assert list(revised["cash_amount"]) == [0.3] and list(revised["run_id"]) == ["nightly"]
    before = backend.tables.read(DIVIDENDS, DAY, as_of=NIGHTLY - timedelta(seconds=1))
    assert before is not None and set(before["run_id"]) == {"backfill"}
    assert set(before["cash_amount"]) == {0.25}
    assert backend.tables.read(DIVIDENDS, DAY, as_of=T0 - timedelta(seconds=1)) is None


def test_a_later_run_without_an_event_does_not_delete_it(backend: Backend) -> None:
    """No tombstones yet (ADR 0007): a cancelled event stays until a restating run."""
    write(backend, "r1", [dividend("EQ:A", DAY, 0.1), dividend("EQ:B", DAY, 0.2)], T0)
    write(backend, "r2", [dividend("EQ:A", DAY, 0.1)], NIGHTLY)
    assert keys(backend.tables.read(DIVIDENDS, DAY)) == [("EQ:A", DAY), ("EQ:B", DAY)]


def test_a_restating_run_replaces_the_runs_before_it(backend: Backend) -> None:
    """migrate_ids rewrites the merged view under new ids: old-id rows are not resurrected,
    runs after it still merge on top, and reads pinned before it see the old union."""
    migrated = T0 + timedelta(hours=1)
    write(backend, "backfill", history("EQ:OLD"), T0)
    write(backend, "migrate", history("EQ:NEW"), migrated, restates=True)
    write(backend, "nightly", [dividend("EQ:NEW", DAY + timedelta(days=3), 0.3)], NIGHTLY)
    merged = backend.tables.read(DIVIDENDS, DAY)
    assert merged is not None and set(merged["instrument_id"]) == {"EQ:NEW"}
    assert len(merged) == 9 and set(merged["run_id"]) == {"migrate", "nightly"}
    pinned = backend.tables.read(DIVIDENDS, DAY, as_of=migrated - timedelta(seconds=1))
    assert pinned is not None and set(pinned["instrument_id"]) == {"EQ:OLD"}
    ranged = backend.tables.read_range(DIVIDENDS, DAY, DAY)
    assert ranged is not None and keys(ranged) == keys(merged)


def test_runs_merge_per_partition_in_a_range(backend: Backend) -> None:
    other = DAY - timedelta(days=1)
    earlier = stamped([dividend("EQ:A", other, 0.1)], other, "old")
    StoreWriter(backend).write_table(DIVIDENDS, other, "old", earlier)
    write(backend, "backfill", history("EQ:A"), T0)
    write(backend, "nightly", [dividend("EQ:A", DAY, 0.2), dividend("EQ:B", DAY, 0.2)], NIGHTLY)
    ranged = backend.tables.read_range(DIVIDENDS, other, DAY, instruments=["EQ:A"])
    assert ranged is not None and len(ranged) == 10  # 1 + 8 backfilled + 1 nightly
    assert ranged["session_date"].iloc[0] == other  # date order
    assert backend.tables.read_range(DIVIDENDS, other, DAY, as_of=T0) is not None


def test_merged_runs_may_differ_in_producer_columns(backend: Backend) -> None:
    write(backend, "r1", [dividend("EQ:A", DAY - timedelta(days=90), 0.1)], T0)
    late = {**dividend("EQ:A", DAY, 0.2), "frequency": 4}
    write(backend, "r2", [late], NIGHTLY)
    merged = backend.tables.read(DIVIDENDS, DAY)
    assert merged is not None and len(merged) == 2
    assert merged["frequency"].isna().sum() == 1


def test_snapshot_tables_keep_latest_run_wins(backend: Backend) -> None:
    full = [{"instrument_id": i, "value": 1.0} for i in ("EQ:A", "EQ:B", "EQ:C")]
    writer = StoreWriter(backend)
    writer.write_table(ROLLUP, DAY, "r1", stamped(full, DAY, "r1", T0))
    writer.write_table(ROLLUP, DAY, "r2", stamped(full[:1], DAY, "r2", NIGHTLY), restates=True)
    latest = backend.tables.read(ROLLUP, DAY)
    assert latest is not None and list(latest["instrument_id"]) == ["EQ:A"]
    before = backend.tables.read(ROLLUP, DAY, as_of=T0)
    assert before is not None and len(before) == 3
