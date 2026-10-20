"""The ``compact-runs`` task (ADR 0078): replace a merge table's per-partition run files by the
rows that matter, value for value, so the volume holds less and no read can tell.

``algotrade-ingest run compact-runs --table T [--from D --to D] [--limit N] [--dry-run]``.
Only the tables of ``nightly.toml [compaction] tables`` (a fitness test keeps them merge-mode
with no history copy); any other is refused. ``TableStore.compact_runs`` does the work of one
partition (a compare-and-swap of its index that moves no sequence); this task is the gentle
caller:

- partitions oldest first, one at a time, under the ``ingest`` lock taken without waiting for
  that partition only: a nightly or a backfill holding it stops the run (resume later, done
  partitions are no-ops), and the job never blocks the nightly's start for longer than one
  partition;
- background CPU priority (``os.nice``) and a pause between partitions;
- before each partition the free disk must cover ``[resources] min_free_gb`` plus one
  partition of scratch (the largest seen; the first is measured by a dry run);
- a swap leaves the superseded files for ``sweep_orphans`` once their grace has passed: a batch
  is compacted, the remaining grace is waited out once, then the batch is swept; a partition
  that needed no swap is swept at once (leftovers of an earlier crash or stop);
- ``partition_seconds`` bounds each partition: planning and verifying stop at it (the partition
  is skipped with "verification over budget", nothing swapped, new files discarded), and a
  partition that took longer in total (a slow disk) stops the run;
- one progress line per partition and per sweep goes to stderr, flushed, from the first
  partition (a long run must not look dead).

``--limit N`` stops after N partitions were compacted. ``--dry-run`` writes nothing, takes no
lock, and reports per-partition files and bytes before and after, the runs dropped, the
partitions it would skip and why, and the estimated saving. It plans only (fast) unless
``--verify``, which also runs the verification a live run does (the slow part: minutes on a
partition of many runs) in memory; the report and a progress line say which it did. The report
is the task's printed summary; no run record is saved (it would move ``runs_generation`` and
evict every cached page) and no table is published. The ``deploy`` lock is held for the whole
run (ADR 0057),
never waited for.
"""

import contextlib
import ctypes
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from time import monotonic
from time import sleep as nap

from algotrade.config.site.nightly import CompactionSettings, NightlySettings
from algotrade.config.site.settings import load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.jobs.exclusive import (
    DEPLOY_LOCK,
    INGEST_LOCK,
    RunLockedError,
    exclusive_run,
)
from algotrade.storage.backends.run_compaction import OVER_BUDGET
from algotrade.storage.locks import held
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import CompactionReport, PartitionBusyError
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "compact-runs"
GB = 1e9
LOCK_HELD = "the ingest lock is held (a nightly or a backfill is running)"
SHOWN = 20  # partitions listed one by one in the run record (the totals count them all)


def settings_of(ctx: TaskContext) -> tuple[CompactionSettings, float]:
    """``[compaction]`` and ``[resources] min_free_gb`` of ``nightly.toml``."""
    nightly = load_nightly(ctx.configs) if ctx.configs is not None else NightlySettings()
    return nightly.compaction, nightly.min_free_gb


def to_stderr(line: str) -> None:
    """The default progress sink: one flushed line on stderr (the log of a detached run)."""
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def describe(day: date, report: CompactionReport, seconds: float) -> str:
    """One partition's progress line."""
    if report.skipped:
        return f"compact-runs {day}: skipped ({report.skipped}) in {seconds:.1f} s"
    return (
        f"compact-runs {day}: files {report.files_before} -> {report.files_after}, "
        f"bytes {report.bytes_before} -> {report.bytes_after}, "
        f"{report.runs_dropped} runs dropped, {seconds:.1f} s"
    )


IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_THROTTLE = 1, 0, 3  # <sys/resource.h> (darwin)


def lower_priority(nice: int) -> None:
    """Take on background CPU and (darwin) disk priority for the rest of this process (the
    CLI's); never raises: a platform without the calls just runs at normal priority."""
    with contextlib.suppress(OSError):
        if nice > 0:
            os.nice(nice)
    if sys.platform == "darwin":
        with contextlib.suppress(OSError, AttributeError):
            libc = ctypes.CDLL(None, use_errno=True)
            libc.setiopolicy_np(IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_THROTTLE)


