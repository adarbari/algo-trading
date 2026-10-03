"""``migrate-ids``: append-only, point-in-time, idempotent (ADR 0018)."""

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.migrate_ids import migrate_ids
from algotrade_ingestion.tasks.reference.instrument_ids import ID_MAP, ID_MAP_COLUMNS
from tests.ingest_helpers import task_ctx
from tests.storage_helpers import T0, stamped

D1, D2 = date(2026, 9, 30), date(2026, 10, 1)
UPGRADED = T0 + timedelta(hours=1)  # when the universe build recorded AAPL -> FIGI
MIGRATED = T0 + timedelta(hours=2)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Backend:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    return factories[request.param]()


def bar(iid: str, day: date) -> dict[str, object]:
    ts = pd.Timestamp(day, tz="UTC")
    return {"instrument_id": iid, "ts": ts, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
            "volume": 1.0}  # fmt: skip


def seed(writer: StoreWriter) -> None:
    writer.write_table(
        "bars/1d", D1, "b1", stamped([bar("EQ:AAPL", D1), bar("EQ:ZZZ", D1)], D1, "b1")
    )
    option = {
        "instrument_id": "OPT:AAPL261231C00200000", "underlying_id": "EQ:AAPL",
        "ts": pd.Timestamp(D1, tz="UTC"), "expiry": date(2026, 12, 31), "right": "C",
        "strike": 200.0, "bid": 1.0, "ask": 1.1, "volume": 1.0, "open_interest": 1.0,
        "iv": 0.2, "delta": 0.5,
    }  # fmt: skip
    writer.write_table("chains/option_quotes", D1, "c1", stamped([option], D1, "c1"))
    id_map = [
        {
            "instrument_id": "EQ:BBG1", "ts": pd.Timestamp(D2, tz="UTC"), "old_id": "EQ:AAPL",
            "new_id": "EQ:BBG1", "symbol": "AAPL", "effective": D2,
            "known_at": pd.Timestamp(UPGRADED),
        }
    ]  # fmt: skip
    frame = stamped(id_map, D2, "u1", UPGRADED)
    assert list(frame.columns[: len(ID_MAP_COLUMNS)]) == ID_MAP_COLUMNS
    writer.write_table(ID_MAP, D2, "u1", frame)


def test_migration_is_append_only_point_in_time_and_idempotent(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    seed(writer)
    # A bar written after the upgrade under the old symbol id is another listing's: left alone.
    late = stamped([bar("EQ:AAPL", D2)], D2, "b2", UPGRADED + timedelta(minutes=5))
    writer.write_table("bars/1d", D2, "b2", late)

    dry = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED), dry_run=True)
    assert dry.stats["tables"] == {
        "bars/1d": {"partitions": 1, "rows": 1},
        "chains/option_quotes": {"partitions": 1, "rows": 1},
    }
    assert reader.runs("migrate_ids") == []  # a dry run writes nothing
    assert list(reader.table("bars/1d", D1)["instrument_id"]) == ["EQ:AAPL", "EQ:ZZZ"]  # type: ignore[index]

    run = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED))
    assert run.status == "complete" and run.stats["tables"] == dry.stats["tables"]
    bars = reader.table("bars/1d", D1)
    assert bars is not None and list(bars["instrument_id"]) == ["EQ:BBG1", "EQ:ZZZ"]
    assert set(bars["run_id"]) == {run.run_id}
    before = reader.table("bars/1d", D1, as_of=UPGRADED)  # as known before the migration
    assert before is not None and list(before["instrument_id"]) == ["EQ:AAPL", "EQ:ZZZ"]
    chains = reader.table("chains/option_quotes", D1)
    assert chains is not None and list(chains["underlying_id"]) == ["EQ:BBG1"]
    assert list(chains["instrument_id"]) == ["OPT:AAPL261231C00200000"]  # OCC ids stay
    assert list(reader.table("bars/1d", D2)["instrument_id"]) == ["EQ:AAPL"]  # type: ignore[index]

    again = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED + timedelta(hours=1)))
    assert again.stats["tables"] == {}


def test_nothing_to_do_without_an_id_map() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    writer.write_table("bars/1d", D1, "b1", stamped([bar("EQ:AAPL", D1)], D1, "b1"))
    record = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED))
    assert (record.stats["mapped_ids"], record.stats["tables"]) == (0, {})


def test_a_partition_holding_old_and_new_ids_is_reported_not_written() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    seed(writer)
    both = stamped([bar("EQ:AAPL", D2), bar("EQ:BBG1", D2)], D2, "b2", T0)
    writer.write_table("bars/1d", D2, "b2", both)
    record = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED))
    assert record.status == "partial" and record.stats["failed_count"] == 1
    assert "bars/1d 2026-10-01" in record.stats["failed"][0]
    assert list(reader.table("bars/1d", D2)["instrument_id"]) == ["EQ:AAPL", "EQ:BBG1"]  # type: ignore[index]


def dividend(iid: str, day: date, amount: float = 0.25) -> dict[str, object]:
    return {"instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "cash_amount": amount}


EVENT_DAYS = [D1 - timedelta(days=91 * q) for q in range(4)]


def test_merge_tables_are_rewritten_whole_and_old_ids_stay_gone(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    seed(writer)
    backfill = [dividend("EQ:AAPL", d) for d in EVENT_DAYS] + [dividend("EQ:KO", D1)]
    writer.write_table("events/dividend", D1, "ca1", stamped(backfill, D1, "ca1"))
    run = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED))
    assert run.stats["tables"]["events/dividend"] == {"partitions": 1, "rows": 4}
    nightly = [dividend("EQ:BBG1", D1 + timedelta(days=5))]  # a later window run, new ids
    later = MIGRATED + timedelta(hours=1)
    writer.write_table("events/dividend", D1, "ca2", stamped(nightly, D1, "ca2", later))

    merged = reader.table("events/dividend", D1)
    assert merged is not None and len(merged) == 6  # 4 + KO + the nightly row
    assert set(merged["instrument_id"]) == {"EQ:BBG1", "EQ:KO"}  # no EQ:AAPL resurrected
    pinned = reader.table("events/dividend", D1, as_of=UPGRADED)
    assert pinned is not None and "EQ:AAPL" in set(pinned["instrument_id"])
    again = migrate_ids(task_ctx(writer, reader, lambda: later + timedelta(hours=1)))
    assert "events/dividend" not in again.stats["tables"]  # idempotent


def test_a_merge_partition_migrated_without_restating_is_repaired_by_a_rerun(
    backend: Backend,
) -> None:
    """Stores migrated before restating runs existed hold the backfill (old ids) and a plain
    migrate run (new ids): merged, both ids show. Re-running migrate-ids restates it."""
    writer, reader = StoreWriter(backend), StoreReader(backend)
    seed(writer)
    old = [dividend("EQ:AAPL", d) for d in EVENT_DAYS]
    writer.write_table("events/dividend", D1, "ca1", stamped(old, D1, "ca1"))
    new = [dividend("EQ:BBG1", d) for d in EVENT_DAYS]
    writer.write_table("events/dividend", D1, "m0", stamped(new, D1, "m0", MIGRATED))
    before = reader.table("events/dividend", D1)
    assert before is not None and set(before["instrument_id"]) == {"EQ:AAPL", "EQ:BBG1"}

    rerun = migrate_ids(task_ctx(writer, reader, lambda: MIGRATED + timedelta(hours=1)))
    assert rerun.status == "complete"
    after = reader.table("events/dividend", D1)
    assert after is not None and len(after) == 4 and set(after["instrument_id"]) == {"EQ:BBG1"}
