"""The nightly workflow (ADR 0039): a DAG of registry tasks per session, oldest session first.

For each session (``sessions.plan_sessions``) the steps in ``NIGHTLY`` run in order through
``tasks/framework/registry.py``, each isolated (``steps.run_isolated``). A step runs only when
every step it ``needs`` is satisfied (SUCCEEDED, WAIVED, or SKIPPED as not applicable);
otherwise it is NOT_RUN, so nothing runs on missing or partial input. A step that runs either
SUCCEEDS or FAILS: its task must not fail, and its acceptance checks (``tasks/maintenance/
quality.py``, run right after it) must not FAIL. A failed critical step makes the session
FAILED; an optional step's failure is a warning. A FAILED session holds every later one back:
the run stops there, and the next run retries it from where it stopped (``attempts.py``:
steps that SUCCEEDED or were WAIVED are not rerun, except a resumable step (``Step.resumable``:
chains) that SUCCEEDED with items its task would refetch (STALE_DATA names Cboe had not rolled
over), which a retry re-runs while the session is the latest and the task's staging exists;
the steps that need it (rollups, market-rollups) re-run on the new data, so the screens do not
fail hourly on the same stale names. A refetch that fails keeps the earlier success. A done
step also re-runs when an optional input it does not need succeeds in a later attempt
(``Step.reruns_after``: the rollups after IBKR IV came back). A
latest-only step (universe files, SEC,
Cboe chains: sources that serve only the current snapshot) runs only for the last closed
session; one that failed and whose session is no longer the latest FAILS as expired until it
is waived by the owner only (``algotrade-ingest nightly --date D --waive STEP --reason ...``).

A step whose source has not published the latest session yet is WAITING, not FAILED, until its
deadline (``[schedule] data_deadline``, ADR 0043; ``waits``): the session is WAITING, holds
later sessions back like a failed one, is not done (the next hourly run resumes it) and sends
no alert. A catch-up session (not the latest) is past its deadline: FAILED as before. A step with
``[steps.<name>] settle_minutes`` WAITS without fetching until the close plus that long, and
every attempt for the latest session records when its source's data arrived (``arrival``).

``purge-raw`` ends the run whatever failed before; then ``notify.report`` writes the summary
file and sends the notifications. Each session gets a ``nightly`` run record (COMPLETE when
the session SUCCEEDED, else FAILED) holding every step's result, which is how the next run
knows where to resume.

What does not decide the session's COMPLETE record runs after it, in the ``post-session``
workflow (``workflows/post_session/``, ADR 0070): ``descriptions``, ``verify`` and ``edge-eval``
are not steps here, so the session is served (ADR 0062) as soon as the screens and the
``edge-signals`` and ``history-copy`` steps are done. ``edge-signals`` stays: ``edge_paper`` is
read as of ``knowledge_ts <= cutoff``. The duration alert (``nightly_duration``) measures this
run, the market-daily path, and never the post-session run.
"""

from collections.abc import Container, Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from algotrade.config.site.settings import NightlySettings, SourcesSettings, load_nightly
from algotrade.core.time.calendar import close_time, last_closed_session, local_deadline
from algotrade.data.reference import snapshot
from algotrade.services.jobs import JobContext
from algotrade.storage.runs import published
from algotrade_ingestion.tasks.analyst.backlog import check_analyst_backlog, check_finnhub_backlog
from algotrade_ingestion.tasks.derived.history_copy import check_history_copy
from algotrade_ingestion.tasks.derived.option_outcomes import check_option_outcomes
from algotrade_ingestion.tasks.derived.outcomes import check_outcomes
from algotrade_ingestion.tasks.derived.residual_returns import check_residual_returns
from algotrade_ingestion.tasks.framework.registry import TASKS, run_task, task
from algotrade_ingestion.tasks.framework.run import (
    RETRYABLE,
    IngestRun,
    TaskContext,
    resumable_run,
    retryable_items,
    utc_now,
)
from algotrade_ingestion.tasks.maintenance.coverage import check_coverage
from algotrade_ingestion.tasks.maintenance.quality import (
    check_analyst_snapshot,
    check_bars,
    check_bars_resolved,
    check_chains,
    check_earnings,
    check_filings,
    check_futures_curves,
    check_ibkr_vols,
    check_ipo_lockups,
    check_macro,
    check_macro_calendar,
    check_market_rollups,
    check_reference_classification,
    check_rollup_inputs,
    check_universe,
    check_vx_futures,
)
from algotrade_ingestion.workflows.nightly.attempts import Attempts, earlier_attempts
from algotrade_ingestion.workflows.nightly.notify import Notifier, default_notifier, report
from algotrade_ingestion.workflows.nightly.records import job_name
from algotrade_ingestion.workflows.nightly.screens import (
    ScreenStep,
    screen_jobs,
    signal_jobs,
    without_chains,
)
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
from algotrade_ingestion.workflows.nightly.timing import minutes_after_close

