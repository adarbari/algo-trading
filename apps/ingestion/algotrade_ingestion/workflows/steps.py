"""Workflow steps: isolation, per-step status and duration, and the overall status rule.

A step that raises is FAILED with its error; the workflow carries on. A step whose hard
dependency FAILED is BLOCKED; one whose data precondition is not met, or whose sources are
not configured, is SKIPPED (with the reason). ``overall`` is the one place that turns step
statuses into the run's COMPLETE / PARTIAL / FAILED.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_ingestion.tasks.framework import TaskContext


class StepStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # not applicable: source not configured, precondition, latest only
    BLOCKED = "BLOCKED"  # a hard dependency failed


class Status(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


# Why a step cannot run for a session (``None``: it can), e.g. no universe snapshot yet.
type Precondition = Callable[[TaskContext, date], str | None]


@dataclass(frozen=True)
class Step:
    """One workflow step: a registry task name (or the ``screens`` job step)."""

    name: str
    blocked_by: tuple[str, ...] = ()  # hard dependencies: these FAILED -> BLOCKED
    requires: Precondition | None = None  # data that must exist (not "today's build passed")
    latest_only: bool = False  # current-snapshot sources: only the latest closed session


@dataclass
class StepResult:
    name: str
    status: StepStatus
    duration_s: float = 0.0
    result: Any = None
    reason: str | None = None  # SKIPPED / BLOCKED
    error: str | None = None  # FAILED

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status.value, "duration_s": self.duration_s}
        for key in ("result", "reason", "error"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        return out


@dataclass
class Outcome:
    """What a step body returns: its status, a JSON-able result, why (BLOCKED)."""

    status: StepStatus
    result: Any = field(default=None)
    reason: str | None = None


def step_status(status: RunStatus) -> StepStatus:
    """A run (or job) status as a step status: COMPLETE, FAILED, anything else PARTIAL."""
    return {
        RunStatus.COMPLETE: StepStatus.COMPLETE,
        RunStatus.FAILED: StepStatus.FAILED,
    }.get(status, StepStatus.PARTIAL)


def from_record(record: RunRecord) -> Outcome:
    """A registry task's run record as a step outcome."""
    return Outcome(step_status(record.status), record.stats)


def run_isolated(
    name: str, body: Callable[[], Outcome], clock: Callable[[], datetime]
) -> StepResult:
    """Run one step; any exception makes it FAILED (with the error) instead of escaping."""
    started = clock()
    try:
        outcome = body()
    except Exception as exc:
        result = StepResult(name, StepStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
    else:
        result = StepResult(name, outcome.status, result=outcome.result, reason=outcome.reason)
    result.duration_s = round((clock() - started).total_seconds(), 3)
    return result


def overall(statuses: Iterable[StepStatus]) -> Status:
    """The status rule, in one place. Of the steps that ran (not SKIPPED): none succeeded ->
    FAILED; any FAILED, BLOCKED or PARTIAL -> PARTIAL; else COMPLETE."""
    ran = [s for s in statuses if s is not StepStatus.SKIPPED]
    if ran and all(s in (StepStatus.FAILED, StepStatus.BLOCKED) for s in ran):
        return Status.FAILED
    if any(s is not StepStatus.COMPLETE for s in ran):
        return Status.PARTIAL
    return Status.COMPLETE