@dataclass
class Totals:
    """What the run did, summed over partitions."""

    compacted: int = 0
    unchanged: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    files_before: int = 0
    files_after: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    runs_dropped: int = 0
    swept_files: int = 0
    partitions: list[dict[str, object]] = field(default_factory=list)

    def add(self, day: date, report: CompactionReport) -> bool:
        """Count one partition's report; whether it changes (or would change) anything."""
        if report.skipped:
            self.skipped[report.skipped] = self.skipped.get(report.skipped, 0) + 1
            return False
        if report.files_after == report.files_before and report.bytes_after == report.bytes_before:
            self.unchanged += 1
            return False
        self.compacted += 1
        self.files_before += report.files_before
        self.files_after += report.files_after
        self.bytes_before += report.bytes_before
        self.bytes_after += report.bytes_after
        self.runs_dropped += report.runs_dropped
        if len(self.partitions) < SHOWN:
            self.partitions.append(
                {
                    "session": day.isoformat(),
                    "files": [report.files_before, report.files_after],
                    "bytes": [report.bytes_before, report.bytes_after],
                    "runs_dropped": report.runs_dropped,
                }
            )
        return True

    def stats(self) -> dict[str, object]:
        return {
            "compacted": self.compacted,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "files_before": self.files_before,
            "files_after": self.files_after,
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
            "saving_bytes": self.bytes_before - self.bytes_after,
            "runs_dropped": self.runs_dropped,
            "swept_files": self.swept_files,
            "partitions": self.partitions,
        }


class Compactor:
    """One run's loop: compacts partitions one at a time and sweeps what the swaps superseded."""

    def __init__(
        self,
        ctx: TaskContext,
        table: str,
        cfg: CompactionSettings,
        floor_bytes: float,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
        progress: Callable[[str], None] = to_stderr,
    ) -> None:
        self.ctx, self.table, self.cfg, self.floor = ctx, table, cfg, floor_bytes
        self.sleep, self.clock, self.progress = sleep, clock, progress
        self.totals = Totals()
        self.stopped: str | None = None
        self.lock_busy = False  # the ingest lock was held: wait for nothing, a later run sweeps
        self.scratch = 0  # the largest partition seen, in bytes
        self.swapped: list[date] = []  # compacted this batch, not yet swept
        self.last_swap = 0.0

    def run(self, days: list[date], limit: int | None) -> None:
        for day in days:
            if limit is not None and self.totals.compacted >= limit:
                break
            if len(self.swapped) >= self.cfg.batch_size:
                self.flush()
            swaps = self.totals.compacted
            if self.stopped or not self.partition(day):
                break
            if self.totals.compacted > swaps:  # a no-op partition costs no I/O: no pause
                self.sleep(self.cfg.pause_seconds)
        self.flush()

    def partition(self, day: date) -> bool:
        """Compact (or sweep) one partition; ``False`` stops the run (the reason is set)."""
        writer = self.ctx.writer
        if not self.room(day):
            return False
        started = self.clock()
        with held(writer.backend.lock(INGEST_LOCK), wait=False) as taken:
            if not taken:
                self.stopped, self.lock_busy = LOCK_HELD, True
                return False
            try:
                report = writer.compact_runs(self.table, day, budget_s=self.cfg.partition_seconds)
            except PartitionBusyError:
                report = CompactionReport(skipped="a pending run is writing the partition")
            self.scratch = max(self.scratch, report.bytes_before)
            if self.totals.add(day, report):
                self.swapped.append(day)
                self.last_swap = self.clock()
            else:
                self.totals.swept_files += writer.sweep_orphans(self.table, day)
        seconds = self.clock() - started
        self.progress(describe(day, report, seconds))
        if seconds > self.cfg.partition_seconds and report.skipped != OVER_BUDGET:
            self.stopped = f"{day} took over {self.cfg.partition_seconds:g} s (the disk is slow)"
            return False
        return True

    def room(self, day: date) -> bool:
        """Whether the free disk covers the floor and one partition of scratch."""
        if not self.scratch:  # the first partition: measure it without writing
            self.scratch = self.ctx.writer.compact_runs(self.table, day, dry_run=True).bytes_before
        free = self.ctx.writer.free_bytes()
        if free < self.floor + self.scratch:
            self.stopped = (
                f"{free / GB:.1f} GB free, under the {self.floor / GB:g} GB floor "
                f"plus {self.scratch / GB:.2f} GB of scratch"
            )
            return False
        return True

    def flush(self) -> None:
        """Wait out the swaps' grace once, then sweep the batch (skipped when the ingest lock is
        held: a later run sweeps)."""
        if not self.swapped:
            return
        if not self.lock_busy:
            self.sleep(max(0.0, self.cfg.sweep_grace_seconds - (self.clock() - self.last_swap)))
        writer = self.ctx.writer
        with held(writer.backend.lock(INGEST_LOCK), wait=False) as taken:
            if taken:
                swept = self.totals.swept_files
                for day in self.swapped:
                    self.totals.swept_files += writer.sweep_orphans(self.table, day)
                self.progress(
                    f"compact-runs sweep: {self.totals.swept_files - swept} files of "
                    f"{len(self.swapped)} partitions removed"
                )
                self.swapped = []
            elif self.stopped is None:
                self.stopped, self.lock_busy = LOCK_HELD, True


