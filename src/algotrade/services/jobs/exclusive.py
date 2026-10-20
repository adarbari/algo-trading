"""One writer at a time: the run lock every writing ingestion command takes (ADR 0019 R5), and
the one-evaluation-per-owner claim every edge-evaluation caller takes (ADR 0059 amendment
2026-10-10).

Two ingestion runs against the same store (a launchd nightly and a manual backfill, say)
could otherwise resume the same unfinished run or interleave writes to the same tables. The
lock is the store's own (``Backend.lock``: a file lock for the local backend), so it holds
across processes. A second run either fails fast with ``RunLockedError`` or, with
``wait=True``, queues behind the first.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from algotrade.config.user import UserContext
from algotrade.core.model.errors import AlgoTradeError
from algotrade.services.jobs.api import run_job
from algotrade.services.jobs.handlers import LIBRARY_HANDLERS
from algotrade.services.jobs.models import JobRecord, JobStatus
from algotrade.storage.locks import held
from algotrade.storage.tables.interfaces import Backend

INGEST_LOCK = "ingest"
DEPLOY_LOCK = "deploy"  # the deploy hold (ADR 0057); long maintenance jobs hold it too
EDGE_EVAL = "edge-eval"  # the job kind (and the lock-name prefix) of an edge evaluation
EDGE_EVAL_STALE = timedelta(hours=2)  # the longest run takes ~40 minutes: older, "running", is dead


class RunLockedError(AlgoTradeError):
    """Another run holds the lock (and the caller chose not to wait)."""


@contextmanager
def exclusive_run(backend: Backend, name: str = INGEST_LOCK, wait: bool = False) -> Iterator[None]:
    """Hold the store's ``name`` lock for the block; raise ``RunLockedError`` if it is taken
    and ``wait`` is false."""
    with held(backend.lock(name), wait=wait) as taken:
        if not taken:
            raise RunLockedError(
                f"another {name} run is using this data store; wait for it to finish "
                "or pass --wait to queue behind it"
            )
        yield


class EdgeEvalBusyError(RunLockedError):
    """The owner already has an evaluation queued or running, or another caller is claiming one."""


@contextmanager
def claim_edge_eval(
    backend: Backend, owner: str, recover: Callable[[], object] | None = None
) -> Iterator[None]:
    """Hold the owner's evaluation slot for the block: one edge evaluation at a time per owner,
    whoever starts it (the API, the CLI, the nightly) and in whichever process.

    The store's lock ``edge-eval:<owner>`` is taken without waiting (held: another caller is
    between its check and its submit, or running the CLI) and, under it, an evaluation job of
    the owner queued or running (a record younger than ``EDGE_EVAL_STALE``) refuses the claim
    too; ``recover`` (the API runner's failing of a stopped process's jobs) runs first. The
    caller submits its job inside the block. Raises ``EdgeEvalBusyError``.

    Limit: a job's liveness is its record's age, not a lock held for the whole run (that needs
    the runner to hold it in its worker); a crashed run blocks its owner for ``EDGE_EVAL_STALE``."""
    with held(backend.lock(f"{EDGE_EVAL}:{owner}"), wait=False) as taken:
        if not taken:
            raise EdgeEvalBusyError(
                f"an evaluation for {owner} is being started or run by another process: "
                "wait for it to finish"
            )
        if recover is not None:
            recover()
        now = datetime.now(UTC)
        for run in backend.runs.find(f"job:{EDGE_EVAL}"):
            job = JobRecord.from_run(run)
            if (
                job.user == owner
                and job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
                and now - job.submitted_at < EDGE_EVAL_STALE
            ):
                raise EdgeEvalBusyError(
                    f"an evaluation of {job.params.get('edge')} is already running "
                    f"for {owner}: wait for it to finish"
                )
        yield


def run_edge_eval_claimed(
    backend: Backend, resources: Mapping[str, Any], params: Mapping[str, Any], owner: UserContext
) -> JobRecord:
    """Run one ``edge-eval`` job to completion under the owner's claim (the CLI's and the
    nightly's path; ``EdgeEvalBusyError`` when the owner already has one)."""
    with claim_edge_eval(backend, owner.user_id):
        return run_job(backend.runs, LIBRARY_HANDLERS, resources, EDGE_EVAL, params, owner)
