"""The rolling sweep of ``compact-runs`` (ADR 0078 amendment 2026-10-20): a swapped partition's
superseded files are removed once ``grace + 1 s`` have passed since the parent saw the swap, one
partition at a time as the run goes, and once more at the end; never earlier, whatever the files'
modification times say (a failed ``utime`` leaves them old, the wait is the parent's own).
Correctness never depends on the wait: a read that lost a file retries (``StaleSnapshotError``).
Only the parent sweeps, so a partition a worker holds is never swept (it is not queued)."""

from collections import deque
from collections.abc import Callable
from datetime import date

from algotrade.storage.tables.interfaces import PartitionBusyError
from algotrade.storage.tables.writers import StoreWriter

MARGIN_S = 1.0  # past the grace, so the stamped modification time is surely under the cutoff


class RollingSweep:
    """The partitions waiting for their grace, and the sweeping of those whose time came."""

    def __init__(
        self,
        writer: StoreWriter,
        table: str,
        grace_s: float,
        wall: Callable[[], float],
    ) -> None:
        self.writer, self.table, self.grace_s, self.wall = writer, table, grace_s, wall
        self.waiting: deque[tuple[date, float]] = deque()  # (day, wall time it may be swept)
        self.swept_files = 0
        self.deferred: list[date] = []  # a pending run wrote there: a later run sweeps

    def after_swap(self, day: date) -> None:
        """A partition was swapped just now (the parent saw it at ``wall()``)."""
        self.waiting.append((day, self.wall() + self.grace_s + MARGIN_S))

    def at_once(self, day: date) -> None:
        """A partition needed no swap: leftovers of an earlier crash or stop are due now."""
        self.waiting.append((day, self.wall()))

    @property
    def pending(self) -> int:
        return len(self.waiting)

    def has_due(self) -> bool:
        now = self.wall()
        return any(at <= now for _, at in self.waiting)

    def sweep_due(self) -> int:
        """Sweep every partition whose time has come; -> files removed."""
        now, removed = self.wall(), 0
        for _ in range(len(self.waiting)):
            day, at = self.waiting.popleft()
            if at > now:
                self.waiting.append((day, at))
                continue
            removed += self._sweep(day)
        return removed

    def sweep_all(self, sleep: Callable[[float], None]) -> int:
        """The end of the run: wait out the longest remaining wait once, sweep everything."""
        if not self.waiting:
            return 0
        sleep(max(0.0, max(at for _, at in self.waiting) - self.wall()))
        removed = 0
        while self.waiting:
            removed += self._sweep(self.waiting.popleft()[0])
        return removed

    def _sweep(self, day: date) -> int:
        try:
            removed = self.writer.sweep_orphans(self.table, day)
        except PartitionBusyError:
            self.deferred.append(day)
            return 0
        self.swept_files += removed
        return removed
