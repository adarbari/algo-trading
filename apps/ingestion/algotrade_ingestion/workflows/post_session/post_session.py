"""The post-session workflow (ADR 0070): what runs after a session's nightly is COMPLETE.

``descriptions`` (ADR 0034), ``verify`` (ADR 0026) and ``edge-eval`` (ADR 0063) do not feed a
session's reads, so they used to delay its ``nightly`` record's COMPLETE for 3 to 20 hours for
nothing. They run here instead, as the ``post-session`` job with its own run record
(``POST_SESSION_RUN``, one per attempt, COMPLETE once it ran: every step is optional, a failed
one is a warning, never a retry loop). ``session_cutoff`` (ADR 0062) reads only the nightly's
record, so this run never moves it.

It runs only for the last session the nightly finished done (``target_session``): a catch-up
night's earlier sessions get no post-session run, as ``latest_only`` steps had none. It is a
no-op when a published post-session record of that session exists (``post_done``), so the
launchd watchdog (``ops/schedule.py``) starts it every half hour at no cost.

Locks: ``descriptions`` and ``verify`` write tables, so they run under the ingest run lock
(``hold``; busy: ``BUSY`` and nothing runs, a later start retries). ``edge-eval`` runs after,
outside it, under the owner's evaluation claim (``screens.edge_eval_jobs``); the whole run holds
the named lock ``post-session`` (taken by the CLI) so two never overlap. ``edge-eval`` is SKIPPED
with its reason when the session's ``outcomes`` step did not succeed in the nightly.
"""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from datetime import date
from typing import Any

from algotrade.config.site.settings import NightlySettings, load_nightly
from algotrade.services.jobs import JobContext
from algotrade.services.jobs.exclusive import RunLockedError, exclusive_run
from algotrade.storage.runs import done_sessions
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import check_verification
from algotrade_ingestion.workflows.nightly.nightly import (
    job_task_context,
    run_step,
    skip_reason,
    step_item,
)
from algotrade_ingestion.workflows.nightly.records import latest_nightly
from algotrade_ingestion.workflows.nightly.screens import ScreenStep, edge_eval_jobs
from algotrade_ingestion.workflows.nightly.sessions import POST_SESSION_RUN, POST_STEPS, last_done
from algotrade_ingestion.workflows.nightly.steps import (
    SATISFIED,
    Outcome,
    Status,
    Step,
    StepResult,
    StepStatus,
    parse_status,
    run_isolated,
)

EDGE_EVAL = POST_STEPS[2]  # not an ingestion task: one `edge-eval` job per open edge
POST_LOCK = "post-session"  # the named lock one post-session run holds (a second one: busy)
BUSY = "BUSY"  # the ingest lock was taken: nothing ran, a later start retries
POST_SESSION: tuple[Step, ...] = (
    # Company and ETF descriptions (ADR 0034): Massive requests capped per night (~25 min).
    Step("descriptions", critical=False),
    # Read-only live verification vs IBKR (ADR 0026): SKIPPED with a WARN when [ibkr] is
    # disabled or IB Gateway is not reachable (~40 min).
    Step("verify", critical=False, accept=(check_verification,)),
    # The evaluation of every open edge (ADR 0063): one job per edge as its owner; the weekly
    # audit when due (``screens.audit_due``), else incremental.
    Step(EDGE_EVAL, critical=False),
)
LOCKED = ("descriptions", "verify")  # the steps that run under the ingest lock

type Hold = Callable[[], AbstractContextManager[Any]]


def target_session(writer: StoreWriter) -> date | None:
    """The one session a post-session run is for: the last the nightly finished done."""
    return last_done(writer)


def post_done(writer: StoreWriter, session: date) -> bool:
    """A published post-session record of ``session`` exists (the run is then a no-op)."""
    return session in done_sessions(writer.runs_for(POST_SESSION_RUN))


def pending_session(writer: StoreWriter) -> date | None:
    """The session a scheduled start runs for: ``target_session`` unless it is already done."""
    target = target_session(writer)
    return None if target is None or post_done(writer, target) else target


