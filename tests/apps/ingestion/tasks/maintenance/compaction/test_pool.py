"""The pool of ``compact-runs`` (ADR 0078 amendment 2026-10-20): real worker processes on adjacent
days beside a committing writer, a killed worker, an ingest lock taken mid-run, SIGTERM, a worker
that goes silent or raises, and readers that never notice the sweeps."""

import multiprocessing
import os
import signal
import subprocess
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.jobs.exclusive import INGEST_LOCK
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.local_index import _named, read_index
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import CompactionReport, PartitionBusyError
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.compaction import pool, task
from algotrade_ingestion.tasks.maintenance.compaction.pool import (
    LOCK_HELD,
    Outcome,
    Plan,
    Pool,
    spawn_executor,
    thread_executor,
)
from tests.helpers.compaction.store import (
    BASE,
    SESSION,
    TABLE,
    context,
    days_from,
    die_before_the_swap,
    fill,
    leftovers,
    partition_dir,
    put,
    rows_of,
    run_job,
)
from tests.helpers.ingest_fakes import task_ctx

DAYS = days_from(4)


@pytest.fixture
def backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / "data")


def plan_for(backend: LocalBackend, workers: int = 1, **kw: Any) -> Plan:
    fields: dict[str, Any] = {"budget_s": 300.0, "swap_grace_s": 0.0, **kw}
    return Plan(f"file://{backend.root}", TABLE, workers, nice=0, arrow_threads=1, **fields)


def job(ctx: TaskContext, **kw: Any) -> dict[str, Any]:
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("make_executor", thread_executor)
    kw.setdefault("progress", lambda line: None)
    return dict(task.compact(ctx, SESSION, TABLE, swap_grace_s=0.0, **kw).stats)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def children_of(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False)
    return [int(p) for p in out.stdout.split()]


def indexed_only(root: Path, day: date) -> bool:
    """Every run file of the partition is one its index names (nothing left to sweep)."""
    directory = partition_dir(root, day)
    named = _named(read_index(directory))
    return {p.name for p in directory.glob("run=*.parquet")} == named


# ----------------------------------------------------------------------------- real processes


def test_real_worker_processes_compact_adjacent_days_beside_a_committing_writer(
    backend: LocalBackend,
) -> None:
    days = days_from(6)
    fill(backend, days)
    committed: dict[str, list[str]] = {d.isoformat(): [] for d in days}
    stop = threading.Event()

    def writer() -> None:  # a backfill committing into the partitions being compacted
        other, n = LocalBackend(backend.root), 0
        while not stop.is_set():
            for day in days[1:5]:
                put(other, day, f"w{n}", {f"EQ:W{n}": 5.0}, 100 + n)
                committed[day.isoformat()].append(f"EQ:W{n}")
                n += 1
            time.sleep(0.02)

    stats: dict[str, Any] = {}

    def run() -> None:
        stats.update(job(context(backend), make_executor=spawn_executor, workers=2))

    thread, runner = threading.Thread(target=writer), threading.Thread(target=run, daemon=True)
    thread.start()
    runner.start()
    runner.join(240)
    stop.set()
    thread.join(30)
    assert not runner.is_alive(), "the job deadlocked"  # no deadlock between workers and writer
    assert "stopped" not in stats and stats["workers"] == 2
    expected = {d: {**BASE, **dict.fromkeys(committed[d], 5.0)} for d in committed}
    assert rows_of(backend, days) == expected  # value-exact, whatever raced
    quiet = job(context(backend), make_executor=spawn_executor, workers=2)  # the next pass
    assert rows_of(backend, days) == expected and "stopped" not in quiet
    assert all(indexed_only(backend.root, d) for d in days)


