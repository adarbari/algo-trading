"""Storage contract, ``read_run`` (ADR 0064): one committed run's own rows of a partition,
whichever run is the latest, without reading the other runs' files."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
TABLE = "rollups/instrument/a@v1"
AT = T0 + timedelta(minutes=30)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def rows(day: date, run: str, *ids: str, later: int = 0) -> pd.DataFrame:
    data = [{"instrument_id": i, "value": 1.0} for i in ids]
    return stamped(data, day, run, knowledge=T0 + timedelta(hours=later))


def publish(backend: Backend, run: str, frame: pd.DataFrame, day: date = D1) -> None:
    backend.tables.write(TABLE, day, run, frame, pending=True)
    backend.tables.commit_run(run, AT)


def test_it_reads_one_runs_rows_of_a_partition_with_several(backend: Backend) -> None:
    publish(backend, "r1", rows(D1, "r1", "EQ:A", "EQ:B"))
    publish(backend, "r2", rows(D1, "r2", "EQ:C", later=1))
    found = backend.tables.read_run(TABLE, D1, "r1")
    assert found is not None and sorted(found["instrument_id"]) == ["EQ:A", "EQ:B"]
    assert set(found["run_id"]) == {"r1"}


def test_an_older_run_is_read_though_a_later_one_is_the_latest(backend: Backend) -> None:
    publish(backend, "r1", rows(D1, "r1", "EQ:A"))
    publish(backend, "r2", rows(D1, "r2", "EQ:B", later=1))
    latest = backend.tables.read(TABLE, D1)
    assert latest is not None and set(latest["run_id"]) == {"r2"}
    older = backend.tables.read_run(TABLE, D1, "r1")
    assert older is not None and list(older["instrument_id"]) == ["EQ:A"]


def test_only_rows_stamped_with_the_run_are_returned(backend: Backend) -> None:
    mixed = pd.concat([rows(D1, "r1", "EQ:A"), rows(D1, "other", "EQ:B")], ignore_index=True)
    publish(backend, "r1", mixed)
    found = backend.tables.read_run(TABLE, D1, "r1")
    assert found is not None and list(found["instrument_id"]) == ["EQ:A"]


def test_nothing_stored_is_none(backend: Backend) -> None:
    publish(backend, "r1", rows(D1, "r1", "EQ:A"))
    assert backend.tables.read_run(TABLE, D1, "nope") is None
    assert backend.tables.read_run(TABLE, D2, "r1") is None
    assert backend.tables.read_run("rollups/instrument/none@v1", D1, "r1") is None


def test_a_pending_run_is_invisible_but_its_own_reader_sees_it(backend: Backend) -> None:
    backend.tables.write(TABLE, D1, "r1", rows(D1, "r1", "EQ:A"), pending=True)
    assert backend.tables.read_run(TABLE, D1, "r1") is None
    mine = backend.tables.read_run(TABLE, D1, "r1", own_run="r1")
    assert mine is not None and list(mine["instrument_id"]) == ["EQ:A"]


def test_a_rewrite_of_the_run_replaces_its_rows(backend: Backend) -> None:
    publish(backend, "r1", rows(D1, "r1", "EQ:A"))
    publish(backend, "r1", rows(D1, "r1", "EQ:B"))
    found = backend.tables.read_run(TABLE, D1, "r1")
    assert found is not None and list(found["instrument_id"]) == ["EQ:B"]


def test_the_reader_facade_reads_a_run(backend: Backend) -> None:
    publish(backend, "r1", rows(D1, "r1", "EQ:A"))
    found = StoreReader(backend).read_run(TABLE, D1, "r1")
    assert found is not None and len(found) == 1


def test_the_local_backend_does_not_open_another_runs_file(tmp_path: Path) -> None:
    local = LocalBackend(tmp_path / "data")
    publish(local, "r1", rows(D1, "r1", "EQ:A"))
    publish(local, "r2", rows(D1, "r2", "EQ:B", later=1))
    for path in (tmp_path / "data" / "tables" / TABLE).rglob("run=r2*.parquet"):
        path.write_bytes(b"not parquet")
    found = local.tables.read_run(TABLE, D1, "r1")
    assert found is not None and list(found["instrument_id"]) == ["EQ:A"]


def test_columns_decode_only_those_and_the_stamps(backend: Backend) -> None:
    frame = rows(D1, "r1", "EQ:A", "EQ:B")
    frame["extra"] = "x"
    publish(backend, "r1", frame)
    found = backend.tables.read_run(TABLE, D1, "r1", columns=["value"])
    assert found is not None and list(found["instrument_id"]) == ["EQ:A", "EQ:B"]
    assert "extra" not in found.columns and {"value", "run_id", "knowledge_ts"} <= set(
        found.columns
    )


def test_instruments_read_only_their_rows_of_the_run(backend: Backend) -> None:
    publish(backend, "r1", rows(D1, "r1", "EQ:A", "EQ:B", "EQ:C"))
    publish(backend, "r2", rows(D1, "r2", "EQ:A", later=1))
    found = backend.tables.read_run(TABLE, D1, "r1", instruments=["EQ:C", "EQ:A", "EQ:Z"])
    assert found is not None and sorted(found["instrument_id"]) == ["EQ:A", "EQ:C"]
    assert set(found["run_id"]) == {"r1"}
    assert backend.tables.read_run(TABLE, D1, "r1", instruments=["EQ:Z"]) is None
    assert backend.tables.read_run(TABLE, D1, "r1", instruments=[]) is None