SCREENS = "screens"  # not an ingestion task: one `screen` job per screener
EDGE_SIGNALS = "edge-signals"  # not an ingestion task: one `edge-signals` job per user
JOB_STEPS = {  # the steps that submit jobs
    SCREENS: "screens",
    EDGE_SIGNALS: "signals",
}
PURGE = "purge-raw"
# Why a step runs only for the latest closed session (``Step.latest_only``): a catch-up
# session SKIPS it as "latest closed session only: <why>". A step that reads only stored
# data for the session (the rollups, the screens) runs for every session (2026-10-16: a
# catch-up skipped its screens and served a complete session without screener runs).
SNAPSHOT = "the source serves only its current snapshot"
LAST_MONTH = "it reads the last 30 filing days whatever the session, so one run covers all"
NEW_SINCE_STORED = "it reads every filing since the latest stored one, so one run covers all"
FORWARD_RECORD = "paper picks are made only on the night they are for (a later one is no record)"
WHOLE_FILES = "it reads every expiry's whole file, so the latest session's run covers this one"
WHOLE_YEAR = "it copies the whole year in one run, so the latest session's run covers this one"
MARKET_DATA = ("bars", "rates", "corporate-actions", "earnings", "chains")


def universe_exists(ctx: TaskContext, session: date) -> str | None:
    """Chains and screens need a universe snapshot for the session."""
    if snapshot(ctx.reader, "universe", session) is None:
        return f"no universe snapshot for {session}"
    return None


