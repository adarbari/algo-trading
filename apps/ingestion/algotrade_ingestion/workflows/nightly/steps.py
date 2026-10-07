"""Workflow steps (ADR 0039): dependencies, acceptance, per-step status and the overall rule.

A step declares the steps it ``needs`` and runs only when each of them is satisfied
(SUCCEEDED, WAIVED, or SKIPPED as not applicable); otherwise it is NOT_RUN with the reason.
A step that runs either SUCCEEDS or FAILS: its task must not fail (nor finish PARTIAL when
``task_complete``), and every acceptance check it declares must not FAIL. Checks that WARN
are carried as warnings. A step that raises is FAILED with its error. A failing check marked
``pending`` (its source has not published the session yet) makes the step WAITING instead,
while ``wait`` holds (before the step's deadline, ADR 0043); never for a fetch failure.
``overall`` is the one place that turns step results into the run's SUCCEEDED / WAITING /
FAILED: a run SUCCEEDS when every critical step is satisfied; an optional (non-critical)
step's failure is only a warning.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from algotrade.config.site.settings import SourcesSettings
from algotrade.data import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade_ingestion.tasks.framework.run import FAILURES, TaskContext, status_label
from algotrade_ingestion.tasks.maintenance.quality import Check
from algotrade_ingestion.workflows.nightly.timing import observe


class StepStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"  # a need was not satisfied, or its data precondition was not met
    WAITING = "WAITING"  # its source has not published the session yet; retried until the deadline
    SKIPPED = "SKIPPED"  # not applicable: latest-only during catch-up, a skip rule
    WAIVED = "WAIVED"  # accepted by hand (``nightly --waive``), with a reason


# Step statuses in run records written before ADR 0039.
LEGACY = {
    "COMPLETE": StepStatus.SUCCEEDED,
    "PARTIAL": StepStatus.FAILED,
    "BLOCKED": StepStatus.NOT_RUN,
}
SATISFIED = (StepStatus.SUCCEEDED, StepStatus.WAIVED, StepStatus.SKIPPED)
BAD = (StepStatus.FAILED, StepStatus.NOT_RUN, StepStatus.WAITING)


def parse_status(value: str) -> StepStatus:
    """A stored step status (current or legacy) as a ``StepStatus``."""
    return LEGACY.get(value) or StepStatus(value)


class Status(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    WAITING = "WAITING"
    FAILED = "FAILED"


# Why a step cannot run for a session (``None``: it can), e.g. no universe snapshot yet.
type Precondition = Callable[[TaskContext, date], str | None]
# An acceptance check over what the step wrote (``tasks/maintenance/quality.py``).
type Acceptance = Callable[[StoreReader, date, SourcesSettings], list[Check]]
# A check that also needs the run's config store (a site registry), e.g. ``check_macro``.
type ConfiguredAcceptance = Callable[[TaskContext, date], list[Check]]


@dataclass(frozen=True)
class Step:
    """One workflow step: a registry task name (or the ``screens`` job step)."""

    name: str
    needs: tuple[str, ...] = ()  # steps that must be satisfied before this one runs
    critical: bool = True  # False: a failure is a warning, not the run's failure
    requires: Precondition | None = None  # data that must exist for the session
    latest_only: bool = False  # current-snapshot sources: only the latest closed session
    accept: tuple[Acceptance, ...] = ()  # acceptance checks run after the task
    accept_with: tuple[ConfiguredAcceptance, ...] = ()  # the same, given the task context
    task_complete: bool = False  # the task must finish COMPLETE (a PARTIAL item fails it)
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)  # extra task params
    # The task resumes (``IngestRun(resume=True)``: it refetches only its RETRYABLE items). A
    # step that SUCCEEDED with such items left is re-run, not reused, by a retry while its
    # session is the latest and the task run's staging exists; its dependents re-run too.
    resumable: bool = False


@dataclass
class StepResult:
    name: str
    status: StepStatus
    critical: bool = True
    duration_s: float = 0.0
    result: Any = None
    reason: str | None = None  # why it FAILED acceptance, was NOT_RUN, SKIPPED or WAIVED
    error: str | None = None  # the exception when it raised
    checks: list[dict[str, Any]] = field(
        default_factory=list
    )  # checks that did not PASS, and those carrying data
    held_by_wait: bool = False  # NOT_RUN only because a need is WAITING (transitively)
    observed: dict[str, Any] | None = None  # what the attempt saw of the source (timing.observe)
    arrival: dict[str, Any] | None = None  # ``observed`` + minutes_after_close, latest session
    task_run: str | None = None  # the registry task's run id (its staging, for a resume)
    origin: str | None = None  # the nightly attempt that produced a reused result

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status.value,
            "critical": self.critical,
            "duration_s": self.duration_s,
        }
        for key in ("result", "reason", "error", "task_run", "origin"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        if self.checks:
            out["checks"] = self.checks
        if self.held_by_wait:
            out["held_by_wait"] = True
        if self.arrival is not None:
            out["arrival"] = self.arrival
        return out


@dataclass
class Outcome:
    """What a step body returns: its status, a JSON-able result, why, its checks."""

    status: StepStatus
    result: Any = field(default=None)
    reason: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)
    observed: dict[str, Any] | None = None
    task_run: str | None = None


def judge(checks: Iterable[Check], result: Any = None, wait: bool = False) -> Outcome:
    """Acceptance: FAILED with the failing checks as the reason when any check FAILs; WAITING
    instead when ``wait`` and every failing check is ``pending`` (not yet published)."""
    checks = list(checks)
    failed = [c for c in checks if c.status == "FAIL"]
    shown = [
        {
            "name": c.name,
            "status": c.status,
            "detail": c.detail,
            **({"data": c.data} if c.data else {}),
        }
        for c in checks
        if c.status != "PASS" or c.data  # a check with figures is kept even when it passes
    ]
    if failed:
        reason = "; ".join(f"{c.name}: {c.detail}" for c in failed)
        if wait and all(c.pending for c in failed):
            return Outcome(StepStatus.WAITING, result, f"not published yet: {reason}", shown)
        return Outcome(StepStatus.FAILED, result, reason, shown)
    return Outcome(StepStatus.SUCCEEDED, result, None, shown)


def from_record(
    record: RunRecord,
    step: Step | None = None,
    ctx: TaskContext | None = None,
    session: date | None = None,
    wait: bool = False,
) -> Outcome:
    """A registry task's run record as a step outcome, after the step's acceptance checks.
    A task that could not run for a reason outside our data (``stats["skipped"]``, e.g. its
    gateway is down) is SKIPPED."""
    outcome = _judged(record, step, ctx, session, wait)
    outcome.task_run = record.run_id
    return outcome


def _judged(
    record: RunRecord,
    step: Step | None,
    ctx: TaskContext | None,
    session: date | None,
    wait: bool,
) -> Outcome:
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
    checks += [c for fn in step.accept_with for c in fn(ctx, session)]
    outcome = judge(checks, record.stats, wait)
    outcome.observed = observe(step.name, checks)
    return outcome


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
            observed=outcome.observed,
            task_run=outcome.task_run,
        )
    result.duration_s = round((clock() - started).total_seconds(), 3)
    return result


def _critical_status(result: StepResult | Mapping[str, Any]) -> tuple[bool, StepStatus, bool]:
    if isinstance(result, StepResult):
        return result.critical, result.status, result.held_by_wait
    return (
        bool(result.get("critical", True)),
        parse_status(str(result["status"])),
        bool(result.get("held_by_wait", False)),
    )


def overall(results: Iterable[StepResult | Mapping[str, Any]]) -> Status:
    """The status rule, in one place: SUCCEEDED when every critical step is satisfied
    (SUCCEEDED, WAIVED or SKIPPED); WAITING when every unmet critical step is WAITING or
    NOT_RUN only because of a waiting need (``held_by_wait``) and at least one is WAITING;
    else FAILED: a real failure is never masked by waiting. Stored results without
    ``critical`` (run records written before ADR 0039) count as critical."""
    unmet = [
        (status, held)
        for critical, status, held in map(_critical_status, results)
        if critical and status not in SATISFIED
    ]
    if not unmet:
        return Status.SUCCEEDED
    waiting = [s is StepStatus.WAITING for s, _ in unmet]
    covered = all(
        w or (s is StepStatus.NOT_RUN and held) for w, (s, held) in zip(waiting, unmet, strict=True)
    )
    return Status.WAITING if covered and any(waiting) else Status.FAILED


def unsatisfied(needs: Iterable[str], done: Mapping[str, StepResult]) -> list[str]:
    """The needs that ran in this session and are not satisfied, as ``name (STATUS)``."""
    return [f"{n} ({done[n].status.value})" for n in needs if n in done and done[n].status in BAD]
