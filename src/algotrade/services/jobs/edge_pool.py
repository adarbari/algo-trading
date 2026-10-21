"""Edge evaluations on several worker processes (ADR 0059 amendment 2026-10-20): the CLI's
``evaluate-edges --jobs N``. Each worker opens the store and configs itself and runs one
``edge-eval`` job at a time; the caller holds the owners' claims (``claim_edge_eval``) for the
whole run, so no API, nightly or second CLI evaluates their edges meanwhile, and the workers
run the jobs without claiming. The workers share the run's screen cache directory
(``reads/screens.py``); commits of their results serialise on the store's commit lock, and a
leg's rows are keyed by edge, so edges never share a row. Results come back in task order."""

import multiprocessing
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.reads.screens import ScreenCache
from algotrade.services.jobs.api import run_job
from algotrade.services.jobs.exclusive import EDGE_EVAL
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobStatus
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
    per worker at a time, longest queue first as submitted; the outcomes in task order."""
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=jobs, mp_context=context) as pool:
        futures = [pool.submit(_evaluate, settings, task) for task in tasks]
        return [future.result() for future in futures]


def _evaluate(settings: PoolSettings, task: EdgeTask) -> EdgeOutcome:
    """One edge as its owner's job, in a worker process (the claim is the caller's)."""
    backend = open_backend(settings.data_url)
    configs = open_config_store(settings.config_dir)
    resources: dict[str, Any] = {
        "reader": StoreReader(backend), "writer": ResultWriter(backend), "configs": configs,
    }  # fmt: skip
    if settings.screens_root is not None:
        resources["screens"] = ScreenCache(Path(settings.screens_root), settings.shared)
    job = run_job(
        backend.runs, LIBRARY_HANDLERS, resources, EDGE_EVAL, task.params, UserContext(task.owner)
    )
    return EdgeOutcome(
        task.edge, task.owner, job.status is not JobStatus.FAILED, job.result, job.error
    )
