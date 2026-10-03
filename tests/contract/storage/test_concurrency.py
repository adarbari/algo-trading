"""Storage contract, concurrency: runs written to the same partition at the same time (by
threads, or for the local backend by processes) are all indexed, and no temp file is left."""

import multiprocessing as mp
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from tests.storage_helpers import stamped

DAY = date(2026, 10, 1)
TABLE = "rollups/instrument/demo@v1"
RUNS_EACH = 15


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def _write_runs(backend: Backend, writer: str) -> None:
    for i in range(RUNS_EACH):
        run = f"{writer}-{i}"
        frame = stamped([{"instrument_id": "EQ:A", "value": float(i)}], DAY, run)
        backend.tables.write(TABLE, DAY, run, frame)


def _indexed_runs(backend: Backend) -> set[str]:
    """Runs a reader can see: each is the latest when read as of its own knowledge time."""
    frame = backend.tables.read_range(TABLE, DAY, DAY)
    assert frame is not None
    if isinstance(backend, LocalBackend):
        directory = backend.root / "tables" / TABLE / f"date={DAY.isoformat()}"
        index = backend.tables._index(directory)
        assert not list(directory.glob("*.tmp")), "temp files left behind"
        return set(index)
    return set(backend.tables._data[(TABLE, DAY)])  # type: ignore[attr-defined]


def test_concurrent_threads_writing_one_partition_are_all_indexed(backend: Backend) -> None:
    threads = [threading.Thread(target=_write_runs, args=(backend, w)) for w in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    expected = {f"{w}-{i}" for w in ("a", "b", "c") for i in range(RUNS_EACH)}
    assert _indexed_runs(backend) == expected


def _process_writer(root: str, writer: str) -> None:
    _write_runs(LocalBackend(Path(root)), writer)


def test_concurrent_processes_writing_one_partition_are_all_indexed(tmp_path: Path) -> None:
    root = tmp_path / "data"
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_process_writer, args=(str(root), w)) for w in ("p", "q")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
        assert p.exitcode == 0
    expected = {f"{w}-{i}" for w in ("p", "q") for i in range(RUNS_EACH)}
    assert _indexed_runs(LocalBackend(root)) == expected
