"""``migrate-ids``: append-only, point-in-time, idempotent (ADR 0018)."""

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.interfaces import Backend
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.instrument_ids import ID_MAP, ID_MAP_COLUMNS
from algotrade_ingestion.jobs.migrate_ids import migrate_ids
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

    dry = migrate_ids(writer, reader, dry_run=True, clock=lambda: MIGRATED)
    assert dry.stats["tables"] == {
        "bars/1d": {"partitions": 1, "rows": 1},
        "chains/option_quotes": {"partitions": 1, "rows": 1},
    }
    assert reader.runs("migrate_ids") == []  # a dry run writes nothing
    assert list(reader.table("bars/1d", D1)["instrument_id"]) == ["EQ:AAPL", "EQ:ZZZ"]  # type: ignore[index]

    run = migrate_ids(writer, reader, clock=lambda: MIGRATED)
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

    again = migrate_ids(writer, reader, clock=lambda: MIGRATED + timedelta(hours=1))
    assert again.stats["tables"] == {}


def test_nothing_to_do_without_an_id_map() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    writer.write_table("bars/1d", D1, "b1", stamped([bar("EQ:AAPL", D1)], D1, "b1"))
    record = migrate_ids(writer, reader, clock=lambda: MIGRATED)
    assert (record.stats["mapped_ids"], record.stats["tables"]) == (0, {})


def test_a_partition_holding_old_and_new_ids_is_reported_not_written() -> None:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    seed(writer)
    both = stamped([bar("EQ:AAPL", D2), bar("EQ:BBG1", D2)], D2, "b2", T0)
    writer.write_table("bars/1d", D2, "b2", both)
    record = migrate_ids(writer, reader, clock=lambda: MIGRATED)
    assert record.status == "partial" and record.stats["failed_count"] == 1
    assert "bars/1d 2026-10-01" in record.stats["failed"][0]
    assert list(reader.table("bars/1d", D2)["instrument_id"]) == ["EQ:AAPL", "EQ:BBG1"]  # type: ignore[index]