NIGHTLY: tuple[Step, ...] = (
    Step(
        "universe-build",
        latest_only=SNAPSHOT,
        accept=(check_universe, check_reference_classification),
        task_complete=True,
    ),
    # The futures curves (read-only IBKR, personal licence): the front contracts of each
    # configured root. EARLY in the order, right after the universe: its prices are only the
    # session's own until each contract's next session opens (18:00 New York at the earliest;
    # 16:30 New York is the earliest start of the day), so the heavy steps must not delay it.
    # Optional like ibkr-iv: SKIPPED with a WARN without the gateway, a root without data
    # permission is a WARN, never a FAIL; nothing reads it yet (history accrues), so no step
    # needs it.
    Step(
        "futures-curves",
        latest_only=SNAPSHOT,
        critical=False,
        accept=(check_futures_curves,),
    ),
    # Reference data (ADR 0039: moves to the weekly `reference` workflow in WF4): optional.
    Step("company-details", latest_only=SNAPSHOT, critical=False),
    Step("shares", latest_only=SNAPSHOT, critical=False),
    # The macro release calendar (ADR 0050): seven FRED requests, dates 400 days either side, so
    # it is a weekly-cadence fact kept current nightly until the `reference` workflow exists
    # (WF4: it moves there with the two steps above). Optional; FRED off or no key: SKIPPED.
    Step(
        "macro-calendar", latest_only=SNAPSHOT, critical=False, accept_with=(check_macro_calendar,)
    ),
    # SEC 8-Ks of the event-study names (ADR 0050): one request per CIK from its latest stored
    # filing, so a night reads the new ones; their Item 2.02 releases are earnings rows. Optional:
    # a failed night is read again the next (the default start is the latest stored filing).
    Step("filings", latest_only=NEW_SINCE_STORED, critical=False, accept_with=(check_filings,)),
    # SEC Form 4 insider transactions (EB D6): the days since the last clean walk from EDGAR's daily
    # index, each filing's XML; a night reads at most a few days, the next goes on. Optional: no
    # edge reads it until the history is backfilled (`algotrade-ingest insider --since`).
    Step("insider", latest_only=NEW_SINCE_STORED, critical=False),
    # IPO facts and lock-up expiry dates from EDGAR 424B4 prospectuses (ADR 0050, edge build D8):
    # the last 30 days' prospectuses, each read once. Optional and WARN-only: one edge reads it.
    Step("ipo-lockups", latest_only=LAST_MONTH, critical=False, accept_with=(check_ipo_lockups,)),
    # The Item sections of the 10-K / 10-Q of the CIKs due a report (edge build D10), each read from
    # its latest stored filing: optional and WARN-only (a PARTIAL run with nothing stored yet or a
    # full disk is a WARN, a failed night is read again); history accrues for track E.
    Step("filing-text", needs=("filings",), latest_only=NEW_SINCE_STORED, critical=False),
    Step("earnings", accept=(check_earnings,), task_complete=True),
    Step("bars", accept=(check_bars, check_bars_resolved)),
    Step("rates", task_complete=True),
    Step("corporate-actions", task_complete=True),
    # Cboe's VIX futures by expiry (EB D3): one static file per contract, the new rows after the
    # latest stored one. Optional, WARN-only acceptance: a Cboe outage never holds the screens
    # back. Cboe regenerates a file about 01:05 New York time the morning after, so a night
    # stores the sessions up to the one before and the next night the session itself.
    Step("vx-futures", latest_only=WHOLE_FILES, critical=False, accept_with=(check_vx_futures,)),
    # Flag the trailing 60 sessions' bars that cannot be right (ADR 0061), after the splits that
    # explain a real jump. Optional; the outcomes need it (a window over a bad bar is UNMEASURED).
    Step("bar-quality", needs=("bars", "corporate-actions"), critical=False),
    # Chains finish PARTIAL by design (NO_CHAIN and the like are items); the checks decide.
    # They need a universe snapshot, not today's build to succeed: chains can be fetched only
    # for the current session, and a failed build already fails the session and holds the
    # screens back (owner-delegated decision, 2026-10-05; amends ADR 0039's graph).
    Step(
        "chains",
        requires=universe_exists,
        latest_only=SNAPSHOT,
        accept=(check_chains,),
        resumable=True,
    ),
    # What each ETF holds (ADR 0035): issuer files, a weekly slot per fund, at most
    # [etf_holdings] per_night funds a night (new and stalest first). Optional.
    Step(
        "etf-holdings",
        needs=("universe-build",),
        requires=universe_exists,
        latest_only=SNAPSHOT,
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
        latest_only=SNAPSHOT,
        critical=False,
    ),
    Step(
        "ibkr-iv",
        needs=("ibkr-contracts",),
        requires=universe_exists,
        latest_only=SNAPSHOT,
        critical=False,
        accept=(check_ibkr_vols,),
    ),
    # Every session (catch-up too), after the market data it reads. A rollup that raises
    # (a gap in a lookback window included) fails the step.
    # Its acceptance is the coverage of the key features by tier (ADR 0043): a FAIL-level breach
    # (core-tier prices) fails the step and holds the screens back; the rest are warnings.
    # ibkr-iv does not gate it (optional), but when it succeeds in a later attempt the
    # rollups re-run (ibkr_iv@v1 for the session), and so do the steps that need them.
    # A group with no input for the session is a WARN, never a FAIL (ADR 0055): an optional
    # source's group (ibkr_iv@v1) is legitimately empty, but it must not pass unnoticed.
    Step(
        "rollups",
        needs=MARKET_DATA,
        reruns_after=("ibkr-iv",),
        accept=(check_coverage,),
        accept_stats=(check_rollup_inputs,),
        task_complete=True,
    ),
    # Economic series and index levels with their vintages (ADR 0048), before the market
    # rollups whose macro and regime groups read them. Latest session only (the sources serve
    # their current state); optional, and its run budget ([macro] run_budget_s) bounds a FRED
    # outage, so it never holds up the screens.
    Step("macro", critical=False, latest_only=SNAPSHOT, accept_with=(check_macro,)),
    # The market-entity rollups (ADR 0047: breadth, macro, the regime, one MKT:US row per group),
    # after the instrument rollups they read. Optional: a failure here never holds back the
    # screens. Not `needs=("macro",)`: a FAILED (or skipped, no FRED key) macro step would hold
    # the regime back (ADR 0039), while its groups read whatever macro/series holds, each value
    # point in time by vintage, and say UNKNOWN for what is missing. When macro succeeds in a
    # later attempt, they re-run on its series (``reruns_after``).
    Step(
        "market-rollups",
        needs=("rollups",),
        reruns_after=("macro",),
        critical=False,
        accept=(check_market_rollups,),
        accept_stats=(check_rollup_inputs,),
    ),
    # Forward outcomes of the windows the session closes (ADR 0053), read only by the edge
    # harness: bars and the splits that adjust them. Optional: never holds back the screens.
    Step(
        "outcomes",
        needs=("bars", "corporate-actions", "bar-quality"),
        critical=False,
        accept=(check_outcomes,),
    ),
    # Chain P&L of the option windows the session closes (ADR 0053 amendment, EB H13): the stored
    # chains of the window's sessions, read only by the edge harness. Optional, forward-only.
    Step(
        "option-outcomes",
        needs=("chains",),
        critical=False,
        accept=(check_option_outcomes,),
    ),
    # The factor-neutral sibling of the outcomes (ADR 0053 amendment, EB H11): the same windows
    # less the loadings of factor_betas@v1 (the rollups step) times the ETF factor returns.
    # Optional: a gap is UNMEASURED rows, a failure never holds back the screens.
    Step(
        "residual-returns",
        needs=("outcomes", "rollups"),
        critical=False,
        accept=(check_residual_returns,),
    ),
    # Every session, catch-up too: the screeners read only stored features, and a complete
    # session without screener runs would be served as one (ADR 0062). In a catch-up session the
    # chains were fetched by its own earlier attempt or not at all; without them the options
    # screeners fall short of coverage: a WARN when they never were (``without_chains``).
    Step(SCREENS, needs=("chains", "rollups"), requires=universe_exists),
    # The followed edges' paper picks for tonight and the open paper trades the stored outcomes
    # close (ADR 0053 amendment 2026-10-09): one job per user, after the screens (the picks read
    # the same features); a trade whose outcome is not stored yet stays open. Optional: a
    # failure warns, never holds the session.
    Step(EDGE_SIGNALS, needs=(SCREENS,), critical=False, latest_only=FORWARD_RECORD),
    # Our own point-in-time history of FMP / Finnhub analyst data (ADR 0068): a rotating slice of
    # names a night within [fmp] daily_budget, appended, never replaced. Optional: a vendor outage
    # or no key only warns. The vendors serve only today's value, so a catch-up session is SKIPPED.
    # After the screens and their jobs (it feeds no read of the session, and ~9 minutes of paced
    # calls must not delay them); [fmp] run_budget_s bounds a stalling vendor, so it cannot hold
    # the ingest lock. Publishes a table the history copies do not hold.
    Step(
        "analyst-snapshot",
        needs=("universe-build",),
        requires=universe_exists,
        latest_only=SNAPSHOT,
        critical=False,
        accept_with=(check_analyst_snapshot, check_analyst_backlog, check_finnhub_backlog),
    ),
    # FINRA short interest and daily short-sale volume (EB D9), both tables no_ml. Optional: an
    # outage only warns; each reads a window of dates not stored yet, so a catch-up session
    # repeats nothing, and a date FINRA has not published is NO_DATA and asked again.
    Step("short-interest", needs=("universe-build",), requires=universe_exists, critical=False),
    Step("short-volume", needs=("universe-build",), requires=universe_exists, critical=False),
    # `edge-eval`, `descriptions` and `verify` are the post-session workflow's (ADR 0070): they
    # do not feed the session's reads, so they no longer delay its COMPLETE record.
    # The derived history copies (ADR 0060), last: every step that publishes the copied tables
    # (bars, the rollups, the market rollups) has committed and the screens' jobs are done, so
    # ingestion commits no more until the post-session run (descriptions, verify). The API can
    # still commit (screener runs, ADR 0033; edge evaluations, ADR 0059): the build refuses
    # half-applied commits, and its fallback may hold the commit lock up to ~48 s. Latest
    # session only (a catch-up night would rebuild the same year per session). Optional: a
    # missed night leaves the old copy, which reads detect as stale and replace by the partitions.
    Step(
        "history-copy",
        needs=("bars", "rollups", "market-rollups"),
        latest_only=WHOLE_YEAR,
        critical=False,
        accept_stats=(check_history_copy,),
    ),
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
    step: Step,
    ctx: TaskContext,
    session: date,
    before: Attempts,
    waive: Mapping[str, str],
    latest: bool,
    reran: Container[str],
) -> StepResult | None:
    """Done before (an earlier attempt SUCCEEDED or WAIVED it) or waived now, else ``None``.
    A done step runs again when one of its inputs (what it needs, or reruns after) ran in
    this attempt (``reran``: its input changed) or when it is a refetch (``_refetch``)."""
    if step.name in before.done:
        stored = before.done[step.name]
        if any(n in reran for n in step.inputs) or _superseded(step, stored, ctx, session, before):
            return None
        left, resumable = _refetch(step, stored, ctx, session, latest)
        if left and resumable:
            return None
        why = _carried_reason(stored)
        if left:
            why += f"; {left} {'/'.join(RETRYABLE)} names left, no staging to resume from"
        return _carry(step, stored, why)
    if step.name in waive:
        who = f"waived by {ctx.user} at {ctx.clock().isoformat(timespec='seconds')}"
        return _held(step, StepStatus.WAIVED, f"{who}: {waive[step.name]}")
    return None


