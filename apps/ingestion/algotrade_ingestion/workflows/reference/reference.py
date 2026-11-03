"""The reference workflow (ADR 0039, WF4): the weekly refresh of what changes slowly.

``company-details``, ``shares``, ``macro-calendar``, ``ibkr-contracts`` and the ETF holdings
slots (``etf-holdings`` with ``weekly``: a week of its per-night cap) are not market data and no
screen needs them the night they are fetched, so they left the nightly (``market-daily``). Each
keeps its own refresh slots (``tasks/framework/refresh.py``), so the SEC and vendor load stays
spread over the window; a name new to the universe waits for the next run (at most a week) and
its reference facts are UNKNOWN until then (ADR 0036).

Every step is optional: a failed one is a warning and an alert (``reference_notice``), never a
held-back session. The run has its own record (``REFERENCE_RUN``, one per attempt, session = the
last closed session) and runs the same engine as the nightly (``run_step``, ``run_isolated``).

Locks. The whole run holds the named lock ``reference`` (taken by the CLI; a second run is
``busy``). Each step runs in its own block under the ingest lock (``hold``, waiting for it) and
releases it before the next, so a nightly can start between two steps; the run also stops
(``yielded``: the rest NOT_RUN) the moment a nightly is pending (``nightly_pending``), because a
file lock is not fair and the nightly's start does not wait. The first locked block recovers
unpublished writes of a crashed ingest (``recover_unpublished``), as the CLI does for a run that
holds the lock for its whole length.

When it runs (``due``): once per ISO week of the last closed session, on a weekend (New York
time) or, when no published run is 8 days old, any day, and only while no nightly or post-session
run is pending. A week counts as done when a run had no FAILED or NOT_RUN step, or after
``MAX_ATTEMPTS`` runs with a FAILED step (a vendor outage then waits for the next week).
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from algotrade.config.site.settings import NightlySettings, load_nightly
from algotrade.core.time.calendar import exchange_date, is_weekend, last_closed_session
from algotrade.services.jobs import JobContext
from algotrade.services.jobs.exclusive import RunLockedError, exclusive_run
from algotrade.storage.runs import RunRecord, published
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext, recover_unpublished
from algotrade_ingestion.tasks.maintenance.quality import check_macro_calendar
from algotrade_ingestion.workflows.nightly.nightly import (
    job_task_context,
    run_step,
    skip_reason,
    step_item,
    universe_exists,
)
from algotrade_ingestion.workflows.nightly.notify import Notice, Notifier, default_notifier
from algotrade_ingestion.workflows.nightly.sessions import last_done
from algotrade_ingestion.workflows.nightly.steps import (
    Status,
    Step,
    StepResult,
    StepStatus,
    parse_status,
)

REFERENCE_RUN = "reference"  # the job name of the run records
REFERENCE_LOCK = "reference"  # the named lock one run holds (a second one: busy)
BUSY = "BUSY"
MAX_ATTEMPTS = 3  # runs with a FAILED step in one week before the week counts as done
OVERDUE = timedelta(days=8)  # no published run for this long: a weekday run is due too
YIELDED = "yielded to a pending nightly"
WEEKLY = {"weekly": True}  # the registry tasks scale their per-night caps to the week

REFERENCE: tuple[Step, ...] = (
    Step("company-details", critical=False, params=WEEKLY),  # SEC company facts and addresses
    Step("shares", critical=False, params=WEEKLY),  # share counts, statements (ADR 0067)
    # The macro release calendar (ADR 0050): FRED off or no key: SKIPPED.
    Step("macro-calendar", critical=False, accept_with=(check_macro_calendar,)),
    # IBKR conids for new optionable names and the monthly refresh (read-only, ADR 0026):
    # SKIPPED with a WARN without the gateway.
    Step("ibkr-contracts", critical=False, requires=universe_exists),
    # The weekly slots of every fund's holdings (ADR 0035); the daily files stay nightly.
    Step("etf-holdings", critical=False, requires=universe_exists, params=WEEKLY),
)
REFERENCE_STEPS = tuple(s.name for s in REFERENCE)

type Hold = Callable[[], AbstractContextManager[Any]]
type Pending = Callable[[], bool]


@dataclass(frozen=True)
class Week:
    """What a week's published reference runs say (``week_state``)."""

    clean: bool  # a run with every step SUCCEEDED or SKIPPED
    failed_attempts: int  # runs with a FAILED step
    newest: datetime | None  # when the newest clean run started


