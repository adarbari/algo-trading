"""``partition_runs`` / ``purge_runs``: named committed runs are deleted, files included, on
every backend; a run not named is never touched, a busy partition raises and loses nothing
(ADR 0066: an erase must remove the data, not only hide it behind a newer run)."""

import contextlib
import os
import threading
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends import local_index
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend, PartitionBusyError
from tests.helpers.stored_frames import T0, stamped

DAY = date(2026, 10, 2)
TABLE = "events/dividend"


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def rows_of(iid: str) -> list[dict[str, object]]:
    return [{"instrument_id": iid, "ts": pd.Timestamp(DAY, tz="UTC"), "cash_amount": 1.0}]


def put(backend: Backend, run: str, iid: str, hours: int, day: date = DAY) -> None:
    frame = stamped(rows_of(iid), day, run, T0 + timedelta(hours=hours))
    backend.tables.write(TABLE, day, run, frame, pending=True)
    backend.tables.commit_run(run, T0 + timedelta(days=1, hours=hours))


def ids(backend: Backend, day: date = DAY) -> list[str]:
    frame = backend.tables.read(TABLE, day)
    assert frame is not None
    return sorted(frame["instrument_id"])


def files(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "data").rglob("*.parquet"))


def test_runs_are_listed_oldest_commit_first(backend: Backend) -> None:
    put(backend, "b", "EQ:A", 5)  # the later ts, committed first
    put(backend, "a", "EQ:B", 1)
    assert backend.tables.partition_runs(TABLE, DAY) == ["b", "a"]
    assert backend.tables.partition_runs(TABLE, date(2020, 1, 1)) == []


def test_named_runs_go_with_their_files_and_others_are_untouched(
    backend: Backend, tmp_path: Path
) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "r2", "EQ:B", 1)
    put(backend, "r3", "EQ:C", 2)
    put(backend, "other", "EQ:Z", 0, day=DAY + timedelta(days=1))
    assert backend.tables.purge_runs(TABLE, DAY, ["r1", "r2", "missing"]) == 2
    assert ids(backend) == ["EQ:C"] and ids(backend, DAY + timedelta(days=1)) == ["EQ:Z"]
    if isinstance(backend, LocalBackend):
        assert files(tmp_path) == ["run=other.parquet", "run=r3.parquet"]


def test_it_is_idempotent_and_moves_the_published_sequence(backend: Backend) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "r2", "EQ:B", 1)
    before = backend.tables.visible_seq()
    assert backend.tables.purge_runs(TABLE, DAY, ["r1"]) == 1
    assert backend.tables.visible_seq() == before + 1
    assert backend.tables.purge_runs(TABLE, DAY, ["r1"]) == 0
    assert backend.tables.visible_seq() == before + 1


def test_a_busy_partition_raises_and_nothing_is_deleted(backend: Backend) -> None:
    put(backend, "r1", "EQ:A", 0)
    frame = stamped(rows_of("EQ:Z"), DAY, "busy", T0 + timedelta(hours=5))
    backend.tables.write(TABLE, DAY, "busy", frame, pending=True)
    with pytest.raises(PartitionBusyError):
        backend.tables.purge_runs(TABLE, DAY, ["r1"])
    assert backend.tables.partition_runs(TABLE, DAY) == ["r1"]
    backend.tables.abort_run("busy")
    assert backend.tables.purge_runs(TABLE, DAY, ["r1"]) == 1


def test_a_commit_racing_a_purge_is_never_lost(backend: Backend) -> None:
    put(backend, "old", "EQ:A", 0)
    stop = threading.Event()
    landed: list[str] = []

    def commits() -> None:
        n = 0
        while not stop.is_set() and n < 25:
            run = f"new{n}"
            put(backend, run, f"EQ:N{n}", 1 + n)
            landed.append(run)
            n += 1

    thread = threading.Thread(target=commits)
    thread.start()
    for _ in range(25):  # purges of runs that are not the racing writer's
        with contextlib.suppress(PartitionBusyError):  # the writer is mid-run: a later pass
            backend.tables.purge_runs(TABLE, DAY, ["old"])
    thread.join()
    backend.tables.purge_runs(TABLE, DAY, ["old"])
    assert backend.tables.partition_runs(TABLE, DAY) == landed
    assert ids(backend) == sorted(f"EQ:N{i}" for i in range(len(landed)))


def test_sweep_removes_only_files_no_index_entry_names(backend: Backend, tmp_path: Path) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "r2", "EQ:B", 1)
    if isinstance(backend, LocalBackend):
        keep = next((tmp_path / "data").rglob("run=r1.parquet"))
        ghost = keep.parent / "run=ghost.parquet"
        ghost.write_bytes(keep.read_bytes())  # a crashed purge
        os.utime(ghost, (0, 0))
        young = keep.parent / "run=young.parquet"
        young.write_bytes(keep.read_bytes())  # maybe a direct write about to be indexed
        assert backend.tables.sweep_orphans(TABLE, DAY) == 1 and young.exists()
        young.unlink()
    assert backend.tables.sweep_orphans(TABLE, DAY) == 0  # the ghost went in the first pass
    assert backend.tables.sweep_orphans(TABLE, DAY) == 0
    assert backend.tables.partition_runs(TABLE, DAY) == ["r1", "r2"] and ids(backend) == [
        "EQ:A",
        "EQ:B",
    ]
    if isinstance(backend, LocalBackend):
        assert files(tmp_path) == ["run=r1.parquet", "run=r2.parquet"]


def test_sweep_leaves_a_pending_runs_files_and_raises_when_busy(backend: Backend) -> None:
    put(backend, "r1", "EQ:A", 0)
    frame = stamped(rows_of("EQ:Z"), DAY, "busy", T0 + timedelta(hours=5))
    backend.tables.write(TABLE, DAY, "busy", frame, pending=True)
    with pytest.raises(PartitionBusyError):
        backend.tables.sweep_orphans(TABLE, DAY)
    backend.tables.commit_run("busy", T0 + timedelta(days=2))
    assert ids(backend) == ["EQ:A", "EQ:Z"]


def test_a_run_staged_between_the_busy_check_and_the_glob_is_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = LocalBackend(tmp_path / "data")
    put(local, "r1", "EQ:A", 0)
    real = local_index.read_index
    staged: list[str] = []

    def stage_then_read(directory: Path) -> object:
        if not staged:  # after the busy check, before the glob
            staged.append("late")
            frame = stamped(rows_of("EQ:Z"), DAY, "late", T0 + timedelta(hours=5))
            local.tables.write(TABLE, DAY, "late", frame, pending=True)
            for p in directory.glob("run=late*.parquet"):
                os.utime(p, (0, 0))  # old enough: only the pending journal protects it
        return real(directory)

    monkeypatch.setattr(local_index, "read_index", stage_then_read)
    assert local.tables.sweep_orphans(TABLE, DAY) == 0
    monkeypatch.setattr(local_index, "read_index", real)
    local.tables.commit_run("late", T0 + timedelta(days=2))
    assert ids(local) == ["EQ:A", "EQ:Z"]
