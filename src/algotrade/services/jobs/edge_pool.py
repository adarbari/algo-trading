"""Edge evaluations on several worker processes (ADR 0059 amendment 2026-10-20): the CLI's
``evaluate-edges --jobs N``. Each worker opens the store and configs itself and runs one
``edge-eval`` job at a time; the caller holds the owners' claims (``claim_edge_eval``) for the
whole run, so no API, nightly or second CLI evaluates their edges meanwhile, and the workers
run the jobs without claiming. The workers share the run's screen cache directory
(``reads/screens.py``); commits of their results serialise on the store's commit lock, and a
leg's rows are keyed by edge, so edges never share a row. Results come back in task order."""

import multiprocessing
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algotrade.config.env import thread_limits
from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.reads.screens import ScreenCache
from algotrade.services.jobs.api import run_job
from algotrade.services.jobs.exclusive import EDGE_EVAL
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.storage.factory import open_backend, open_config_store
from algotrade.storage.tables.result_writer import ResultWriter


@dataclass(frozen=True)
class PoolSettings:
    """What a worker needs to open what the caller has: the store, the configs and the run's
    screen cache (its scratch directory and the shared (owner, config hash) pairs)."""

    data_url: str
    config_dir: str
    screens_root: str | None = None
    shared: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class EdgeTask:
    edge: str
    owner: str
    params: Mapping[str, Any]


@dataclass(frozen=True)
class EdgeOutcome:
    edge: str
    owner: str
    ok: bool
    result: Mapping[str, Any]
    error: str | None = None


def run_edge_evals(
    settings: PoolSettings, tasks: Sequence[EdgeTask], jobs: int
) -> list[EdgeOutcome]:
    """``tasks`` on ``jobs`` worker processes (spawned: no shared interpreter state), one edge
    per worker at a time, in the order given; the outcomes in task order. A worker that raises
    or dies is that edge's failed outcome (the others' results are kept), and the job records the
    dead worker left running are failed here, while the caller still holds the claims."""
    threads = max(1, (os.cpu_count() or 1) // jobs)  # each worker's share of the cores
    outcomes: list[EdgeOutcome] = []
    died = False
    with thread_limits(threads), ProcessPoolExecutor(
        max_workers=jobs, mp_context=multiprocessing.get_context("spawn"),
    ) as pool:  # fmt: skip
        futures = [pool.submit(_evaluate, settings, task) for task in tasks]
        for task, future in zip(tasks, futures, strict=True):
            try:
                outcomes.append(future.result())
            except Exception as error:  # a worker killed (memory) breaks the pool
                died = True
                outcomes.append(EdgeOutcome(task.edge, task.owner, False, {}, _describe(error)))
    if died:
        _fail_in_flight(settings, tasks)
    return outcomes


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _fail_in_flight(settings: PoolSettings, tasks: Sequence[EdgeTask]) -> None:
    """Fail the unfinished ``edge-eval`` jobs of these tasks' owners and edges (the claims are
    the caller's, so they are this run's workers' or a crash's, never another caller's)."""
    runs = open_backend(settings.data_url).runs
    wanted = {(t.owner, t.edge) for t in tasks}
    now = datetime.now(UTC)
    for run in runs.find(f"job:{EDGE_EVAL}"):
        record = JobRecord.from_run(run)
        if not record.done and (record.user, record.params.get("edge")) in wanted:
            record.status, record.finished_at = JobStatus.FAILED, now
            record.error = "abandoned: the worker process running it stopped"
            runs.save(record.to_run())


def _evaluate(settings: PoolSettings, task: EdgeTask) -> EdgeOutcome:
    """One edge as its owner's job, in a worker process (the claim is the caller's)."""
    try:
        backend = open_backend(settings.data_url)
        resources: dict[str, Any] = {
            "reader": StoreReader(backend), "writer": ResultWriter(backend),
            "configs": open_config_store(settings.config_dir),
        }  # fmt: skip
        if settings.screens_root is not None:
            resources["screens"] = ScreenCache(Path(settings.screens_root), settings.shared)
        user = UserContext(task.owner)
        job = run_job(backend.runs, LIBRARY_HANDLERS, resources, EDGE_EVAL, task.params, user)
    except Exception as error:  # the edge's failure, not the run's
        return EdgeOutcome(task.edge, task.owner, False, {}, _describe(error))
    ok = job.status is not JobStatus.FAILED
    return EdgeOutcome(task.edge, task.owner, ok, job.result, job.error)
