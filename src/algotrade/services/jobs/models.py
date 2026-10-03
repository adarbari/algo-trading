"""Job records, persisted as run records so they survive restarts and show in audits."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from algotrade.config.user import UserContext
from algotrade.storage.runs import RunRecord, RunStatus

JobStatus = RunStatus  # queued -> running -> complete | partial | failed

JOB_PREFIX = "job:"

__all__ = ["JOB_PREFIX", "JobRecord", "JobStatus", "job_id_for"]


def job_id_for(kind: str, params: Mapping[str, Any], user: UserContext) -> str:
    """Deterministic id: the same work submitted twice is the same job (idempotent)."""
    canonical = json.dumps(
        {"kind": kind, "params": params, "user": user.user_id}, sort_keys=True, default=str
    )
    return f"job-{kind}-{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


@dataclass
class JobRecord:
    job_id: str
    kind: str
    params: dict[str, Any]
    user: str
    submitted_at: datetime
    status: JobStatus = JobStatus.QUEUED
    finished_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_run(self) -> RunRecord:
        return RunRecord(
            run_id=self.job_id,
            job=f"{JOB_PREFIX}{self.kind}",
            session_date=self.submitted_at.date(),
            started_at=self.submitted_at,
            status=self.status,
            finished_at=self.finished_at,
            stats={
                "params": self.params,
                "user": self.user,
                "result": self.result,
                "error": self.error,
            },
        )

    @classmethod
    def from_run(cls, run: RunRecord) -> "JobRecord":
        return cls(
            job_id=run.run_id,
            kind=run.job.removeprefix(JOB_PREFIX),
            params=dict(run.stats.get("params", {})),
            user=str(run.stats.get("user", "")),
            submitted_at=run.started_at,
            status=run.status,
            finished_at=run.finished_at,
            result=dict(run.stats.get("result") or {}),
            error=run.stats.get("error"),
        )

    @property
    def done(self) -> bool:
        return self.status in (JobStatus.COMPLETE, JobStatus.PARTIAL, JobStatus.FAILED)
