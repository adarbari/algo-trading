"""The nightly workflow: ordered, isolated registry tasks for each session to catch up.

For each session (``sessions.plan_sessions``; oldest first) the steps in ``NIGHTLY`` run in
order through ``tasks/framework/registry.py``, each isolated (``steps.run_isolated``): a step that
raises is FAILED and later steps still run, unless they name it in ``blocked_by``. Sources
that only serve the current snapshot (universe files, SEC, Cboe chains) run only for the
latest closed session; bars, rates, corporate actions, earnings and rollups catch up (rollups
after the data they read; one whose input a session lacks, e.g. option liquidity without that
session's chains, reports ``no_input``). ``quality`` ends every
session and the ``purge-raw`` task ends the run, whatever failed before; then
``notify.report`` writes the summary file and sends the notifications (the summary email every
night). Each session gets a ``nightly`` run record (COMPLETE / PARTIAL / FAILED, per
``steps.overall``), which is how the next run knows where to resume.
"""

from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from algotrade.config.site.settings import NightlySettings, SourcesSettings, load_nightly
from algotrade.data.reference import snapshot
from algotrade.services.jobs import JobContext
from algotrade_ingestion.tasks.framework.registry import TASKS, run_task, task
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.workflows.nightly.notify import Notifier, default_notifier, report
from algotrade_ingestion.workflows.nightly.screens import ScreenStep, screen_jobs
from algotrade_ingestion.workflows.nightly.sessions import (
    NIGHTLY_RUN,
    Plan,
    last_done,
    plan_sessions,
)
from algotrade_ingestion.workflows.nightly.steps import (
    Outcome,
    Status,
    Step,
    StepResult,
    StepStatus,
    from_record,
    overall,
    run_isolated,
)

SCREENS = "screens"  # not an ingestion task: one `screen` job per scheduled screener
PURGE = "purge-raw"
LATEST_ONLY = "latest closed session only (the source serves the current snapshot)"


def universe_exists(ctx: TaskContext, session: date) -> str | None:
    """Chains and screens need a universe snapshot (not today's build passing)."""
    if snapshot(ctx.reader, "universe", session) is None:
        return f"no universe snapshot for {session}"
    return None


NIGHTLY: tuple[Step, ...] = (
    Step("universe-build", latest_only=True),
    Step("company-details", latest_only=True),
    Step("shares", latest_only=True),
    Step("earnings"),
    Step("bars"),
    Step("rates"),
    Step("corporate-actions"),
    Step("chains", requires=universe_exists, latest_only=True),
    # Every session (catch-up too): a rollup whose input is missing reports no_input.
    Step("rollups"),
    Step(SCREENS, blocked_by=("chains", "rollups"), requires=universe_exists, latest_only=True),
    Step("quality"),  # always last in a session
)
FINALLY: tuple[Step, ...] = (Step(PURGE),)  # once, after every session


def skip_reason(name: str, ctx: TaskContext) -> str | None:
    """Why a workflow skips a registry task: a needed source is not built, or its rule."""
    spec = task(name)
    missing = [s for s in spec.sources if s not in ctx.sources]
    if missing:
        reasons = sorted({ctx.unavailable.get(s, f"{s} is not configured") for s in missing})
        return f"skipped: {'; '.join(reasons)}"
    return spec.skip(ctx) if spec.skip else None


def _not_run(
    step: Step, ctx: TaskContext, latest: bool, done: Mapping[str, StepResult]
) -> StepResult | None:
    """A SKIPPED / BLOCKED result when the step must not run, else ``None``."""
    if step.latest_only and not latest:
        return StepResult(step.name, StepStatus.SKIPPED, reason=LATEST_ONLY)
    failed = [
        d
        for d in step.blocked_by
        if d in done and done[d].status in (StepStatus.FAILED, StepStatus.BLOCKED)
    ]
    if failed:
        return StepResult(step.name, StepStatus.BLOCKED, reason=f"{', '.join(failed)} failed")
    reason = skip_reason(step.name, ctx) if step.name in TASKS else None
    return StepResult(step.name, StepStatus.SKIPPED, reason=reason) if reason else None


def run_step(
    step: Step,
    ctx: TaskContext,
    session: date,
    params: Mapping[str, Any],
    screens: ScreenStep | None,
) -> StepResult:
    """One step, isolated: its precondition, then the registry task (or the screen jobs)."""

    def body() -> Outcome:
        if step.requires is not None and (why := step.requires(ctx, session)):
            return Outcome(StepStatus.BLOCKED, reason=why)
        if step.name == SCREENS:
            if screens is None:
                return Outcome(StepStatus.SKIPPED, reason="no job runner to submit screens to")
            return screens(session)
        return from_record(run_task(step.name, ctx, {**params, "session": session}))

    return run_isolated(step.name, body, ctx.clock)


