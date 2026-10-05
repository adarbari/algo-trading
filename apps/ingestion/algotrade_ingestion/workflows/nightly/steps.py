"""Workflow steps (ADR 0039): dependencies, acceptance, per-step status and the overall rule.

A step declares the steps it ``needs`` and runs only when each of them is satisfied
(SUCCEEDED, WAIVED, or SKIPPED as not applicable); otherwise it is NOT_RUN with the reason.
A step that runs either SUCCEEDS or FAILS: its task must not fail (nor finish PARTIAL when
``task_complete``), and every acceptance check it declares must not FAIL. Checks that WARN
are carried as warnings. A step that raises is FAILED with its error. ``overall`` is the one
place that turns step results into the run's SUCCEEDED / FAILED: a run SUCCEEDS when every
critical step is satisfied; an optional (non-critical) step's failure is only a warning.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_ingestion.tasks.framework.run import FAILURES, TaskContext, status_label
from algotrade_ingestion.tasks.maintenance.quality import Check


class StepStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"  # a need was not satisfied, or its data precondition was not met
    SKIPPED = "SKIPPED"  # not applicable: latest-only during catch-up, a skip rule
    WAIVED = "WAIVED"  # accepted by hand (``nightly --waive``), with a reason


# Step statuses in run records written before ADR 0039.
LEGACY = {
    "COMPLETE": StepStatus.SUCCEEDED,
    "PARTIAL": StepStatus.FAILED,
    "BLOCKED": StepStatus.NOT_RUN,
}
SATISFIED = (StepStatus.SUCCEEDED, StepStatus.WAIVED, StepStatus.SKIPPED)
BAD = (StepStatus.FAILED, StepStatus.NOT_RUN)


def parse_status(value: str) -> StepStatus:
    """A stored step status (current or legacy) as a ``StepStatus``."""
    return LEGACY.get(value) or StepStatus(value)


class Status(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


# Why a step cannot run for a session (``None``: it can), e.g. no universe snapshot yet.
type Precondition = Callable[[TaskContext, date], str | None]
# An acceptance check over what the step wrote (``tasks/maintenance/quality.py``).
type Acceptance = Callable[[StoreReader, date, SourcesSettings], list[Check]]


@dataclass(frozen=True)
class Step:
    """One workflow step: a registry task name (or the ``screens`` job step)."""

    name: str
    needs: tuple[str, ...] = ()  # steps that must be satisfied before this one runs
    critical: bool = True  # False: a failure is a warning, not the run's failure
    requires: Precondition | None = None  # data that must exist for the session
    latest_only: bool = False  # current-snapshot sources: only the latest closed session
    accept: tuple[Acceptance, ...] = ()  # acceptance checks run after the task
    task_complete: bool = False  # the task must finish COMPLETE (a PARTIAL item fails it)
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)  # extra task params


@dataclass
class StepResult:
    name: str
    status: StepStatus
    critical: bool = True
    duration_s: float = 0.0
    result: Any = None
    reason: str | None = None  # why it FAILED acceptance, was NOT_RUN, SKIPPED or WAIVED
    error: str | None = None  # the exception when it raised
    checks: list[dict[str, str]] = field(default_factory=list)  # checks that did not PASS

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status.value,
            "critical": self.critical,
            "duration_s": self.duration_s,
        }
        for key in ("result", "reason", "error"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.checks:
            out["checks"] = self.checks
        return out


@dataclass
class Outcome:
    """What a step body returns: its status, a JSON-able result, why, its checks."""

    status: StepStatus
    result: Any = field(default=None)
    reason: str | None = None
    checks: list[dict[str, str]] = field(default_factory=list)


def judge(checks: Iterable[Check], result: Any = None) -> Outcome:
    """Acceptance: FAILED with the failing checks as the reason when any check FAILs."""
    checks = list(checks)
    failed = [c for c in checks if c.status == "FAIL"]
    shown = [asdict(c) for c in checks if c.status != "PASS"]
    if failed:
        reason = "; ".join(f"{c.name}: {c.detail}" for c in failed)
        return Outcome(StepStatus.FAILED, result, reason, shown)
    return Outcome(StepStatus.SUCCEEDED, result, None, shown)


def from_record(
    record: RunRecord,
    step: Step | None = None,
    ctx: TaskContext | None = None,
    session: date | None = None,
) -> Outcome:
    """A registry task's run record as a step outcome, after the step's acceptance checks.
    A task that could not run for a reason outside our data (``stats["skipped"]``, e.g. its
    gateway is down) is SKIPPED."""
    skipped = record.stats.get("skipped")
    if skipped:
        return Outcome(StepStatus.SKIPPED, record.stats, reason=f"skipped: {skipped}")
    if record.status is RunStatus.FAILED:
        error = record.stats.get("error") or "the task failed"
        return Outcome(StepStatus.FAILED, record.stats, reason=str(error))
    if step is not None and step.task_complete and record.status is not RunStatus.COMPLETE:
        reason = f"task finished {record.status.value}: {partial_reason(record)}"
        return Outcome(StepStatus.FAILED, record.stats, reason=reason)
    if step is None or ctx is None or session is None:
        return Outcome(StepStatus.SUCCEEDED, record.stats)
    checks = [c for fn in step.accept for c in fn(ctx.reader, session, ctx.settings)]
    return judge(checks, record.stats)


SHOWN_ITEMS = 3  # failed items named in a step's reason


def partial_reason(record: RunRecord) -> str:
    """Why a task finished PARTIAL: its stated reasons, then its first failed items (e.g. a
    rollup's gap, with the command that fills it)."""
    reasons = [str(r) for r in record.stats.get("partial", [])]
    failed = [f"{k}: {v}" for k, v in record.items.items() if status_label(v) in FAILURES]
    more = f" (+{len(failed) - SHOWN_ITEMS} more)" if len(failed) > SHOWN_ITEMS else ""
    shown = [*reasons, *failed[:SHOWN_ITEMS]]
    return ("; ".join(shown) + more) if shown else "items failed"


def run_isolated(
    name: str, body: Callable[[], Outcome], clock: Callable[[], datetime], critical: bool = True
) -> StepResult:
    """Run one step; any exception makes it FAILED (with the error) instead of escaping."""
    started = clock()
    try:
        outcome = body()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        result = StepResult(name, StepStatus.FAILED, critical, error=error)
    else:
        result = StepResult(
            name,
            outcome.status,
            critical,
            result=outcome.result,
            reason=outcome.reason,
            checks=outcome.checks,
        )
    result.duration_s = round((clock() - started).total_seconds(), 3)
    return result


def _critical_status(result: StepResult | Mapping[str, Any]) -> tuple[bool, StepStatus]:
    if isinstance(result, StepResult):
        return result.critical, result.status
    return bool(result.get("critical", True)), parse_status(str(result["status"]))


def overall(results: Iterable[StepResult | Mapping[str, Any]]) -> Status:
    """The status rule, in one place: SUCCEEDED when every critical step is satisfied
    (SUCCEEDED, WAIVED or SKIPPED); else FAILED. Stored results without ``critical`` (run
    records written before ADR 0039) count as critical."""
    for critical, status in map(_critical_status, results):
        if critical and status not in SATISFIED:
            return Status.FAILED
    return Status.SUCCEEDED


def unsatisfied(needs: Iterable[str], done: Mapping[str, StepResult]) -> list[str]:
    """The needs that ran in this session and are not satisfied, as ``name (STATUS)``."""
    return [f"{n} ({done[n].status.value})" for n in needs if n in done and done[n].status in BAD]