def _superseded(
    step: Step, stored: Mapping[str, Any], ctx: TaskContext, session: date, before: Attempts
) -> bool:
    """Whether the step's own job published a run since its stored result that no attempt
    cites: COMPLETE or PARTIAL, started after the stored ``task_run`` (after the carried
    attempt for a result without one). A forced attempt killed after its task finished, or a
    standalone ``run <task>``, leaves rows its dependents never saw; a FAILED or RUNNING run
    published nothing and does not count. Own job only; one ``runs`` read per carried step."""
    job = job_name(step.name)
    if job is None:
        return False
    anchor = ctx.reader.run(str(stored.get("task_run") or stored["run_id"]))
    if anchor is None:
        return False
    return any(
        published(r) and r.started_at > anchor.started_at and r.run_id not in before.cited
        for r in ctx.reader.runs(job, session)
    )


def _carried_reason(stored: Mapping[str, Any]) -> str:
    return f"{str(stored['status']).lower()} in an earlier attempt ({stored['run_id']})"


def _carry(step: Step, stored: Mapping[str, Any], why: str) -> StepResult:
    """The stored result reused, citing the attempt that produced it."""
    result = _held(step, StepStatus(str(stored["status"])), why)
    result.origin = str(stored["run_id"])
    result.task_run = stored.get("task_run")
    return result


