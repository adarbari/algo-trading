"""Run records for display: recent nightly runs (per session, step by step) and one run's
detail with its items summarised and failures grouped by reason.

Reads the records through the store (never the ingestion app): the nightly workflow saves one
``nightly`` record per session whose ``stats.steps`` hold each step's status, duration and
result counts; every other job saves per-item statuses (``items``: key -> status, where a
status may carry a detail after a colon, e.g. ``STALE_DATA: chain is for 2026-10-01``);
failures are grouped by ``services.run_items``, as the nightly report groups them.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from algotrade.services.explore.store import NotFoundError, ReadStore
from algotrade.services.run_items import failed_items, status_code
from algotrade.storage.runs import RunRecord

NIGHTLY = "nightly"  # the job name of the nightly workflow's per-session records
EXAMPLES = 10


@dataclass(frozen=True)
class StepSummary:
    name: str
    status: str
    duration_s: float | None
    reason: str | None
    error: str | None
    counts: dict[str, Any]


@dataclass(frozen=True)
class NightlySummary:
    run_id: str
    session: date
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None
    steps: list[StepSummary]
    problems: list[str]


def _duration(run: RunRecord) -> float | None:
    if run.finished_at is None:
        return None
    return round((run.finished_at - run.started_at).total_seconds(), 3)


def _steps(run: RunRecord) -> list[StepSummary]:
    stored = run.stats.get("steps")
    if not isinstance(stored, dict):  # a run that failed before recording its steps
        return [StepSummary(n, s, None, None, None, {}) for n, s in run.items.items()]
    return [
        StepSummary(
            name=str(name),
            status=str(step.get("status", "")),
            duration_s=step.get("duration_s"),
            reason=step.get("reason"),
            error=step.get("error"),
            counts=dict(step.get("result") or {}),
        )
        for name, step in stored.items()
    ]


def nightly_runs(store: ReadStore, limit: int = 10) -> list[NightlySummary]:
    """The ``limit`` most recent nightly session runs, newest first."""
    runs = store.reader.runs(NIGHTLY)[-max(limit, 1) :]
    return [
        NightlySummary(
            run_id=r.run_id,
            session=r.session_date,
            status=r.status.value,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_s=_duration(r),
            steps=_steps(r),
            problems=[str(p) for key in ("partial", "failed") for p in r.stats.get(key) or []],
        )
        for r in reversed(runs)
    ]


@dataclass(frozen=True)
class FailureGroup:
    reason: str  # normalised (services.run_items): code + message without ids, dates, numbers
    count: int
    examples: list[str]  # item keys (tickers, steps), sorted
    statuses: list[str]  # distinct statuses as recorded, sorted


@dataclass(frozen=True)
class RunDetail:
    run_id: str
    job: str
    session: date
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None
    items_total: int
    items_by_status: dict[str, int]
    failures: list[FailureGroup]
    stats: dict[str, Any]


def failure_groups(items: dict[str, str]) -> list[FailureGroup]:
    """Items whose status is not fine, grouped by normalised reason (largest group first)."""
    return [
        FailureGroup(
            reason=reason,
            count=len(rows),
            examples=[k for k, _ in rows[:EXAMPLES]],
            statuses=sorted({s for _, s in rows})[:EXAMPLES],
        )
        for reason, rows in failed_items(items)
    ]


def run_detail(store: ReadStore, run_id: str) -> RunDetail:
    """One run record by id; ``NotFoundError`` when there is none."""
    try:
        run = store.reader.run(run_id)
    except ValueError as exc:  # not a valid storage key
        raise NotFoundError(f"run {run_id!r}: {exc}") from exc
    if run is None:
        raise NotFoundError(f"no run {run_id!r}")
    by_status = Counter(status_code(str(s)) for s in run.items.values())
    return RunDetail(
        run_id=run.run_id,
        job=run.job,
        session=run.session_date,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_s=_duration(run),
        items_total=len(run.items),
        items_by_status=dict(by_status.most_common()),
        failures=failure_groups(run.items),
        stats=run.stats,
    )