def test_a_worker_killed_after_writing_before_the_swap_leaves_a_clean_next_pass(
    backend: LocalBackend,
) -> None:
    fill(backend, DAYS)
    before = rows_of(backend, DAYS)
    child = multiprocessing.get_context("spawn").Process(
        target=die_before_the_swap, args=(str(backend.root), DAYS[1].isoformat())
    )
    child.start()
    child.join(120)
    assert child.exitcode == -signal.SIGKILL
    directory = partition_dir(backend.root, DAYS[1])
    assert not indexed_only(backend.root, DAYS[1])  # the fresh files it wrote
    (directory / ".run=zz.parquet.ab12.tmp").write_bytes(b"x")  # a write it died in
    assert rows_of(backend, DAYS) == before
    for path in directory.iterdir():
        os.utime(path, (0, 0))  # a minute and more later
    stats = job(context(backend))
    assert stats["compacted"] == 4 and "stopped" not in stats
    assert rows_of(backend, DAYS) == before
    assert leftovers(backend.root) == [] and all(indexed_only(backend.root, d) for d in DAYS)


def test_sigterm_leaves_no_worker_and_no_temp_file(backend: LocalBackend) -> None:
    days = days_from(12)
    fill(backend, days)
    before = rows_of(backend, days)
    spawn = multiprocessing.get_context("spawn")
    started = spawn.Event()
    child = spawn.Process(target=run_job, args=(str(backend.root), 2, started))
    child.start()
    try:
        assert started.wait(120), "no partition finished"
        assert child.pid is not None
        kids = children_of(child.pid)
        assert kids  # the workers
        os.kill(child.pid, signal.SIGTERM)
        child.join(120)
        assert child.exitcode == 0  # it stopped by itself, not killed by the signal
        deadline = time.monotonic() + 30
        while any(alive(k) for k in kids) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not any(alive(k) for k in kids)
    finally:
        if child.is_alive():
            child.kill()
    assert leftovers(backend.root) == []
    assert rows_of(backend, days) == before
    assert job(context(backend))["compacted"] >= 0  # and the next pass runs


# ----------------------------------------------------------------------------- the logic


def test_an_ingest_lock_taken_mid_run_stops_the_dispatch_and_lets_in_flight_finish(
    backend: LocalBackend,
) -> None:
    fill(backend, DAYS)
    lock = backend.lock(INGEST_LOCK)

    def progress(line: str) -> None:
        if line.startswith("compact-runs [w"):
            lock.acquire(wait=False)  # a nightly starts as the first partition finishes

    try:
        stats = job(context(backend), workers=2, progress=progress)
    finally:
        lock.release()
    assert stats["stopped"] == LOCK_HELD
    assert stats["compacted"] == 2  # the two in flight finished; none was dispatched after
    assert len(read_index(partition_dir(backend.root, DAYS[3]))) == 4  # untouched
    assert len(read_index(partition_dir(backend.root, DAYS[0]))) == 2


def test_a_reader_never_notices_the_sweeps(backend: LocalBackend) -> None:
    days = days_from(8)
    fill(backend, days)
    expected = rows_of(backend, days)
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader() -> None:
        mine = LocalBackend(backend.root)
        try:
            while not stop.is_set():
                frame = mine.tables.read_range(TABLE, days[0], days[-1])
                assert frame is not None and len(frame) == 3 * len(days)
                assert set(frame["cash_amount"]) == {1.0}
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    try:
        stats = job(context(backend), workers=2)  # a zero grace: swept as soon as it can be
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert stats["compacted"] == 8 and stats["swept_files"] >= 16
    assert not errors and rows_of(backend, days) == expected


