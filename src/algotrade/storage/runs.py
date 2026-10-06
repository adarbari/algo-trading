"""Run records: the audit trail and checkpoint for every job (ADR 0010).

The ``run-records`` owner (ADR 0019): run ids come from ``new_run_id``; a one-shot use case
(a screen, a backtest) opens its record with ``start_run`` and closes it with
``RunRecord.finish``, which decides COMPLETE or PARTIAL. The ingest loop (``IngestRun``) and
the job runner (``services/jobs``) build on the same record.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    WAITING = "waiting"  # a workflow whose source has not published the session yet (ADR 0043)
    FAILED = "failed"


@dataclass
class RunRecord:
    run_id: str
    job: str
    session_date: date
    started_at: datetime
    status: RunStatus = RunStatus.RUNNING
    finished_at: datetime | None = None
    items: dict[str, str] = field(default_factory=dict)  # per-item status, e.g. ticker -> OK
    stats: dict[str, Any] = field(default_factory=dict)

    def finish(
        self, now: datetime, *, complete: bool = True, stats: dict[str, Any] | None = None
    ) -> "RunRecord":
        """Close the run: COMPLETE, or PARTIAL when ``complete`` is false. Returns ``self``."""
        self.status = RunStatus.COMPLETE if complete else RunStatus.PARTIAL
        self.finished_at = now
        if stats is not None:
            self.stats = stats
        return self

    def to_json(self) -> str:
        data = asdict(self)
        data["session_date"] = self.session_date.isoformat()
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        return json.dumps(data, indent=2, sort_keys=True, default=str)

    @classmethod
    def from_json(cls, text: str) -> "RunRecord":
        data = json.loads(text)
        return cls(
            run_id=data["run_id"],
            job=data["job"],
            session_date=date.fromisoformat(data["session_date"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            status=RunStatus(data["status"]),
            finished_at=datetime.fromisoformat(data["finished_at"])
            if data["finished_at"]
            else None,
            items=data["items"],
            stats=data["stats"],
        )


def new_run_id(job: str, session_date: date, now: datetime) -> str:
    """Sortable, filesystem-safe run id, e.g. ``option_chains-2026-10-02-20261003T010203Z``."""
    return f"{job}-{session_date.isoformat()}-{now.strftime('%Y%m%dT%H%M%SZ')}"


def start_run(job: str, session_date: date, now: datetime) -> RunRecord:
    """A new RUNNING record for ``job`` with a fresh run id."""
    return RunRecord(new_run_id(job, session_date, now), job, session_date, now)


_RUN_SESSION = re.compile(r"-(\d{4}-\d{2}-\d{2})-\d{8}T\d{6}Z$")


def run_session(run_id: str) -> date | None:
    """The session date encoded by ``new_run_id``; ``None`` for ids in any other form."""
    match = _RUN_SESSION.search(run_id)
    return date.fromisoformat(match.group(1)) if match else None