def _week(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return iso.year, iso.week


def _clean(record: RunRecord) -> bool:
    steps = (record.stats.get("steps") or {}).values()
    return all(
        parse_status(str(s.get("status"))) in (StepStatus.SUCCEEDED, StepStatus.SKIPPED)
        for s in steps
    )


def _failed(record: RunRecord) -> bool:
    steps = (record.stats.get("steps") or {}).values()
    return any(parse_status(str(s.get("status"))) is StepStatus.FAILED for s in steps)


def week_state(records: Sequence[RunRecord], session: date) -> Week:
    """The published runs of ``session``'s ISO week."""
    pool = [r for r in records if published(r)]
    mine = [r for r in pool if _week(r.session_date) == _week(session)]
    # the overdue clock runs from the last clean run: a failed or yielded one never resets it
    newest = max((r.started_at for r in pool if _clean(r)), default=None)
    return Week(any(_clean(r) for r in mine), sum(1 for r in mine if _failed(r)), newest)


def due(week: Week, now: datetime, quiet: bool) -> str | None:
    """Why a reference run should start now, else ``None``. ``quiet``: no nightly or
    post-session run is pending."""
    if week.clean or week.failed_attempts >= MAX_ATTEMPTS or not quiet:
        return None
    if is_weekend(exchange_date(now)):  # New York's calendar day
        return "weekend"
    if week.newest is None or now - week.newest > OVERDUE:
        return "overdue"
    return None


def nightly_pending(writer: StoreWriter, now: datetime, settings: NightlySettings) -> bool:
    """A closed session has no done nightly yet (so the nightly will, or does, want the lock)."""
    closed = last_closed_session(now, timedelta(minutes=settings.settle_minutes))
    done = last_done(writer)
    return done is None or done < closed


def _step(step: Step, ctx: TaskContext, session: date) -> StepResult:
    reason = skip_reason(step.name, ctx)
    if reason is not None:
        return StepResult(step.name, StepStatus.SKIPPED, step.critical, reason=reason)
    return run_step(step, ctx, session, {}, None)


def run_reference(
    ctx: TaskContext,
    session: date,
    settings: NightlySettings | None = None,
    hold: Hold | None = None,
    pending: Pending | None = None,
) -> dict[str, Any]:
    """The reference steps for ``session`` (the last closed one); saves a ``reference`` run record.
    ``hold``: the ingest-lock context each step runs under (none: no lock, tests); ``pending``:
    whether a nightly is waiting, checked before each step. -> the summary; ``status`` ``BUSY``
    (and no record) when the first step could not take the lock."""
    settings = settings or NightlySettings()
    started = ctx.clock()
    done: dict[str, StepResult] = {}
    recovered = False
    for step in REFERENCE:
        if pending is not None and pending():
            done[step.name] = StepResult(
                step.name, StepStatus.NOT_RUN, step.critical, reason=YIELDED
            )
            continue
        try:
            with hold() if hold else nullcontext():
                if not recovered:  # a crashed ingest's unpublished writes, as a CLI run does
                    recover_unpublished(ctx.writer, ctx.clock())
                    recovered = True
                done[step.name] = _step(step, ctx, session)
        except RunLockedError as busy:
            return {"session": session.isoformat(), "status": BUSY, "reason": str(busy)}
    with IngestRun(ctx, REFERENCE_RUN, session) as run:
        for name, result in done.items():
            run.record_item(name, step_item(result))
        steps = {name: r.as_dict() for name, r in done.items()}
        run.stats["steps"] = steps
    finished = ctx.clock()
    warnings = [
        {"check": "optional_step", "status": "WARN", "detail": f"{n}: {r.error or r.reason}"}
        for n, r in done.items()
        if r.status is StepStatus.FAILED
    ]
    return {
        "session": session.isoformat(),
        "status": Status.SUCCEEDED.value,
        "run_id": run.run_id,
        "steps": steps,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": round((finished - started).total_seconds(), 3),
        "warnings": warnings,
    }


def reference_notice(summary: Mapping[str, Any]) -> Notice:
    """The notice for a run: FAILED (an alert, as a failed nightly step) when a step failed, else
    SUCCEEDED (no alert). A step that yielded to the nightly is no failure."""
    failed = sorted(n for n, s in summary["steps"].items() if s["status"] == StepStatus.FAILED)
    status = "FAILED" if failed else Status.SUCCEEDED.value
    detail = f": {', '.join(failed)} failed" if failed else ""
    return Notice(status, "algotrade reference", f"{status} ({summary['session']}){detail}")


def _notify(summary: dict[str, Any], notifier: Notifier, settings: NightlySettings) -> None:
    if not settings.notify_enabled or summary["status"] == BUSY:
        return
    try:
        problem = notifier.notify(reference_notice(summary))
    except Exception as exc:  # a notifier must not raise; if one does, it is a warning
        problem = f"notifier failed: {type(exc).__name__}: {exc}"
    if problem:
        warn = {"check": "notify", "status": "WARN", "detail": problem}
        summary["warnings"] = [*summary.get("warnings", []), warn]


def reference_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """Job handler. params: ``session`` (the last closed session); ``yield`` (stop when a nightly is
    pending: a scheduled run; a run by hand with ``--date`` / ``--force`` goes on). The per-step
    ingest lock is always waited for (a nightly in flight is no error). Resources: the nightly's."""
    r = ctx.resources
    task_ctx = job_task_context(ctx)
    backend = task_ctx.writer.backend
    settings = load_nightly(r["configs"])
    summary = run_reference(
        task_ctx,
        date.fromisoformat(params["session"]),
        settings,
        lambda: exclusive_run(backend, wait=True),
        lambda: (
            bool(params.get("yield"))
            and nightly_pending(task_ctx.writer, datetime.now(UTC), settings)
        ),
    )
    _notify(summary, r.get("notifier") or default_notifier(settings), settings)
    return {**summary, "_partial": summary["status"] != Status.SUCCEEDED}