def dry_run_report(
    ctx: TaskContext,
    table: str,
    days: list[date],
    limit: int | None,
    verify: bool = False,
    budget_s: float | None = None,
    clock: Callable[[], float] = monotonic,
    progress: Callable[[str], None] = to_stderr,
) -> Totals:
    """What a run would do, partition by partition; writes nothing and takes no lock. With
    ``verify`` each partition's plan is also verified (in memory), as a live run does."""
    totals = Totals()
    progress(f"compact-runs dry run: {'plan and verify' if verify else 'plan only'}")
    for day in days:
        if limit is not None and totals.compacted >= limit:
            break
        started = clock()
        report = ctx.writer.compact_runs(table, day, dry_run=True, verify=verify, budget_s=budget_s)
        progress(describe(day, report, clock() - started))
        totals.add(day, report)
    return totals


def compact(
    ctx: TaskContext,
    session: date,
    table: str,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    sleep: Callable[[float], None] = nap,
    clock: Callable[[], float] = monotonic,
    prioritise: Callable[[int], None] = lower_priority,
    verify: bool = False,
    progress: Callable[[str], None] = to_stderr,
) -> RunRecord:
    """Compact ``table``'s partitions in ``start``..``end`` (oldest first) as the module says."""
    cfg, min_free_gb = settings_of(ctx)
    if table not in cfg.tables:
        raise ConfigurationError(
            f"{table} is not in nightly.toml [compaction] tables ({', '.join(cfg.tables)}): only "
            "merge-mode tables without a history copy may be listed (ADR 0078)"
        )
    days = [
        d
        for d in sorted(ctx.reader.dates(table))
        if (start is None or d >= start) and (end is None or d <= end)
    ]
    with IngestRun(ctx, TASK, session, save=False) as run:  # no run record: a saved one would
        # move runs_generation and evict every cached page (ADR 0078 decisions 1 and 5)
        run.stats.update(table=table, dry_run=dry_run, partitions_in_range=len(days))
        progress(f"compact-runs {table}: {len(days)} partitions in range")
        if dry_run:
            run.stats["verified"] = verify
            totals = dry_run_report(
                ctx, table, days, limit, verify, cfg.partition_seconds, clock, progress
            )
        else:
            prioritise(cfg.nice)
            job = Compactor(ctx, table, cfg, min_free_gb * GB, sleep, clock, progress)
            try:  # a deploy must not run between partitions (ADR 0057): hold its lock throughout
                with exclusive_run(ctx.writer.backend, DEPLOY_LOCK, wait=False):
                    job.run(days, limit)
            except RunLockedError:
                job.stopped = "a deploy is running (the deploy lock is held)"
            totals = job.totals
            if job.stopped:
                run.stats["stopped"] = job.stopped
                run.partial(job.stopped)
        run.stats.update(totals.stats())
    return run.record
