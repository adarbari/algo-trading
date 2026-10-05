"""Run records for the Admin pages: recent nightly runs (``NightlyRun``, step by step), one run
record (``RunDetail``: items summarised, failures grouped by reason) and its items (``RunItem``).

Run records, not session data (a run names its own session): the loaders take the session-free
``Stores`` context. The nightly workflow saves one ``nightly`` record per session whose
``stats.steps`` hold each step's status, duration and result counts; every other job saves
per-item statuses (``items``: key -> status, a status may carry a detail after a colon, e.g.
``STALE_DATA: chain is for 2026-10-01``); failures are grouped by ``services.run_items``, as
the nightly report groups them."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from algotrade.services.read.context import Stores
from algotrade.services.run_items import failed_items, status_code
from algotrade.storage.runs import RunRecord

NIGHTLY = "nightly"  # the job name of the nightly workflow's per-session records
EXAMPLES = 10


@dataclass(frozen=True)
class RunStep:
    """One step of a nightly run: ``counts`` are its result counts as recorded."""

    name: str
    status: str
    duration_s: float | None
    reason: str | None
    error: str | None
    counts: dict[str, Any]


@dataclass(frozen=True)
class NightlyRun:
    """One session's nightly run: ``steps`` in workflow order, ``problems`` why it is partial
    or failed."""

    run_id: str
    session: date
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None
    steps: tuple[RunStep, ...]
    problems: tuple[str, ...]


@dataclass(frozen=True)
class FailureGroup:
    """Items not fine, grouped by a normalised reason (code + message without ids, dates or
    numbers): ``examples`` item keys, ``statuses`` the distinct statuses as recorded."""

    reason: str
    count: int
    examples: tuple[str, ...]
    statuses: tuple[str, ...]


@dataclass(frozen=True)
class RunDetail:
    """One run record: ``items_by_status`` status code -> count (most common first),
    ``failures`` largest group first, ``stats`` as recorded."""

    run_id: str
    job: str
    session: date
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None
    items_total: int
    items_by_status: dict[str, int]
    failures: tuple[FailureGroup, ...]
    stats: dict[str, Any]


@dataclass(frozen=True)
class RunItem:
    """One item of a run: ``key`` (a ticker, an instrument id, a step, a check), its status
    ``code`` (``STALE_DATA``) and ``status`` as recorded, with its detail."""

    key: str
    code: str
    status: str


def _duration(run: RunRecord) -> float | None:
    if run.finished_at is None:
        return None
    return round((run.finished_at - run.started_at).total_seconds(), 3)


def _steps(run: RunRecord) -> tuple[RunStep, ...]:
    stored = run.stats.get("steps")
    if not isinstance(stored, dict):  # a run that failed before recording its steps
        return tuple(RunStep(n, s, None, None, None, {}) for n, s in run.items.items())
    return tuple(
        RunStep(
            name=str(name),
            status=str(step.get("status", "")),
            duration_s=step.get("duration_s"),
            reason=step.get("reason"),
            error=step.get("error"),
            counts=dict(step.get("result") or {}),
        )
        for name, step in stored.items()
    )


def load_nightly_runs(ctx: Stores, limit: int = 10) -> tuple[NightlyRun, ...]:
    """The ``limit`` most recent nightly session runs, newest first."""
    runs = ctx.reader.runs(NIGHTLY)[-max(limit, 1) :]
    return tuple(
        NightlyRun(
            run_id=r.run_id,
            session=r.session_date,
            status=r.status.value,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_s=_duration(r),
            steps=_steps(r),
            problems=tuple(str(p) for key in ("partial", "failed") for p in r.stats.get(key) or []),
        )
        for r in reversed(runs)
    )


def failure_groups(items: dict[str, str]) -> tuple[FailureGroup, ...]:
    """Items whose status is not fine, grouped by normalised reason (largest group first)."""
    return tuple(
        FailureGroup(
            reason=reason,
            count=len(rows),
            examples=tuple(k for k, _ in rows[:EXAMPLES]),
            statuses=tuple(sorted({s for _, s in rows})[:EXAMPLES]),
        )
        for reason, rows in failed_items(items)
    )


def run_record(ctx: Stores, run_id: str) -> RunRecord | None:
    """One run record by id; ``None`` when there is none (or the id is not a valid key)."""
    try:
        return ctx.reader.run(run_id)
    except ValueError:  # not a valid storage key
        return None


def run_detail(run: RunRecord) -> RunDetail:
    """``run`` with its items summarised and its failures grouped."""
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


def load_run(ctx: Stores, run_id: str) -> RunDetail | None:
    """The run record ``run_id``; ``None`` when there is none."""
    run = run_record(ctx, run_id)
    return run_detail(run) if run is not None else None


def load_run_items(ctx: Stores, run_id: str) -> tuple[RunItem, ...] | None:
    """Every item of the run ``run_id`` with its status, sorted by key (the run-record drawer
    and its CSV); ``None`` when there is no such run."""
    run = run_record(ctx, run_id)
    if run is None:
        return None
    return tuple(RunItem(k, status_code(str(s)), str(s)) for k, s in sorted(run.items.items()))
