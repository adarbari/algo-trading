"""The worker processes of ``compact-runs`` and the parent's dispatch loop (ADR 0078 amendment
2026-10-20).

Workers (``spawn``, never ``fork``: the parent holds locks and Arrow pools) each open their own
backend from the data URL, take background CPU and disk priority and one Arrow thread, ignore
SIGINT (the parent decides), turn SIGTERM into ``SystemExit`` (so a partition in flight discards
the files it wrote), and exit when their parent does. A worker takes no lock: ``swap_runs`` (a
compare-and-swap under the commit lock) and ``PartitionBusyError`` already protect a partition
from a writer. The parent holds the ``ingest-tree`` lock for the run, and, unless
``beside_ingest``, probes the ``ingest`` lock (taken without waiting, released at once) before
every dispatch and every sweep: a held lock stops the dispatch, the partitions in flight finish
(each bounded by ``partition_seconds``) and the rest is left for the next run.

The parent dispatches the days oldest first, one per worker at a time (so the free space and
``--limit`` are checked against what is in flight), sweeps as it goes (``sweep.py``), writes every
line of progress (a worker never writes stderr) and a summary each minute. A worker silent for
``partition_seconds + 60`` s stops the run (the pool is terminated); SIGINT / SIGTERM stop the
dispatch, terminate the workers and leave the sweep to the next run.
"""