def run_session(
    ctx: TaskContext,
    session: date,
    latest: bool,
    screens: ScreenStep | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Every ``NIGHTLY`` step for one session; saves the session's ``nightly`` run record."""
    done: dict[str, StepResult] = {}
    with IngestRun(ctx, NIGHTLY_RUN, session) as run:
        for step in NIGHTLY:
            skipped = _not_run(step, ctx, latest, done)
            done[step.name] = skipped or run_step(step, ctx, session, {"workers": workers}, screens)
            run.record_item(step.name, done[step.name].status.value)
        status = overall(r.status for r in done.values())
        bad = [
            n for n, r in done.items() if r.status not in (StepStatus.COMPLETE, StepStatus.SKIPPED)
        ]
        if status is Status.FAILED:
            run.failed("no step succeeded")
        elif status is Status.PARTIAL:
            run.partial(f"steps not complete: {', '.join(bad)}")
        steps = {name: r.as_dict() for name, r in done.items()}
        run.stats["steps"] = steps
    return {"session": session.isoformat(), "status": status.value, "steps": steps}


def _minutes(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60


def run_nightly(
    ctx: TaskContext,
    plan: Plan,
    settings: NightlySettings | None = None,
    screens: ScreenStep | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Every planned session, then ``FINALLY``. -> the run summary (status, per-session
    steps with status and duration, start / finish, catch-up, warnings)."""
    settings = settings or NightlySettings()
    started = ctx.clock()
    runs = [run_session(ctx, s, s == plan.latest, screens, workers) for s in plan.sessions]
    reference = plan.latest or plan.last_done
    final: dict[str, StepResult] = {}
    if reference is not None:
        for step in FINALLY:
            final[step.name] = run_step(step, ctx, reference, {}, screens)
    statuses = [StepStatus(s["status"]) for r in runs for s in r["steps"].values()]
    status = overall([*statuses, *(r.status for r in final.values())])
    finished = ctx.clock()
    minutes = _minutes(started, finished)
    warnings = []
    if minutes > settings.max_duration_minutes:
        warnings.append(
            {
                "check": "nightly_duration",
                "status": "WARN",
                "detail": f"nightly took {minutes:.1f} min "
                f"(alert above {settings.max_duration_minutes:g} min)",
            }
        )
    return {
        "status": status.value,
        "sessions": [s.isoformat() for s in plan.sessions],
        "catch_up": {
            "last_done": plan.last_done.isoformat() if plan.last_done else None,
            "dropped": [d.isoformat() for d in plan.dropped],
        },
        "runs": runs,
        "steps": {name: r.as_dict() for name, r in final.items()},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": round(minutes * 60, 3),
        "warnings": warnings,
    }


def nightly_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """Job handler for the nightly workflow. params: ``session`` (the last closed session),
    ``catch_up`` (also run sessions missed since the last nightly), ``export_dir``,
    ``workers``. Resources: ``reader``, ``writer``, ``configs``, ``sources`` (by name),
    ``sources_settings``, ``unavailable`` (source -> why it was not built), ``raw_sections``
    (raw source -> sources.toml section, for retention), optional ``notifier``."""
    r = ctx.resources
    task_ctx = TaskContext(
        r["reader"],
        r["writer"],
        r.get("sources", {}),
        r.get("sources_settings") or SourcesSettings(),
        r["configs"],
        user=ctx.user.user_id,
        unavailable=r.get("unavailable", {}),
        raw_sections=r.get("raw_sections", {}),
    )
    settings = load_nightly(r["configs"])
    session = date.fromisoformat(params["session"])
    if params.get("catch_up"):
        plan = plan_sessions(last_done(task_ctx.writer), session, settings.max_catch_up)
    else:
        plan = Plan([session])
    export_dir = Path(params["export_dir"]) if params.get("export_dir") else None
    screens = screen_jobs(ctx.jobs, r["configs"], export_dir) if ctx.jobs else None
    workers = int(params["workers"]) if params.get("workers") else None
    summary = run_nightly(task_ctx, plan, settings, screens, workers)
    notifier: Notifier = r.get("notifier") or default_notifier(settings)
    summary = report(summary, settings, notifier, task_ctx.reader)
    return {**summary, "_partial": summary["status"] != Status.COMPLETE}