def test_a_silent_worker_stops_the_run_and_the_pool(
    backend: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill(backend, DAYS)
    release = threading.Event()
    monkeypatch.setattr(pool, "work", lambda day: release.wait(30))
    monkeypatch.setattr(pool, "POLL_S", 0.05)
    run = Pool(
        StoreWriter(backend), plan_for(backend), 0, make_executor=thread_executor, silent_s=0.2,
        progress=lambda line: None,
    )  # fmt: skip
    try:
        run.run(DAYS, None)
    finally:
        release.set()
    assert run.stopped is not None and "silent" in run.stopped
    assert run.totals.compacted == 0


def test_a_worker_that_raises_stops_the_run_with_its_error(
    backend: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill(backend, DAYS)

    def boom(day: date) -> Outcome:
        raise RuntimeError("the disk is gone")

    monkeypatch.setattr(pool, "work", boom)
    run = Pool(StoreWriter(backend), plan_for(backend), 0, make_executor=thread_executor)
    with pytest.raises(RuntimeError, match="the disk is gone"):
        run.run(DAYS, None)


def test_a_signal_stops_the_dispatch_and_restores_the_handlers(backend: LocalBackend) -> None:
    fill(backend, DAYS)
    before = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)

    def progress(line: str) -> None:
        if line.startswith("compact-runs [w"):
            os.kill(os.getpid(), signal.SIGTERM)

    stats = job(context(backend), workers=1, progress=progress)
    assert stats["stopped"] == "interrupted (SIGTERM)" and stats["compacted"] == 1
    assert stats["swept_files"] == 0  # the sweep is left for the next run
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == before
    assert job(context(backend), workers=1)["compacted"] == 3  # the next run takes the rest


def test_a_summary_is_printed_each_minute(backend: LocalBackend) -> None:
    fill(backend, DAYS)
    ticks = iter(range(0, 10_000, 61))  # every look at the clock is 61 s later
    lines: list[str] = []
    run = Pool(
        StoreWriter(backend), plan_for(backend), 0, make_executor=thread_executor,
        progress=lines.append, clock=lambda: float(next(ticks)), silent_s=1e9,
    )  # fmt: skip
    run.run(DAYS, None)
    summary = [line for line in lines if "partitions," in line]
    assert summary and "ETA" in summary[0] and "sweeps pending" in summary[0]


def test_the_limit_counts_the_partitions_in_flight(backend: LocalBackend) -> None:
    fill(backend, DAYS)
    stats = job(context(backend), workers=4, limit=1)
    assert stats["compacted"] == 1  # one dispatched, not four


def test_free_space_must_cover_a_partition_of_scratch_per_worker(backend: LocalBackend) -> None:
    fill(backend, DAYS)
    writer = StoreWriter(backend)
    scratch = writer.compact_runs(TABLE, DAYS[0], dry_run=True).bytes_before
    writer.free_bytes = lambda: 3 * scratch  # type: ignore[method-assign]
    run = Pool(writer, plan_for(backend, workers=4), 0, make_executor=thread_executor)
    run.run(DAYS, None)
    assert run.stopped is not None and "scratch" in run.stopped and run.totals.compacted == 0
    writer.free_bytes = lambda: 4 * scratch  # type: ignore[method-assign]
    ok = Pool(writer, plan_for(backend, workers=4), 0, make_executor=thread_executor)
    ok.run(DAYS, None)
    assert ok.stopped is None and ok.totals.compacted == 4


def test_a_dry_run_uses_the_pool_and_writes_nothing(backend: LocalBackend) -> None:
    fill(backend, DAYS)
    before = sorted(p.name for p in backend.root.rglob("*.parquet"))
    stats = job(context(backend), dry_run=True, workers=2)
    assert stats["compacted"] == 4 and stats["workers"] == 2 and "stopped" not in stats
    assert sorted(p.name for p in backend.root.rglob("*.parquet")) == before


def test_a_worker_reports_a_busy_partition_as_skipped(
    backend: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill(backend, DAYS[:1])
    pool.init_worker(plan_for(backend), os.getpid(), process=False)

    def busy(*args: object, **kwargs: object) -> CompactionReport:
        raise PartitionBusyError("pending")

    monkeypatch.setattr(StoreWriter, "compact_runs", busy)
    outcome = pool.work(DAYS[0])
    assert outcome.report.skipped == "a pending run is writing the partition"


def test_a_worker_takes_the_swap_grace_of_its_plan(backend: LocalBackend) -> None:
    fill(backend, DAYS[:1])
    pool.init_worker(plan_for(backend, swap_grace_s=7.0), os.getpid(), process=False)
    writer = pool._state["worker"][1]
    assert writer.backend.tables.swap_grace_s == 7.0  # type: ignore[attr-defined]


def test_only_a_local_store_can_be_compacted_by_workers() -> None:
    with pytest.raises(ConfigurationError, match="local"):
        task.store_url(task_ctx(StoreWriter(MemoryBackend())))


def test_the_default_executor_is_a_spawn_pool_that_ends_with_the_run(
    backend: LocalBackend,
) -> None:
    fill(backend, DAYS[:2])
    stats = job(context(backend), make_executor=spawn_executor, workers=2)
    assert stats["compacted"] == 2 and "stopped" not in stats
