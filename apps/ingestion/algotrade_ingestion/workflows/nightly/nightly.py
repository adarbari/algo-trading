"""The nightly workflow (ADR 0039): a DAG of registry tasks per session, oldest session first.

For each session (``sessions.plan_sessions``) the steps in ``NIGHTLY`` run in order through
``tasks/framework/registry.py``, each isolated (``steps.run_isolated``). A step runs only when
every step it ``needs`` is satisfied (SUCCEEDED, WAIVED, or SKIPPED as not applicable);
otherwise it is NOT_RUN, so nothing runs on missing or partial input. A step that runs either
SUCCEEDS or FAILS: its task must not fail, and its acceptance checks (``tasks/maintenance/
quality.py``, run right after it) must not FAIL. A failed critical step makes the session
FAILED; an optional step's failure is a warning. A FAILED session holds every later one back:
the run stops there, and the next run retries it from where it stopped (``attempts.py``:
steps that SUCCEEDED or were WAIVED are not rerun). A latest-only step (universe files, SEC,
Cboe chains: sources that serve only the current snapshot) runs only for the last closed
session; one that failed and whose session is no longer the latest FAILS as expired until it
is waived by hand (``algotrade-ingest nightly --date D --waive STEP --reason ...``).

A step whose source has not published the latest session yet is WAITING, not FAILED, until its
deadline (``[schedule] data_deadline``, ADR 0043; ``waits``): the session is WAITING, holds
later sessions back like a failed one, is not done (the next hourly run resumes it) and sends
no alert. A catch-up session (not the latest) is past its deadline: FAILED as before.

``purge-raw`` ends the run whatever failed before; then ``notify.report`` writes the summary
file and sends the notifications. Each session gets a ``nightly`` run record (COMPLETE when
the session SUCCEEDED, else FAILED) holding every step's result, which is how the next run
knows where to resume.
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from algotrade.config.site.settings import NightlySettings, SourcesSettings, load_nightly
from algotrade.core.time.calendar import last_closed_session, local_deadline
from algotrade.data.reference import snapshot
from algotrade.services.jobs import JobContext
from algotrade_ingestion.tasks.framework.registry import TASKS, run_task, task
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext, utc_now
from algotrade_ingestion.tasks.maintenance.coverage import check_coverage
from algotrade_ingestion.tasks.maintenance.quality import (
    check_bars,
    check_bars_resolved,
    check_chains,
    check_earnings,
    check_universe,
    check_verification,
)
from algotrade_ingestion.workflows.nightly.attempts import Attempts, earlier_attempts
from algotrade_ingestion.workflows.nightly.notify import Notifier, default_notifier, report
from algotrade_ingestion.workflows.nightly.screens import ScreenStep, screen_jobs
from algotrade_ingestion.workflows.nightly.sessions import (
    NIGHTLY_RUN,
    Plan,
    last_done,
    plan_sessions,
)
from algotrade_ingestion.workflows.nightly.steps import (
    BAD,
    Outcome,
    Status,
    Step,
    StepResult,
    StepStatus,
    from_record,
    overall,
    run_isolated,
    unsatisfied,
)

SCREENS = "screens"  # not an ingestion task: one `screen` job per screener
PURGE = "purge-raw"
LATEST_ONLY = "latest closed session only (the source serves the current snapshot)"
MARKET_DATA = ("bars", "rates", "corporate-actions", "earnings", "chains")


def universe_exists(ctx: TaskContext, session: date) -> str | None:
    """Chains and screens need a universe snapshot for the session."""
    if snapshot(ctx.reader, "universe", session) is None:
        return f"no universe snapshot for {session}"
    return None


NIGHTLY: tuple[Step, ...] = (
    Step("universe-build", latest_only=True, accept=(check_universe,), task_complete=True),
    # Reference data (ADR 0039: moves to the weekly `reference` workflow in WF4): optional.
    Step("company-details", latest_only=True, critical=False),
    Step("shares", latest_only=True, critical=False),
    Step("earnings", accept=(check_earnings,), task_complete=True),
    Step("bars", accept=(check_bars, check_bars_resolved)),
    Step("rates", task_complete=True),
    Step("corporate-actions", task_complete=True),
    # Chains finish PARTIAL by design (NO_CHAIN and the like are items); the checks decide.
    # They need a universe snapshot, not today's build to succeed: chains can be fetched only
    # for the current session, and a failed build already fails the session and holds the
    # screens back (owner-delegated decision, 2026-10-05; amends ADR 0039's graph).
    Step(
        "chains",
        requires=universe_exists,
        latest_only=True,
        accept=(check_chains,),
    ),
    # What each ETF holds (ADR 0035): issuer files, a weekly slot per fund, at most
    # [etf_holdings] per_night funds a night (new and stalest first). Optional.
    Step(
        "etf-holdings",
        needs=("universe-build",),
        requires=universe_exists,
        latest_only=True,
        critical=False,
        params={"nightly": True},
    ),
    # IBKR enrichment (ADR 0028), read-only, SKIPPED with a WARN when [ibkr] is disabled or IB
    # Gateway is not reachable: conids for new optionable names (and the monthly refresh),
    # then the session's IV snapshot (+ a capped history backfill) for ibkr_iv@v1. Optional:
    # IV rank falls back to ours, labelled.
    Step(
        "ibkr-contracts",
        needs=("universe-build",),
        requires=universe_exists,
        latest_only=True,
        critical=False,
    ),
    Step(
        "ibkr-iv",
        needs=("ibkr-contracts",),
        requires=universe_exists,
        latest_only=True,
        critical=False,
    ),
    # Every session (catch-up too), after the market data it reads. A rollup that raises
    # (a gap in a lookback window included) fails the step.
    # Its acceptance is the coverage of the key features by tier (ADR 0043): a FAIL-level breach
    # (core-tier prices) fails the step and holds the screens back; the rest are warnings.
    Step("rollups", needs=MARKET_DATA, accept=(check_coverage,), task_complete=True),
    Step(SCREENS, needs=("chains", "rollups"), requires=universe_exists, latest_only=True),
    # Company and ETF descriptions (ADR 0034): after the screens, so the Massive requests
    # (capped per night, ~21 min) do not delay them. Optional.
    Step("descriptions", latest_only=True, critical=False),
    # Read-only live verification vs IBKR (ADR 0026): SKIPPED with a WARN when [ibkr] is
    # disabled or IB Gateway is not reachable; optional.
    Step("verify", latest_only=True, critical=False, accept=(check_verification,)),
)
FINALLY: tuple[Step, ...] = (Step(PURGE, critical=False),)  # once, after every session


def skip_reason(name: str, ctx: TaskContext) -> str | None:
    """Why a workflow skips a registry task: a needed source is not built, or its rule."""
    spec = task(name)
    missing = [s for s in spec.sources if s not in ctx.sources]
    if missing:
        reasons = sorted({ctx.unavailable.get(s, f"{s} is not configured") for s in missing})
        return f"skipped: {'; '.join(reasons)}"
    return spec.skip(ctx) if spec.skip else None


def _sources_missing(name: str, ctx: TaskContext) -> bool:
    return name in TASKS and any(s not in ctx.sources for s in task(name).sources)


def _held(step: Step, status: StepStatus, reason: str) -> StepResult:
    return StepResult(step.name, status, step.critical, reason=reason)


def _carried(
    step: Step, ctx: TaskContext, before: Attempts, waive: Mapping[str, str]
) -> StepResult | None:
    """Done before (an earlier attempt SUCCEEDED or WAIVED it) or waived now, else ``None``."""
    if step.name in before.done:
        stored = before.done[step.name]
        why = f"{stored['status'].lower()} in an earlier attempt ({stored['run_id']})"
        return _held(step, StepStatus(stored["status"]), why)
    if step.name in waive:
        who = f"waived by {ctx.user} at {ctx.clock().isoformat(timespec='seconds')}"
        return _held(step, StepStatus.WAIVED, f"{who}: {waive[step.name]}")
    return None


def _not_latest(step: Step, before: Attempts) -> StepResult:
    """A latest-only step for an older session: SKIPPED, or FAILED as expired when an
    earlier attempt tried it without success (it can no longer be fetched)."""
    if step.critical and step.name in before.tried:
        why = (
            "expired: the source serves only the current snapshot and this session is no "
            "longer the latest; accept the gap with `algotrade-ingest nightly --date "
            f"<session> --waive {step.name} --reason ...`"
        )
        return _held(step, StepStatus.FAILED, why)
    return _held(step, StepStatus.SKIPPED, LATEST_ONLY)


def _not_run(
    step: Step,
    ctx: TaskContext,
    latest: bool,
    done: Mapping[str, StepResult],
    before: Attempts,
    waive: Mapping[str, str],
) -> StepResult | None:
    """The step's result when it must not run (reused, waived, skipped, expired, held
    back), else ``None``."""
    carried = _carried(step, ctx, before, waive)
    if carried is not None:
        return carried
    if step.latest_only and not latest:
        return _not_latest(step, before)
    held = unsatisfied(step.needs, done)
    if held:
        result = _held(step, StepStatus.NOT_RUN, f"needs {', '.join(held)}")
        unmet = [done[n] for n in step.needs if n in done and done[n].status in BAD]
        result.held_by_wait = all(r.status is StepStatus.WAITING or r.held_by_wait for r in unmet)
        return result
    reason = skip_reason(step.name, ctx) if step.name in TASKS else None
    if reason is None:
        return None
    if step.critical and _sources_missing(step.name, ctx):  # a critical source must exist
        return _held(step, StepStatus.FAILED, reason.removeprefix("skipped: "))
    return _held(step, StepStatus.SKIPPED, reason)


def waits(
    step: Step, ctx: TaskContext, session: date, latest: bool, settings: NightlySettings
) -> bool:
    """Whether ``step`` may WAIT for its source to publish ``session``: only the latest
    session, and only before the step's deadline (Los Angeles time on the session's date)."""
    deadline = local_deadline(session, settings.deadline_for(step.name))
    return latest and ctx.clock() < deadline


def run_step(
    step: Step,
    ctx: TaskContext,
    session: date,
    params: Mapping[str, Any],
    screens: ScreenStep | None,
    wait: bool = False,
) -> StepResult:
    """One step, isolated: its precondition, the registry task (or the screen jobs), then
    its acceptance checks (``wait``: a pending failure is WAITING, not FAILED)."""

    def body() -> Outcome:
        if step.requires is not None and (why := step.requires(ctx, session)):
            return Outcome(StepStatus.NOT_RUN, reason=why)
        if step.name == SCREENS:
            if screens is None:
                return Outcome(StepStatus.SKIPPED, reason="no job runner to submit screens to")
            return screens(session)
        record = run_task(step.name, ctx, {**params, **step.params, "session": session})
        return from_record(record, step, ctx, session, wait)

    return run_isolated(step.name, body, ctx.clock, step.critical)


def run_session(
    ctx: TaskContext,
    session: date,
    latest: bool,
    screens: ScreenStep | None = None,
    workers: int | None = None,
    resume: bool = True,
    waive: Mapping[str, str] | None = None,
    settings: NightlySettings | None = None,
) -> dict[str, Any]:
    """Every ``NIGHTLY`` step for one session; saves the session's ``nightly`` run record.
    ``resume``: reuse the steps an earlier attempt of the session did; ``waive``: step ->
    reason, accepted by hand; ``settings``: the deadlines a step may wait until."""
    settings = settings or NightlySettings()
    before = earlier_attempts(ctx.reader, session) if resume else Attempts()
    done: dict[str, StepResult] = {}
    with IngestRun(ctx, NIGHTLY_RUN, session) as run:
        for step in NIGHTLY:
            held = _not_run(step, ctx, latest, done, before, waive or {})
            wait = waits(step, ctx, session, latest, settings)
            done[step.name] = held or run_step(
                step, ctx, session, {"workers": workers}, screens, wait
            )
            run.record_item(step.name, _item(done[step.name]))
        status = overall(done.values())
        failed = [
            f"{n}: {r.error or r.reason or r.status.value}"
            for n, r in done.items()
            if r.critical and r.status in BAD
        ]
        if status is Status.FAILED:
            run.failed(f"critical steps not done: {'; '.join(failed)}")
        elif status is Status.WAITING:  # not done either: the next run resumes it (ADR 0043)
            run.waiting(f"waiting for publication: {'; '.join(failed)}")
        steps = {name: r.as_dict() for name, r in done.items()}
        run.stats["steps"] = steps
    return {"session": session.isoformat(), "status": status.value, "steps": steps}


def _item(result: StepResult) -> str:
    """A step's item in the session's run record: an optional step's failure is a WARN, so it
    never makes the record PARTIAL (the session's status is ``overall``'s alone)."""
    if not result.critical and result.status is StepStatus.FAILED:
        return "WARN: FAILED (optional step)"
    return result.status.value


def _minutes(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60


def run_nightly(
    ctx: TaskContext,
    plan: Plan,
    settings: NightlySettings | None = None,
    screens: ScreenStep | None = None,
    workers: int | None = None,
    resume: bool = True,
    waive: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The planned sessions, oldest first, stopping at the first that FAILS (the later ones
    are ``held``); then ``FINALLY``. -> the run summary (status, per-session steps with
    status and duration, start / finish, catch-up, warnings)."""
    settings = settings or NightlySettings()
    started = ctx.clock()
    runs: list[dict[str, Any]] = []
    held: list[date] = []
    for session in plan.sessions:
        if runs and runs[-1]["status"] != Status.SUCCEEDED:  # failed or waiting
            held.append(session)
            continue
        runs.append(
            run_session(
                ctx, session, session == plan.latest, screens, workers, resume, waive, settings
            )
        )
    ran = [date.fromisoformat(r["session"]) for r in runs]
    reference = ran[-1] if ran else plan.last_done
    final: dict[str, StepResult] = {}
    if reference is not None:
        for step in FINALLY:
            final[step.name] = run_step(step, ctx, reference, {}, screens)
    statuses = {r["status"] for r in runs}
    status = Status.SUCCEEDED
    if Status.FAILED in statuses:
        status = Status.FAILED
    elif Status.WAITING in statuses:
        status = Status.WAITING
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
    optional = [
        f"{r['session']} {name}: {s.get('error') or s.get('reason') or s['status']}"
        for r in runs
        for name, s in r["steps"].items()
        if not s["critical"] and s["status"] == StepStatus.FAILED
    ]
    warnings += [{"check": "optional_step", "status": "WARN", "detail": d} for d in optional]
    return {
        "status": status.value,
        "sessions": [s.isoformat() for s in plan.sessions if s not in held],
        "catch_up": {
            "last_done": plan.last_done.isoformat() if plan.last_done else None,
            "held": [d.isoformat() for d in held],
            "waiting": [d.isoformat() for d in plan.waiting],
        },
        "runs": runs,
        "steps": {name: r.as_dict() for name, r in final.items()},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": round(minutes * 60, 3),
        "warnings": warnings,
    }