def outcomes_gap(ctx: TaskContext, session: date) -> str | None:
    """Why ``edge-eval`` cannot trust the session's outcomes: the nightly's ``outcomes`` step did
    not succeed (``None``: it did, or the record names no such step)."""
    record = latest_nightly(ctx.reader, session)
    step = (record.stats.get("steps") or {}).get("outcomes") if record is not None else None
    if not isinstance(step, dict):
        return None
    status = parse_status(str(step.get("status")))
    return None if status in SATISFIED else f"outcomes {status.value} for {session}"


def _registry_step(step: Step, ctx: TaskContext, session: date) -> StepResult:
    """A registry task step, SKIPPED (with the reason) when its source is not built."""
    reason = skip_reason(step.name, ctx)
    if reason is not None:
        return StepResult(step.name, StepStatus.SKIPPED, step.critical, reason=reason)
    return run_step(step, ctx, session, {}, None)


def _edge_eval(step: Step, ctx: TaskContext, session: date, evals: ScreenStep | None) -> StepResult:
    def body() -> Outcome:
        if evals is None:
            return Outcome(StepStatus.SKIPPED, reason="no job runner to submit edge evaluations to")
        if (gap := outcomes_gap(ctx, session)) is not None:
            return Outcome(StepStatus.SKIPPED, {"evaluations": []}, reason=gap)
        return evals(session)

    return run_isolated(step.name, body, ctx.clock, step.critical)


def run_post_session(
    ctx: TaskContext,
    session: date,
    settings: NightlySettings | None = None,
    evals: ScreenStep | None = None,
    hold: Hold | None = None,
) -> dict[str, Any]:
    """The post-session steps for ``session``; saves the session's ``post-session`` run record.
    ``hold``: the ingest-lock context the locked steps run under (none: no lock, tests).
    -> the summary, with ``status`` ``BUSY`` (and no record) when the lock was taken."""
    settings = settings or NightlySettings()
    started = ctx.clock()
    done: dict[str, StepResult] = {}
    try:
        with hold() if hold else nullcontext():
            for step in POST_SESSION:
                if step.name in LOCKED:
                    done[step.name] = _registry_step(step, ctx, session)
    except RunLockedError as busy:
        return {"session": session.isoformat(), "status": BUSY, "reason": str(busy)}
    with IngestRun(ctx, POST_SESSION_RUN, session) as run:
        for step in POST_SESSION:
            if step.name not in LOCKED:
                done[step.name] = _edge_eval(step, ctx, session, evals)
        for name, result in done.items():
            run.record_item(name, step_item(result))
        steps = {name: r.as_dict() for name, r in done.items()}
        run.stats["steps"] = steps
    finished = ctx.clock()
    seconds = (finished - started).total_seconds()
    warnings = [
        {"check": "optional_step", "status": "WARN", "detail": f"{n}: {r.error or r.reason}"}
        for n, r in done.items()
        if r.status is StepStatus.FAILED
    ]
    if seconds / 60 > settings.post_max_duration_minutes:
        detail = f"post-session took {seconds / 60:.1f} min "
        detail += f"(alert above {settings.post_max_duration_minutes:g} min)"
        warnings.append({"check": "post_duration", "status": "WARN", "detail": detail})
    return {
        "session": session.isoformat(),
        "status": Status.SUCCEEDED.value,
        "run_id": run.run_id,
        "steps": steps,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": round(seconds, 3),
        "warnings": warnings,
    }


def post_session_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """Job handler for the post-session workflow. params: ``session`` (the nightly-done session
    to run for), ``wait`` (queue behind a running ingest instead of ``BUSY``). Resources as the
    nightly's (``reader``, ``writer``, ``configs``, ``sources``, ...)."""
    r = ctx.resources
    task_ctx = job_task_context(ctx)
    backend = task_ctx.writer.backend  # the owner claim and the ingest lock are the store's
    evals = edge_eval_jobs(ctx.jobs, r["configs"], task_ctx.reader, backend) if ctx.jobs else None
    summary = run_post_session(
        task_ctx,
        date.fromisoformat(params["session"]),
        load_nightly(r["configs"]),
        evals,
        lambda: exclusive_run(backend, wait=bool(params.get("wait"))),
    )
    return {**summary, "_partial": summary["status"] != Status.SUCCEEDED}
