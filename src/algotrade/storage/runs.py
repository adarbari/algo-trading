"""Run records: the audit trail and checkpoint for every job (ADR 0010)."""

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
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
