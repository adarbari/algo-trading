"""``RollingSweep`` (ADR 0078 amendment 2026-10-20): a swapped partition is swept no sooner than
grace + 1 s after the parent saw the swap, whatever its files' modification times say, and the
end of the run waits out the rest once."""

import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.runs import local_index
from algotrade.storage.tables.interfaces import PartitionBusyError
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.compaction.sweep import RollingSweep
from tests.helpers.compaction.store import TABLE, fill, partition_dir

DAYS = [date(2026, 9, 1), date(2026, 9, 2)]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Spy:
    """A writer whose sweeps are recorded with the fake time they happened at."""

    def __init__(self, writer: StoreWriter, clock: Clock) -> None:
        self.writer, self.clock = writer, clock
        self.calls: list[tuple[date, float]] = []

    def sweep_orphans(self, table: str, day: date) -> int:
        self.calls.append((day, self.clock.now))
        return self.writer.sweep_orphans(table, day)


def sweeper(writer: Any, clock: Clock, grace: float = 30.0) -> RollingSweep:
    return RollingSweep(writer, TABLE, grace, clock)


@pytest.fixture
def store(tmp_path: Path) -> LocalBackend:
    backend = LocalBackend(tmp_path)
    fill(backend, DAYS)
    return backend


def test_a_swapped_partition_is_swept_only_after_the_grace_and_a_second(
    store: LocalBackend,
) -> None:
    clock = Clock()
    spy = Spy(StoreWriter(store), clock)
    sweep = sweeper(spy, clock)
    sweep.after_swap(DAYS[0])
    clock.now += 30.9
    assert not sweep.has_due() and sweep.sweep_due() == 0 and spy.calls == []
    clock.now += 0.2  # 31.1 s after the swap
    assert sweep.has_due() and sweep.pending == 1
    sweep.sweep_due()
    assert [d for d, _ in spy.calls] == [DAYS[0]] and sweep.pending == 0
    assert spy.calls[0][1] >= 1031.0  # never before the swap + grace + 1 s


def test_a_partition_that_needed_no_swap_is_due_at_once(store: LocalBackend) -> None:
    sweep = sweeper(StoreWriter(store), Clock())
    sweep.at_once(DAYS[0])
    assert sweep.has_due()


def test_each_partition_waits_for_its_own_swap_time(store: LocalBackend) -> None:
    clock = Clock()
    spy = Spy(StoreWriter(store), clock)
    sweep = sweeper(spy, clock)
    sweep.after_swap(DAYS[0])
    clock.now += 20
    sweep.after_swap(DAYS[1])
    clock.now += 12  # 32 s after the first, 12 s after the second
    sweep.sweep_due()
    assert [d for d, _ in spy.calls] == [DAYS[0]] and sweep.pending == 1


def test_the_end_of_the_run_waits_out_the_longest_remaining_wait_once(
    store: LocalBackend,
) -> None:
    clock = Clock()
    sweep = sweeper(StoreWriter(store), clock)
    sweep.after_swap(DAYS[0])
    clock.now += 10
    sweep.after_swap(DAYS[1])
    slept: list[float] = []
    sweep.sweep_all(slept.append)
    assert slept == [pytest.approx(31.0)] and sweep.pending == 0


def test_a_failing_utime_does_not_make_the_sweep_early(
    store: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The superseded files keep their old modification time when ``utime`` fails, so
    ``sweep_orphans`` would take them at once; the parent's own wait is what spares them."""

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("utime")

    clock = Clock()
    for path in partition_dir(store.root, DAYS[0]).glob("*.parquet"):
        os.utime(path, (0, 0))  # old files, as they stay when the stamp fails
    monkeypatch.setattr(local_index.os, "utime", broken)
    writer = StoreWriter(store)
    assert writer.compact_runs(TABLE, DAYS[0]).runs_dropped == 2
    spy = Spy(writer, clock)
    sweep = sweeper(spy, clock)
    sweep.after_swap(DAYS[0])
    clock.now += 29
    assert sweep.sweep_due() == 0 and spy.calls == []
    directory = partition_dir(store.root, DAYS[0])
    assert (directory / "run=0901r2.parquet").exists()  # the superseded files are still there
    assert (directory / "run=0901r3.parquet").exists()


def test_a_partition_a_pending_run_wrote_to_is_left_for_the_next_run() -> None:
    class Busy:
        def sweep_orphans(self, table: str, day: date) -> int:
            raise PartitionBusyError(str(day))

    sweep = sweeper(Busy(), Clock(), 0.0)
    sweep.at_once(DAYS[0])
    assert sweep.sweep_due() == 0 and sweep.deferred == [DAYS[0]] and sweep.pending == 0