def nightly_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """Job handler for the nightly workflow. params: ``session`` (the last closed session, or
    the ``--date``), ``catch_up`` (also run the sessions pending since the last nightly),
    ``resume`` (default true: reuse what earlier attempts of a session did; false reruns
    every step), ``waive`` (step -> reason), ``export_dir``, ``workers``. Resources:
    ``reader``, ``writer``, ``configs``, ``sources`` (by name), ``sources_settings``,
    ``unavailable`` (source -> why it was not built), ``raw_sections`` (raw source ->
    sources.toml section, for retention), ``pacing`` (limiter key -> limiter, for pacing
    stats in run records), optional ``notifier`` and ``clock`` (tests)."""
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
        pacing=r.get("pacing", {}),
        clock=r.get("clock") or utc_now,
    )
    settings = load_nightly(r["configs"])
    session = date.fromisoformat(params["session"])
    until = last_closed_session(task_ctx.clock(), timedelta(minutes=settings.settle_minutes))
    if params.get("catch_up"):
        plan = plan_sessions(last_done(task_ctx.writer), session, settings.max_catch_up)
    else:  # `--date`: latest-only steps run only when it is the last closed session
        plan = Plan([session], until=max(until, session))
    export_dir = Path(params["export_dir"]) if params.get("export_dir") else None
    screens = screen_jobs(ctx.jobs, r["configs"], export_dir) if ctx.jobs else None
    workers = int(params["workers"]) if params.get("workers") else None
    resume = bool(params.get("resume", True))
    waive = dict(params.get("waive") or {})
    summary = run_nightly(task_ctx, plan, settings, screens, workers, resume, waive)
    notifier: Notifier = r.get("notifier") or default_notifier(settings)
    summary = report(summary, settings, notifier, task_ctx.reader)
    return {**summary, "_partial": summary["status"] != Status.SUCCEEDED}
