"""Long-running work as jobs (ADR 0010): submit, poll, fetch the result.

Phase 0 ships a local in-process runner. A queue-backed runner (phase 6) implements the
same ``JobRunner`` protocol, so the CLIs and the future API do not change.
"""

from algotrade.services.jobs.models import JobRecord, JobStatus, job_id_for
from algotrade.services.jobs.runner import JobContext, JobHandler, JobRunner, LocalJobRunner

__all__ = [
    "JobContext",
    "JobHandler",
    "JobRecord",
    "JobRunner",
    "JobStatus",
    "LocalJobRunner",
    "job_id_for",
]
