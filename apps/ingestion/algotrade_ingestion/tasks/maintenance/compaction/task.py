"""The ``compact-runs`` task (ADR 0078): replace a merge table's per-partition run files by the
rows that matter, value for value, so the volume holds less and no read can tell.

``algotrade-ingest run compact-runs --table T [--from D --to D] [--limit N] [--workers N]
[--beside-ingest] [--dry-run [--verify]]``. Only the tables of ``nightly.toml [compaction]
tables`` (a fitness test keeps them merge-mode with no history copy); any other is refused.
``TableStore.compact_runs`` does the work of one partition (a compare-and-swap of its index that
moves no sequence); this task is the gentle caller, and ``pool.py`` runs it:

- ``[compaction] workers`` (default 4, ``--workers N``) worker processes take the partitions
  oldest first, one each, at background CPU and disk priority with one Arrow thread (``pool.py``);
- no worker takes a lock: a writer committing meanwhile makes the swap refuse (the index moved)
  and a pending one makes it raise ``PartitionBusyError``: the partition is skipped with the
  reason, nothing swapped, the new files discarded, and the next run retries. The parent holds
  the ``ingest-tree`` lock for the whole run (never waited for), so the ingest-tree sync cannot
  move this checkout, and probes the ``ingest`` lock before every dispatch and every sweep: a
  nightly or a backfill holding it stops the dispatch (the partitions in flight finish, each
  bounded by ``partition_seconds``) and the rest is left for the next run. ``--beside-ingest``
  skips the probe: the compaction then runs beside an ingest. Opt-in, off by default: a writer
  that stages a partition's file while a worker plans it is protected by the journal re-read
  and the swap's refusal (ADR 0078 amendment 2026-10-20), but the job competes with the ingest
  for disk and CPU, and a nightly that overran its window is the last moment to add load;
- before each dispatch the free disk must cover ``[resources] min_free_gb`` plus one partition
  of scratch per worker (the largest seen; the first is measured by a dry run);
- a swap leaves the superseded files for the rolling sweep (``sweep.py``): each swapped
  partition is swept once 30 s (``SWAP_GRACE_S``) + 1 s have passed, as the run goes, and once
  more at the end; a partition that needed no swap is swept at once;
- ``partition_seconds`` bounds each partition: planning and verifying stop at it (the partition
  is skipped with "verification over budget", nothing swapped, new files discarded), a partition
  that took longer in total (a slow disk) stops the run, and a worker silent for 60 s more
  stops it with the pool terminated;
- SIGINT / SIGTERM stop the dispatch and terminate the workers (a partition in flight discards
  its files); the sweep is left for the next run. Only the parent writes stderr: one
  ``[wN] day ...`` line per partition and a summary every minute (done / total, rate, ETA).

``--limit N`` counts the partitions compacted plus those in flight. ``--dry-run`` writes nothing,
takes no lock, and reports per-partition files and bytes before and after, the runs dropped, the
partitions it would skip and why, and the estimated saving, through the same pool. It plans only
(fast) unless ``--verify``, which also runs the verification a live run does (the slow part:
minutes on a partition of many runs) in memory; the report and a progress line say which it did.
The report is the task's printed summary; no run record is saved (it would move
``runs_generation`` and evict every cached page) and no table is published. The ``deploy`` lock
is not taken, a serving deploy runs from the release tree (ADR 0079).
"""

from collections.abc import Callable
from concurrent.futures import Executor
from datetime import date
from time import monotonic, time
from time import sleep as nap

from algotrade.config.site.nightly import CompactionSettings, NightlySettings
from algotrade.config.site.settings import load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.jobs.exclusive import INGEST_TREE_LOCK, RunLockedError, exclusive_run
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.local_index import SWAP_GRACE_S
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.compaction.pool import Plan, Pool, spawn_executor
from algotrade_ingestion.tasks.maintenance.compaction.report import GB, to_stderr

TASK = "compact-runs"


def settings_of(ctx: TaskContext) -> tuple[CompactionSettings, float]:
    """``[compaction]`` and ``[resources] min_free_gb`` of ``nightly.toml``."""
    nightly = load_nightly(ctx.configs) if ctx.configs is not None else NightlySettings()
    return nightly.compaction, nightly.min_free_gb


def store_url(ctx: TaskContext) -> str:
    """The URL a worker opens the store by (``file://`` only: a worker is another process)."""
    backend = ctx.writer.backend
    if not isinstance(backend, LocalBackend):
        raise ConfigurationError("compact-runs needs a local (file://) store: its workers open it")
    return f"file://{backend.root.resolve()}"


def compact(
    ctx: TaskContext,
    session: date,
    table: str,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    verify: bool = False,
    workers: int | None = None,
    beside_ingest: bool = False,
    progress: Callable[[str], None] = to_stderr,
    swap_grace_s: float = SWAP_GRACE_S,
    make_executor: Callable[[Plan], Executor] = spawn_executor,
    sleep: Callable[[float], None] = nap,
    clock: Callable[[], float] = monotonic,
    wall: Callable[[], float] = time,
) -> RunRecord:
    """Compact ``table``'s partitions in ``start``..``end`` (oldest first) as the module says.
    ``swap_grace_s``, ``make_executor``, ``sleep``, ``clock`` and ``wall`` are seams for tests
    (a shorter grace, threads, no waiting, a fake clock)."""
    cfg, min_free_gb = settings_of(ctx)
    if table not in cfg.tables:
        raise ConfigurationError(
            f"{table} is not in nightly.toml [compaction] tables ({', '.join(cfg.tables)}): only "
            "merge-mode tables without a history copy may be listed (ADR 0078)"
        )
    if workers is not None and workers < 1:
        raise ConfigurationError(f"--workers must be at least 1, not {workers}")
    days = [
        d
        for d in sorted(ctx.reader.dates(table))
        if (start is None or d >= start) and (end is None or d <= end)
    ]
    plan = Plan(
        store_url(ctx),
        table,
        workers or cfg.workers,
        cfg.partition_seconds,
        cfg.nice,
        cfg.worker_arrow_threads,
        swap_grace_s,
        dry_run,
        verify,
    )
    with IngestRun(ctx, TASK, session, save=False) as run:  # no run record: a saved one would
        # move runs_generation and evict every cached page (ADR 0078 decisions 1 and 5)
        run.stats.update(
            table=table,
            dry_run=dry_run,
            partitions_in_range=len(days),
            workers=plan.workers,
            beside_ingest=beside_ingest,
        )
        progress(f"compact-runs {table}: {len(days)} partitions in range, {plan.workers} workers")
        if dry_run:
            run.stats["verified"] = verify
            progress(f"compact-runs dry run: {'plan and verify' if verify else 'plan only'}")
        job = Pool(
            ctx.writer,
            plan,
            min_free_gb * GB,
            beside_ingest,
            progress,
            make_executor,
            clock,
            wall,
            sleep,
        )
        try:  # the ingest-tree sync must not rewrite this checkout between partitions
            if dry_run:  # writes nothing: no lock
                job.run(days, limit)
            else:
                with exclusive_run(ctx.writer.backend, INGEST_TREE_LOCK, wait=False):
                    job.run(days, limit)
        except RunLockedError:
            job.stopped = "the ingest tree is being synced (the ingest-tree lock is held)"
        if job.stopped:
            run.stats["stopped"] = job.stopped
            run.partial(job.stopped)
        run.stats.update(job.totals.stats())
    return run.record
