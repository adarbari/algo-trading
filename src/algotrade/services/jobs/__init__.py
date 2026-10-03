"""Long-running work as jobs (ADR 0010): submit, poll, fetch the result.

Phase 0 ships a local in-process runner. A queue-backed runner (phase 6) implements the
same ``JobRunner`` protocol, so the CLIs and the future API do not change.
"""

from algotrade.services.jobs.api import run_job
from algotrade.services.jobs.exclusive import INGEST_LOCK, RunLockedError, exclusive_run
from algotrade.services.jobs.models import JobRecord, JobStatus, job_id_for
from algotrade.services.jobs.pool import as_completed
from algotrade.services.jobs.runner import (
    JobContext,
    JobHandler,
    JobKind,
    JobRunner,
    LocalJobRunner,
)

__all__ = [
    "INGEST_LOCK",
    "JobContext",
    "JobHandler",
    "JobKind",
    "JobRecord",
    "JobRunner",
    "JobStatus",
    "LocalJobRunner",
    "RunLockedError",
    "as_completed",
    "exclusive_run",
    "job_id_for",
    "run_job",
]