def _refetch(
    step: Step, stored: Mapping[str, Any], ctx: TaskContext, session: date, latest: bool
) -> tuple[int, bool]:
    """(items a resumed re-run of the task would refetch, whether it can): a resumable step
    that SUCCEEDED with retryable items left is re-run by a retry while the session is the
    latest (the source still serves it) and the run its task would resume exists with its
    staging (``resumable_run``, the same rule the task applies; without the staging the task
    would refetch everything: hours, every hour). A stored result without its ``task_run`` (a
    record from older code) falls back to the run the task would resume: the step's task job
    (its registry ``TASK`` name, not necessarily the step's), ``resumable_run``."""
    if not step.resumable or stored.get("status") != StepStatus.SUCCEEDED.value:
        return 0, False
    task_run = stored.get("task_run")
    if task_run:
        record = ctx.writer.load_run(str(task_run))
    else:
        job = job_name(step.name)
        record = resumable_run(ctx.writer, job, session) if job else None
    if record is None:
        return 0, False
    left = len(retryable_items(record))
    if not left or not latest:
        return left, False
    return left, resumable_run(ctx.writer, record.job, session) is not None


def _refetch_failed(step: Step, stored: Mapping[str, Any], result: StepResult) -> StepResult:
    """A refetch that did not succeed keeps the earlier success (its rows are published and
    still stand), noting why; the next attempt may refetch again."""
    why = f"{_carried_reason(stored)}; refetch failed: {result.error or result.reason}"
    return _carry(step, stored, why)