import contextlib
import ctypes
import os
import signal
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import (
    FIRST_COMPLETED,
    Executor,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from multiprocessing import get_context
from time import monotonic, time
from time import sleep as nap
from types import FrameType
from typing import Any

from algotrade.services.jobs.exclusive import INGEST_LOCK
from algotrade.storage.backends.arrow_memory import limit_threads
from algotrade.storage.backends.run_compaction import OVER_BUDGET, CompactionVerificationError
from algotrade.storage.factory import open_backend
from algotrade.storage.locks import held
from algotrade.storage.tables.interfaces import CompactionReport, PartitionBusyError
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.maintenance.compaction.report import GB, Totals, describe, to_stderr
from algotrade_ingestion.tasks.maintenance.compaction.sweep import RollingSweep

LOCK_HELD = "the ingest lock is held (a nightly or a backfill is running)"
SILENT_EXTRA_S = 60.0  # a worker silent this long past ``partition_seconds`` is dead or stuck
POLL_S = 0.5  # how often the parent looks at the clock, the signals and the lock
SUMMARY_S = 60.0
IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_THROTTLE = 1, 0, 3  # <sys/resource.h> (darwin)


def lower_priority(nice: int) -> None:
    """Take on background CPU and (darwin) disk priority for the rest of this process; never
    raises: a platform without the calls just runs at normal priority."""
    with contextlib.suppress(OSError):
        if nice > 0:
            os.nice(nice)
    if sys.platform == "darwin":
        with contextlib.suppress(OSError, AttributeError):
            libc = ctypes.CDLL(None, use_errno=True)
            libc.setiopolicy_np(IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_THROTTLE)


@dataclass(frozen=True)
class Plan:
    """What every worker needs, picklable: the store by URL (a worker opens its own backend)."""

    url: str
    table: str
    workers: int
    budget_s: float  # one partition's planning and verifying
    nice: int
    arrow_threads: int
    swap_grace_s: float
    dry_run: bool = False
    verify: bool = False


@dataclass(frozen=True)
class Outcome:
    """What a worker sends back for one partition."""

    day: date
    report: CompactionReport
    seconds: float
    worker: str  # which worker (a process, or a thread of the in-process test seam)


# ----------------------------------------------------------------------------- the worker side

_state: dict[str, tuple[Plan, StoreWriter]] = {}  # "worker" -> this worker's plan and store


def init_worker(plan: Plan, parent_pid: int, process: bool = True) -> None:
    """A worker's start: its own backend, background priority, one Arrow thread, signals and
    the parent watch. ``process=False`` (threads, the in-process test seam) does none of the
    process-wide parts."""
    backend = open_backend(plan.url)
    if hasattr(backend.tables, "swap_grace_s"):  # the local backend's
        backend.tables.swap_grace_s = plan.swap_grace_s
    _state["worker"] = (plan, StoreWriter(backend))
    if not process:
        return
    lower_priority(plan.nice)
    limit_threads(plan.arrow_threads, plan.arrow_threads)
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the parent decides (and sends SIGTERM)
    signal.signal(signal.SIGTERM, _terminate)
    threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()


def _terminate(signum: int, frame: FrameType | None) -> None:
    raise SystemExit(f"terminated by signal {signum}")  # the partition in flight discards


def _watch_parent(parent_pid: int) -> None:
    """Exit (as a SIGTERM would) when the parent is gone: a killed run leaves no workers."""
    while True:
        if os.getppid() != parent_pid:
            os.kill(os.getpid(), signal.SIGTERM)
            return
        nap(2.0)


def work(day: date) -> Outcome:
    """Compact (or, in a dry run, plan) one partition."""
    plan, writer = _state["worker"]
    started = monotonic()
    try:
        report = writer.compact_runs(
            plan.table, day, dry_run=plan.dry_run, verify=plan.verify, budget_s=plan.budget_s
        )
    except PartitionBusyError:
        report = CompactionReport(skipped="a pending run is writing the partition")
    except CompactionVerificationError as exc:  # nothing swapped, new files discarded
        report = CompactionReport(skipped=f"verification failed: {exc}")
    except SystemExit:
        # SIGTERM: the partition already discarded its fresh files (``_compact_runs`` catches
        # BaseException). The pool's own loop would catch this and wait for more work, so the
        # process ends here, as a SIGTERM would (128 + 15).
        os._exit(143)
    return Outcome(day, report, monotonic() - started, f"{os.getpid()}:{threading.get_ident()}")


# ----------------------------------------------------------------------------- the executors


def spawn_executor(plan: Plan) -> Executor:
    """The real pool: ``spawn`` processes."""
    return ProcessPoolExecutor(
        plan.workers,
        mp_context=get_context("spawn"),
        initializer=init_worker,
        initargs=(plan, os.getpid(), True),
    )


def thread_executor(plan: Plan) -> Executor:
    """Threads of this process: the test seam for the logic around the pool (fast, and the
    test can patch what the workers call)."""
    return ThreadPoolExecutor(
        plan.workers, initializer=init_worker, initargs=(plan, os.getpid(), False)
    )


def stop_children(executor: Executor, grace_s: float = 10.0) -> None:
    """SIGTERM the worker processes (their partition discards its files), then SIGKILL the
    ones still alive after ``grace_s``; threads have no such thing."""
    processes = list(getattr(executor, "_processes", {}).values())
    for process in processes:
        with contextlib.suppress(OSError, ValueError):
            process.terminate()
    for process in processes:
        process.join(grace_s)
        if process.is_alive():
            with contextlib.suppress(OSError, ValueError):
                process.kill()
            process.join(grace_s)


# ----------------------------------------------------------------------------- the parent side


class Pool:
    """One run: dispatch partitions to the workers, collect, sweep, report."""

    def __init__(
        self,
        writer: StoreWriter,
        plan: Plan,
        floor_bytes: float,
        beside_ingest: bool = False,
        progress: Callable[[str], None] = to_stderr,
        make_executor: Callable[[Plan], Executor] = spawn_executor,
        clock: Callable[[], float] = monotonic,
        wall: Callable[[], float] = time,
        sleep: Callable[[float], None] = nap,
        silent_s: float | None = None,
    ) -> None:
        self.writer, self.plan, self.floor = writer, plan, floor_bytes
        self.beside_ingest, self.progress = beside_ingest, progress
        self.make_executor = make_executor
        self.clock, self.sleep = clock, sleep
        self.silent_s = plan.budget_s + SILENT_EXTRA_S if silent_s is None else silent_s
        self.totals = Totals()
        self.sweeper = RollingSweep(writer, plan.table, plan.swap_grace_s, wall)
        self.stopped: str | None = None
        self.scratch = 0  # the largest partition seen, in bytes
        self.failure: BaseException | None = None
        self._flying: dict[Future[Outcome], tuple[date, float]] = {}
        self._names: dict[str, str] = {}
        self._interrupted: str | None = None
        self._executor: Executor | None = None
        self._last_summary = 0.0
        self._total = 0
        self._done = 0

    # ------------------------------------------------------------------ the run

    def run(self, days: list[date], limit: int | None) -> None:
        queue, self._total = deque(days), len(days)
        started = self._last_summary = self.clock()
        executor = self._executor = self.make_executor(self.plan)
        crashed = True
        try:
            with self._signals():
                while True:
                    self._dispatch(queue, limit)
                    if not self._flying:
                        break
                    done, _ = wait(self._flying, timeout=POLL_S, return_when=FIRST_COMPLETED)
                    for future in done:
                        self._collect(future)
                    if self._interrupted or self.failure is not None or self._tick(started):
                        break
            crashed = False
        finally:
            self._finish(executor, crashed)
        if self.failure is not None:
            raise self.failure

    def _finish(self, executor: Executor, crashed: bool) -> None:
        """Stop what is still running (SIGTERM: its partition discards its files), then sweep."""
        aborted = crashed or self._interrupted or self.failure is not None or self._flying
        if aborted:
            stop_children(executor)
        executor.shutdown(wait=not aborted, cancel_futures=True)
        if self._interrupted:
            self.stopped = f"interrupted ({self._interrupted})"
        elif not aborted:
            self._final_sweep()
        self.totals.swept_files = self.sweeper.swept_files
        self.totals.unswept = self.sweeper.pending + len(self.sweeper.deferred)

    # ------------------------------------------------------------------ dispatch

    def _dispatch(self, queue: deque[date], limit: int | None) -> None:
        executor_full = len(self._flying) >= self.plan.workers
        while queue and not self.stopped and not self._interrupted and not executor_full:
            if limit is not None and self.totals.compacted + len(self._flying) >= limit:
                break
            if not self._ingest_free() or not self._room(queue[0]):
                break
            day = queue.popleft()
            try:
                future = self._executor.submit(work, day)  # type: ignore[union-attr]
            except BrokenProcessPool as exc:
                self.stopped = f"a worker process died ({exc})"
                break
            self._flying[future] = (day, self.clock())
            executor_full = len(self._flying) >= self.plan.workers

    def _ingest_free(self) -> bool:
        """``False`` (and the run stops dispatching) when a nightly or a backfill holds the
        ingest lock. The probe takes the lock without waiting and releases it at once."""
        if self.beside_ingest or self.plan.dry_run:
            return True
        with held(self.writer.backend.lock(INGEST_LOCK), wait=False) as taken:
            if taken:
                return True
        self.stopped = LOCK_HELD
        return False

    def _room(self, day: date) -> bool:
        """Whether the free disk covers the floor and a partition of scratch per worker."""
        if self.plan.dry_run:
            return True
        if not self.scratch:  # the first partition: measure it without writing
            self.scratch = self.writer.compact_runs(self.plan.table, day, dry_run=True).bytes_before
        free = self.writer.free_bytes()
        need = self.floor + self.plan.workers * self.scratch
        if free < need:
            self.stopped = (
                f"{free / GB:.1f} GB free, under the {self.floor / GB:g} GB floor "
                f"plus {self.plan.workers} x {self.scratch / GB:.2f} GB of scratch"
            )
            return False
        return True

    # ------------------------------------------------------------------ results

    def _collect(self, future: "Future[Outcome]") -> None:
        day, _ = self._flying.pop(future)
        error = future.exception()
        if isinstance(error, BrokenProcessPool):
            self.stopped = self.stopped or f"a worker process died ({error})"
            self._abort_flying()
            return
        if error is not None:
            if not self._interrupted:
                self.failure = self.failure or error
            return
        outcome = future.result()
        name = self._names.setdefault(outcome.worker, f"w{len(self._names) + 1}")
        self._done += 1
        self.progress(describe(outcome.day, outcome.report, outcome.seconds, name))
        self.scratch = max(self.scratch, outcome.report.bytes_before)
        if self.totals.add(outcome.day, outcome.report):
            self.sweeper.after_swap(outcome.day)
        elif not self.plan.dry_run:
            self.sweeper.at_once(outcome.day)
        if outcome.seconds > self.plan.budget_s and outcome.report.skipped != OVER_BUDGET:
            self.stopped = self.stopped or (
                f"{day} took over {self.plan.budget_s:g} s (the disk is slow)"
            )

    def _abort_flying(self) -> None:
        """The pool broke: every future in flight carries the same error."""
        self._flying.clear()

    def _tick(self, started: float) -> bool:
        """The clock work between results; -> whether the run must stop at once (a silent
        worker: the pool is terminated and the partitions in flight are left)."""
        now = self.clock()
        if any(now - at > self.silent_s for _, at in self._flying.values()):
            self.stopped = (
                f"a worker was silent for over {self.silent_s:g} s (the pool was stopped)"
            )
            return True
        if self.sweeper.has_due() and self._ingest_free():
            removed = self.sweeper.sweep_due()
            if removed:
                self.progress(f"compact-runs sweep: {removed} files removed")
        if now - self._last_summary >= SUMMARY_S:
            self._last_summary = now
            self.progress(self._summary(now - started))
        return False

    def _summary(self, elapsed: float) -> str:
        rate = self._done / elapsed * 60 if elapsed else 0.0
        left = max(0, self._total - self._done)
        eta = f"{left / rate:.0f} min" if rate else "unknown"
        return (
            f"compact-runs: {self._done}/{self._total} partitions, {rate:.1f}/min, ETA {eta}, "
            f"{self.sweeper.pending} sweeps pending"
        )

    def _final_sweep(self) -> None:
        if not self.sweeper.waiting or not self._ingest_free():
            return  # a later run sweeps (the superseded files are only disk, never read)
        removed = self.sweeper.sweep_all(self.sleep)
        self.progress(f"compact-runs sweep: {removed} files removed (the end of the run)")

    # ------------------------------------------------------------------ signals

    @contextmanager
    def _signals(self) -> Iterator[None]:
        """SIGINT and SIGTERM stop the dispatch (main thread only; elsewhere nothing is set)."""
        saved: dict[signal.Signals, Any] = {}
        try:
            for caught in (signal.SIGINT, signal.SIGTERM):
                saved[caught] = signal.signal(caught, self._on_signal)
        except ValueError:  # not the main thread: the caller owns the signals
            pass
        try:
            yield
        finally:
            for number, handler in saved.items():
                signal.signal(number, handler)

    def _on_signal(self, signum: int, frame: FrameType | None) -> None:
        self._interrupted = signal.Signals(signum).name
