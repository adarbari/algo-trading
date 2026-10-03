"""Locks shared across threads and processes (``storage/locks.py``) and the ingest run lock
(``services/jobs/exclusive.py``)."""

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from algotrade.services.jobs import RunLockedError, exclusive_run
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.locks import FileLock, ThreadLock, held

HOLDER = """
import sys, time
from pathlib import Path
from algotrade.storage.locks import FileLock
lock = FileLock(Path(sys.argv[1]))
assert lock.acquire()
print("held", flush=True)
sys.stdin.readline()  # hold until the parent says so
lock.release()
"""


def test_file_locks_exclude_each_other_and_release(tmp_path: Path) -> None:
    first, second = FileLock(tmp_path / "x.lock"), FileLock(tmp_path / "x.lock")
    with held(first) as taken:
        assert taken
        with held(second, wait=False) as other:
            assert not other  # a separate open file: excluded like another process
    with held(second, wait=False) as again:
        assert again


def test_file_lock_excludes_another_process(tmp_path: Path) -> None:
    path = tmp_path / "locks" / "ingest.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        assert not FileLock(path).acquire(wait=False)
    finally:
        holder.communicate("go\n", timeout=10)
    lock = FileLock(path)
    assert lock.acquire(wait=False)
    lock.release()


def test_one_file_lock_shared_by_threads_serialises_them(tmp_path: Path) -> None:
    lock, inside, overlaps = FileLock(tmp_path / "t.lock"), [0], [0]

    def work() -> None:
        for _ in range(50):
            with held(lock):
                inside[0] += 1
                overlaps[0] = max(overlaps[0], inside[0])
                inside[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlaps[0] == 1
    with held(FileLock(tmp_path / "t.lock"), wait=False) as free:
        assert free  # every thread released it


def test_thread_lock_and_memory_backend_locks() -> None:
    lock = ThreadLock()
    assert lock.acquire(wait=False) and not lock.acquire(wait=False)
    lock.release()
    backend = MemoryBackend()
    assert backend.lock("ingest") is backend.lock("ingest")
    assert backend.lock("ingest") is not backend.lock("other")


@pytest.mark.parametrize("kind", ["memory", "local"])
def test_exclusive_run_fails_fast_or_waits(kind: str, tmp_path: Path) -> None:
    backend = MemoryBackend() if kind == "memory" else LocalBackend(tmp_path / "data")
    with exclusive_run(backend):
        with pytest.raises(RunLockedError, match="--wait"), exclusive_run(backend):
            pass  # pragma: no cover - never entered
        order: list[str] = []
        waiter = threading.Thread(target=lambda: _queued(backend, order))
        waiter.start()
        order.append("first done")
    waiter.join(timeout=10)
    assert order == ["first done", "second ran"]
    with exclusive_run(backend):  # free again
        pass


def _queued(backend: MemoryBackend | LocalBackend, order: list[str]) -> None:
    with exclusive_run(backend, wait=True):
        order.append("second ran")


def test_local_backend_lock_lives_under_the_data_root(tmp_path: Path) -> None:
    lock = LocalBackend(tmp_path / "data").lock("ingest")
    assert lock.path == tmp_path / "data" / "locks" / "ingest.lock"
    with pytest.raises(ValueError, match="invalid storage key"):
        LocalBackend(tmp_path).lock("../x")