def _not_latest(step: Step, before: Attempts, session: date) -> StepResult:
    """A latest-only step for an older session: SKIPPED, or FAILED as expired when an
    earlier attempt tried it without success (it can no longer be fetched)."""
    if step.critical and step.name in before.tried:
        why = (
            "expired: the source serves only the current snapshot and this session is no "
            "longer the latest; only the owner can accept the gap, from their own terminal: "
            "`algotrade-ingest nightly --date "
            f"{session.isoformat()} --waive {step.name} --reason ...`"
        )
        return _held(step, StepStatus.FAILED, why)
    return _held(step, StepStatus.SKIPPED, f"latest closed session only: {step.latest_only}")


def _not_run(
    step: Step,
    ctx: TaskContext,
    session: date,
    latest: bool,
    done: Mapping[str, StepResult],
    before: Attempts,
    waive: Mapping[str, str],
    reran: Container[str] = (),
) -> StepResult | None:
    """The step's result when it must not run (reused, waived, skipped, expired, held
    back), else ``None``."""
    carried = _carried(step, ctx, session, before, waive, latest, reran)
    if carried is not None:
        return carried
    if step.latest_only and not latest:
        return _not_latest(step, before, session)
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


def settle_until(step: Step, session: date, settings: NightlySettings) -> datetime | None:
    """The instant before which ``step`` does not fetch (close + ``[steps.<name>]
    settle_minutes``), ``None`` when it has no settle time."""
    minutes = settings.settle_for(step.name)
    return close_time(session) + timedelta(minutes=minutes) if minutes else None


def run_step(
    step: Step,
    ctx: TaskContext,
    session: date,
    params: Mapping[str, Any],
    screens: ScreenStep | None,
    wait: bool = False,
    settle_until: datetime | None = None,
    observe: bool = False,
    signal_step: ScreenStep | None = None,
) -> StepResult:
    """One step, isolated: its precondition, the registry task (or the screen jobs), then
    its acceptance checks (``wait``: a pending failure is WAITING, not FAILED;
    ``settle_until``: WAITING without fetching before then; ``observe``: the latest session,
    so the attempt records when the data arrived)."""
    started = ctx.clock()

    def body() -> Outcome:
        if settle_until is not None and started < settle_until:
            return Outcome(StepStatus.WAITING, reason=f"settling until {settle_until:%H:%M} UTC")
        if step.requires is not None and (why := step.requires(ctx, session)):
            return Outcome(StepStatus.NOT_RUN, reason=why)
        if step.name in JOB_STEPS:
            job = {SCREENS: screens, EDGE_SIGNALS: signal_step}[step.name]
            if job is None:
                return Outcome(
                    StepStatus.SKIPPED, reason=f"no job runner to submit {JOB_STEPS[step.name]} to"
                )
            return job(session)
        # ``probe``: a task that can sample its source first (chains) may WAIT as soon as the
        # data is clearly not published; once the deadline has passed it fetches in full
        record = run_task(
            step.name, ctx, {**params, **step.params, "session": session, "probe": wait}
        )
        return from_record(record, step, ctx, session, wait)

    result = run_isolated(step.name, body, ctx.clock, step.critical)
    if observe and result.observed is not None:
        minutes = minutes_after_close(started, close_time(session))
        result.arrival = {"minutes_after_close": minutes, **result.observed}
    return result


