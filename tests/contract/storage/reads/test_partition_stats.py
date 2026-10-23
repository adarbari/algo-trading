"""Storage contract, ``partition_stats``: rows, run ids and one column's values of a partition,
equal to what a full ``read`` of it gives (``PartitionStats.of``), for every shape of partition
(one run, a latest run replacing another, merged runs, a restated day, an empty one, pending
writes of the reader's own run, a pinned reader); the local backend counting a one-run partition
from the Parquet footer, decoding no more than ``run_id`` and the asked column."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend, PartitionStats
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
STATUS = "chains/status"  # snapshot run mode, a ``status`` column
MERGE = "volatility/ibkr_iv30"  # merge run mode: runs union, the latest row winning per key
AT = T0 + timedelta(minutes=30)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def statuses(day: date, run: str, *pairs: tuple[str, str], later: int = 0) -> pd.DataFrame:
    rows: list[dict[str, object]] = [{"instrument_id": i, "status": s} for i, s in pairs]
    return stamped(rows, day, run, knowledge=T0 + timedelta(hours=later))


def vols(day: date, run: str, *ids: str, later: int = 0) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": i, "iv30_ibkr": 0.2, "source_kind": "ib"} for i in ids
    ]
    return stamped(rows, day, run, knowledge=T0 + timedelta(hours=later))


def put(backend: Backend, table: str, run: str, day: date, frame: pd.DataFrame, **kw: bool) -> None:
    backend.tables.write(table, day, run, frame, pending=True, **kw)
    backend.tables.commit_run(run, AT)


def same_as_a_full_read(reader: StoreReader, table: str, day: date, column: str | None) -> None:
    full = reader.table(table, day)
    found = reader.partition_stats(table, day, column)
    assert found == (None if full is None else PartitionStats.of(full, column))


def test_one_run_partition_counts_rows_run_and_the_asked_column(backend: Backend) -> None:
    put(backend, STATUS, "r1", D1, statuses(D1, "r1", ("EQ:A", "OK"), ("EQ:B", "STALE")))
    found = StoreReader(backend).partition_stats(STATUS, D1, "status")
    assert found == PartitionStats(2, ("r1",), ("OK", "STALE"))
    assert StoreReader(backend).partition_stats(STATUS, D1) == PartitionStats(2, ("r1",), ())
    assert StoreReader(backend).partition_stats(STATUS, D1, "absent") == PartitionStats(
        2, ("r1",), ()
    )


def test_no_partition_is_none_and_an_empty_one_counts_nothing(backend: Backend) -> None:
    reader = StoreReader(backend)
    assert reader.partition_stats(STATUS, D1, "status") is None
    put(backend, STATUS, "r1", D2, statuses(D2, "r1"))
    same_as_a_full_read(reader, STATUS, D2, "status")


def test_a_later_snapshot_run_replaces_the_earlier(backend: Backend) -> None:
    put(backend, STATUS, "r1", D1, statuses(D1, "r1", ("EQ:A", "OK"), ("EQ:B", "OK")))
    put(backend, STATUS, "r2", D1, statuses(D1, "r2", ("EQ:A", "STALE"), later=1))
    reader = StoreReader(backend)
    assert reader.partition_stats(STATUS, D1, "status") == PartitionStats(1, ("r2",), ("STALE",))
    same_as_a_full_read(reader, STATUS, D1, "status")


def test_merged_runs_count_the_merge_not_the_files(backend: Backend) -> None:
    put(backend, MERGE, "r1", D1, vols(D1, "r1", "EQ:A", "EQ:B"))
    put(backend, MERGE, "r2", D1, vols(D1, "r2", "EQ:B", "EQ:C", later=1))  # B restated by r2
    reader = StoreReader(backend)
    found = reader.partition_stats(MERGE, D1)
    assert found is not None and found.rows == 3 and found.run_ids == ("r1", "r2")
    same_as_a_full_read(reader, MERGE, D1, None)


def test_a_restating_run_hides_the_runs_before_it(backend: Backend) -> None:
    put(backend, MERGE, "r1", D1, vols(D1, "r1", "EQ:A", "EQ:B"))
    put(backend, MERGE, "r2", D1, vols(D1, "r2", "EQ:C", later=1), restates=True)
    reader = StoreReader(backend)
    assert reader.partition_stats(MERGE, D1) == PartitionStats(1, ("r2",))
    same_as_a_full_read(reader, MERGE, D1, None)


def test_a_pinned_reader_counts_the_partition_as_of_its_pin(backend: Backend) -> None:
    put(backend, STATUS, "r1", D1, statuses(D1, "r1", ("EQ:A", "OK")))
    pin = backend.tables.visible_seq()
    put(backend, STATUS, "r2", D1, statuses(D1, "r2", ("EQ:A", "OK"), ("EQ:B", "OK"), later=1))
    live, pinned = StoreReader(backend), StoreReader(backend).pinned(pin)
    assert live.partition_stats(STATUS, D1) == PartitionStats(2, ("r2",))
    assert pinned.partition_stats(STATUS, D1) == PartitionStats(1, ("r1",))
    same_as_a_full_read(pinned, STATUS, D1, None)


def test_a_reader_sees_the_pending_writes_of_its_own_run(backend: Backend) -> None:
    backend.tables.write(STATUS, D3, "mine", statuses(D3, "mine", ("EQ:A", "OK")), pending=True)
    assert StoreReader(backend).partition_stats(STATUS, D3) is None
    own = StoreReader(backend).including("mine")
    assert own.partition_stats(STATUS, D3) == PartitionStats(1, ("mine",))
    same_as_a_full_read(own, STATUS, D3, "status")


def test_a_one_run_partition_is_counted_without_decoding_its_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count cells of the ingestion grid (1,636 partitions on a cold first request) read the
    footer; the one column a cell needs is the only one decoded."""
    backend = LocalBackend(tmp_path / "data")
    put(backend, STATUS, "r1", D1, statuses(D1, "r1", ("EQ:A", "OK"), ("EQ:B", "STALE")))
    decoded: list[object] = []
    real = pq.ParquetFile.read

    def spy(self: pq.ParquetFile, columns: object = None, *a: object, **k: object) -> object:
        decoded.append(columns)
        return real(self, columns, *a, **k)

    monkeypatch.setattr(pq.ParquetFile, "read", spy)
    reader = StoreReader(backend)
    assert reader.partition_stats(STATUS, D1) == PartitionStats(2, ("r1",))
    assert decoded == []  # the footer alone: rows and the one run id
    assert reader.partition_stats(STATUS, D1, "status") is not None
    assert decoded == [["status"]]