def run_session(
    ctx: TaskContext,
    session: date,
    latest: bool,
    screens: ScreenStep | None = None,
    workers: int | None = None,
    resume: bool = True,
    waive: Mapping[str, str] | None = None,
    settings: NightlySettings | None = None,
    signal_step: ScreenStep | None = None,
) -> dict[str, Any]:
    """Every ``NIGHTLY`` step for one session; saves the session's ``nightly`` run record.
    ``resume``: reuse the steps an earlier attempt of the session did; ``waive``: step ->
    reason, accepted by hand; ``settings``: the deadlines a step may wait until."""
    settings = settings or NightlySettings()
    before = earlier_attempts(ctx.reader, session) if resume else Attempts()
    done: dict[str, StepResult] = {}
    reran: set[str] = set()  # steps this attempt ran to success: their dependents re-run
    with IngestRun(ctx, NIGHTLY_RUN, session) as run:
        for step in NIGHTLY:
            held = _not_run(step, ctx, session, latest, done, before, waive or {}, reran)
            if held is None:
                # decided before the run: this attempt's own task run must not count
                stale = step.name in before.done and _superseded(
                    step, before.done[step.name], ctx, session, before
                )
                wait = waits(step, ctx, session, latest, settings)
                result = run_step(
                    step,
                    ctx,
                    session,
                    {"workers": workers},
                    screens,
                    wait,
                    settle_until(step, session, settings) if wait else None,
                    latest,
                    signal_step,
                )
                if step.name == SCREENS:
                    unfetched = not latest and done["chains"].status is StepStatus.SKIPPED
                    result = without_chains(result, unfetched)
                # a done step that ran although none of its inputs did is a refetch
                refetch = (
                    step.name in before.done
                    and not any(n in reran for n in step.inputs)
                    and not stale
                )
                if refetch and result.status in BAD:
                    result = _refetch_failed(step, before.done[step.name], result)
                elif result.status is StepStatus.SUCCEEDED:  # new data for what needs it
                    reran.add(step.name)
                held = result
            done[step.name] = held
            run.record_item(step.name, step_item(held))
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


def step_item(result: StepResult) -> str:
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
    signal_step: ScreenStep | None = None,
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
                ctx,
                session,
                session == plan.latest,
                screens,
                workers,
                resume,
                waive,
                settings,
                signal_step,
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


def job_task_context(ctx: JobContext) -> TaskContext:
    """The task context of a workflow job from its resources (the nightly's and the
    post-session's handlers share it)."""
    r = ctx.resources
    return TaskContext(
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
    task_ctx = job_task_context(ctx)
    settings = load_nightly(r["configs"])
    session = date.fromisoformat(params["session"])
    until = last_closed_session(task_ctx.clock(), timedelta(minutes=settings.settle_minutes))
    if params.get("catch_up"):
        plan = plan_sessions(last_done(task_ctx.writer), session, settings.max_catch_up)
    else:  # `--date`: latest-only steps run only when it is the last closed session
        plan = Plan([session], until=max(until, session))
    export_dir = Path(params["export_dir"]) if params.get("export_dir") else None
    screens = screen_jobs(ctx.jobs, r["configs"], export_dir) if ctx.jobs else None
    signals = signal_jobs(ctx.jobs, r["configs"], task_ctx.reader) if ctx.jobs else None
    workers = int(params["workers"]) if params.get("workers") else None
    resume = bool(params.get("resume", True))
    waive = dict(params.get("waive") or {})
    summary = run_nightly(task_ctx, plan, settings, screens, workers, resume, waive, signals)
    notifier: Notifier = r.get("notifier") or default_notifier(settings)
    summary = report(summary, settings, notifier, task_ctx.reader)
    return {**summary, "_partial": summary["status"] != Status.SUCCEEDED}
