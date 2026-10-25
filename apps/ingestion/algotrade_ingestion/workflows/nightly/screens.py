"""The nightly's job steps: ``screens`` (one ``screen`` job per screener, ADR 0033) and
``edge-signals`` (one job per record owner: ``site`` and each user with an edge recording or
open paper trades, ADR 0053 amendment 2026-10-10).

Screens run through the job runner (``services/jobs``), never inline (ADR 0019, R5): each
screener (every site preset as ``site``, then each user's finalised ones) becomes a ``screen``
job for its owner; exports are that job's output. The step SUCCEEDS when every job is
COMPLETE (each screener reached its coverage threshold, ADR 0039), else it FAILS naming the
screeners that did not. A screener that ran without a table none of its fields
needed (``missing_optional_tables``: an optional source's, e.g. ``ibkr_iv@v1`` with IB Gateway
down, or a required one whose coalesce fallback is present, e.g. ``iv30@v1`` before it was
stored) is a WARN check on the step, never its failure (ADR 0055, coverage of coalescing
expressions). In a catch-up session whose chains were never fetched, a screener short of coverage
only is a WARN too (``without_chains``, ADR 0039 amendment 2026-10-16), as is one short only for
want of a table whose backfill is declared under way (``while_backfilling``, ADR 0055
amendment 2026-10-20).

The ``edge-signals`` step (``signal_jobs``) mirrors it: each job makes the owner's tonight picks of
its open edges (``loading.records_paper``; a follower's bookmark trades nothing) and settles the
open paper trades whose outcome is stored
(``services/evaluation/forward``). When an edge the owner records is below its usual range (the
read model's live state, ADR 0064 decision 9) the step adds one WARN line naming it and keeps the
names in its result: nothing is pushed or sent. It needs ``screens`` (settlement leaves a trade
open when its outcome is not stored) and is not critical: a failed job is a warning naming the
user, never a hold on the session or a later one.

The ``edge-eval`` step (``edge_eval_jobs``) is the ``post-session`` workflow's (ADR 0070), not the
nightly's: it runs one ``edge-eval`` job per open edge (not rejected or blocked, with screeners or
baselines) as the edge's owner over the stored outcome sessions (ADR 0063), under the owner's
evaluation claim (each summary carries ``mode``, the one requested, and ``effective_mode``, the
one the harness ran, so a FULL fallback shows): ``mode="incremental"`` (reuse the stored legs), or
``mode="audit"`` (recompute every leg, compare, rewrite the ones that differ, FAIL naming them)
when ``audit_due`` (the week's last session, or the edge's last audit is over 9 days old). A job
that is not COMPLETE fails the step, a warning naming the edge, never a hold on anything.
"""

import logging
from collections.abc import Callable, Collection, Mapping
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from algotrade.config.edges.document import CLOSED, Edge
from algotrade.config.edges.loading import load_all_edges
from algotrade.config.site.nightly import Backfilling
from algotrade.config.user import UserContext
from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.time.calendar import last_session_of_week
from algotrade.data import StoreReader
from algotrade.features.registry import GROUPS
from algotrade.services.configs import nightly_screeners
from algotrade.services.evaluation.cross_section.harness import stored_outcome_sessions
from algotrade.services.evaluation.forward.results import paper_owners
from algotrade.services.jobs import JobRecord, JobRunner, JobStatus
from algotrade.services.jobs.exclusive import EDGE_EVAL, EdgeEvalBusyError, claim_edge_eval
from algotrade.services.read.context import open_context
from algotrade.services.read.edge_desk.states import below_range
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.interfaces import Backend
from algotrade_ingestion.workflows.nightly.steps import Outcome, StepResult, StepStatus

LOG = logging.getLogger(__name__)

type ScreenStep = Callable[[date], Outcome]


def _summary(config_id: str, job: JobRecord) -> dict[str, Any]:
    out: dict[str, Any] = {"job_id": job.job_id, "config": config_id, "status": job.status.value}
    if job.error:
        out["error"] = job.error
    return {**out, **job.result}


def _optional_warnings(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One WARN check per screener that went without a table no field needed."""
    return [
        {
            "name": "optional_sources",
            "status": "WARN",
            "detail": f"{s['config']} ran without {', '.join(missing)}",
        }
        for s in summaries
        if (missing := s.get("missing_optional_tables"))
    ]


def screen_jobs(jobs: JobRunner, configs: ConfigStore, export_dir: Path | None) -> ScreenStep:
    """The screens step, submitting through ``jobs`` (run in the nightly's own thread)."""

    def run(session: date) -> Outcome:
        summaries, short = [], []
        for config in nightly_screeners(configs):
            params = {
                "config": config.config.id,
                "session": session.isoformat(),
                "export_dir": str(export_dir) if export_dir else None,
            }
            job = jobs.run("screen", params, config.user, force=True)
            summaries.append(_summary(config.config.id, job))
            if job.status is not JobStatus.COMPLETE:
                short.append(f"{config.config.id} {job.status.value}")
        result = {"screens": summaries}
        warnings = _optional_warnings(summaries)
        if short:
            reason = f"screeners not complete: {', '.join(short)}"
            return Outcome(StepStatus.FAILED, result, reason, warnings)
        return Outcome(StepStatus.SUCCEEDED, result, None, warnings)

    return run


def chain_tables() -> frozenset[str]:
    """The rollup tables computed from the option chains, directly or through another such
    table (the groups in dependency order, so a group's inputs come first)."""
    found: set[str] = set()
    for group in GROUPS.values():
        if any(i.table.startswith("chains/") or i.table in found for i in group.inputs):
            found.add(group.table)
    return frozenset(found)


def _short(result: StepResult) -> list[Mapping[str, Any]]:
    complete = JobStatus.COMPLETE.value
    return [s for s in (result.result or {}).get("screens", []) if s["status"] != complete]


def _excused(
    result: StepResult, tables: Collection[str], check: str, why: Callable[[Mapping[str, Any]], str]
) -> StepResult:
    """``result`` with its FAILED step SUCCEEDED when every screener short of coverage is a
    PARTIAL job (its run stored) whose missing tables are a non-empty subset of ``tables``;
    each is one WARN ``check``. Anything else short (a FAILED job, another missing table, a
    shortfall with no missing table) leaves the step failed."""
    short = _short(result)
    if not short:
        return result
    partial = JobStatus.PARTIAL.value
    for s in short:
        missing = s.get("missing_tables") or []
        if s["status"] != partial or not missing or not set(missing) <= set(tables):
            return result
    warnings = [{"name": check, "status": "WARN", "detail": why(s)} for s in short]
    return replace(
        result, status=StepStatus.SUCCEEDED, reason=None, checks=[*result.checks, *warnings]
    )


def without_chains(result: StepResult, unfetched: bool) -> StepResult:
    """The screens of a catch-up session whose chains were never fetched (``unfetched``: SKIPPED,
    the source no longer serves the session; ADR 0039 amendment 2026-10-16). A screener short of
    coverage only for want of chain-derived tables (a PARTIAL job, its run stored, every missing
    table one of ``chain_tables``) is one WARN, never a hold on the session or the later ones,
    whose snapshots would be lost. Anything else short (a FAILED job, another missing table, a
    shortfall with no missing table) still fails the step."""
    if result.status is not StepStatus.FAILED or not unfetched:
        return result
    return _excused(
        result,
        chain_tables(),
        "no_chains",
        lambda s: (
            f"{s['config']} short of coverage: no chains stored for this session "
            f"({', '.join(s['missing_tables'])})"
        ),
    )


def while_backfilling(
    result: StepResult, backfills: Mapping[str, Backfilling], today: date
) -> StepResult:
    """The screens whose shortfall is a declared backfill (``[backfilling]`` in nightly.toml,
    ADR 0055 amendment 2026-10-20): a screener PARTIAL only for want of tables whose ``until`` is
    not before ``today`` (the wall-clock date: a forgotten entry lapses) is one WARN
    ``backfilling`` naming the reason; the run
    stays stored PARTIAL. A FAILED job, another missing table or an expired entry still fails."""
    if result.status is not StepStatus.FAILED:
        return result
    live = {t for t, b in backfills.items() if b.until >= today}
    return _excused(
        result,
        live,
        "backfilling",
        lambda s: (
            f"{s['config']} short of coverage: backfill under way "
            + "; ".join(
                f"{t} until {backfills[t].until} ({backfills[t].reason})"
                for t in s["missing_tables"]
            )
        ),
    )


def _below_range(
    reader: StoreReader, configs: ConfigStore, owner: UserContext, session: date
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """The edges ``owner`` records that are below their usual range on ``session`` (the read
    model's live state) and the WARN checks of a state that could not be read: logged and
    recorded on the run record, never swallowed and never a reason to fail the step."""
    try:
        found = below_range(open_context(reader, configs, owner, session), datetime.now(UTC))
    except AlgoTradeError as error:
        LOG.warning("live state of %s on %s not read: %s", owner.user_id, session, error)
        detail = f"live state of {owner.user_id} not read: {error}"
        return [], [{"name": "edge_live_state", "status": "WARN", "detail": detail}]
    return [{"user": owner.user_id, "edge": s.edge_id, "headline": s.headline} for s in found], []


def signal_jobs(jobs: JobRunner, configs: ConfigStore, reader: StoreReader) -> ScreenStep:
    """The edge-signals step (a job per record owner), submitting through ``jobs``."""

    def run(session: date) -> Outcome:
        summaries, short, below, warnings = [], [], [], []
        for user in paper_owners(reader, configs, session):
            job = jobs.run("edge-signals", {"session": session.isoformat()}, user, force=True)
            summaries.append(
                {"user": user.user_id, "job_id": job.job_id, "status": job.status.value}
                | ({"error": job.error} if job.error else {})
                | dict(job.result)
            )
            if job.status is not JobStatus.COMPLETE:
                short.append(f"{user.user_id} {job.status.value}")
            elif reader is not None:
                lines, failed = _below_range(reader, configs, user, session)
                below += lines
                warnings += failed
        result: dict[str, Any] = {"signals": summaries}
        if below:
            result["below_range"] = below
            named = ", ".join(sorted({b["edge"] for b in below}))
            detail = f"below the usual range: {named}"
            warnings.append({"name": "edge_below_range", "status": "WARN", "detail": detail})
        if short:
            reason = f"edge signals not complete: {', '.join(short)}"
            return Outcome(StepStatus.FAILED, result, reason, warnings)
        return Outcome(StepStatus.SUCCEEDED, result, None, warnings)

    return run


AUDIT_MAX_AGE = timedelta(days=9)  # an edge never goes longer than this without an audit


def audit_due(backend: Backend | None, edge: Edge, session: date) -> bool:
    """The edge's weekly audit is due (ADR 0063 amendment 6, moved by ADR 0070): on the last
    session of the ISO week of ``session``, or when its last audit is more than 9 days older than
    ``session`` (none on record: due), session to session: the audit's own session is the
    ``session`` param of its completed ``edge-eval`` job whose effective mode was audit (a job
    from before the param counts as none). Every other run is incremental."""
    if session == last_session_of_week(session):
        return True
    if backend is None:
        return True
    audits = [
        date.fromisoformat(job.params["session"])
        for job in map(JobRecord.from_run, backend.runs.find(f"job:{EDGE_EVAL}"))
        if job.params.get("edge") == edge.id
        and job.user == edge.owner
        and job.status is JobStatus.COMPLETE
        and job.result.get("mode") == "audit"
        and job.params.get("session")
    ]
    return not audits or session - max(audits) > AUDIT_MAX_AGE


def edge_eval_jobs(
    jobs: JobRunner, configs: ConfigStore, reader: StoreReader, backend: Backend | None = None
) -> ScreenStep:
    """The edge-eval step (a job per open edge, as its owner), submitting through ``jobs`` under
    the owner's evaluation claim when ``backend`` is given (an API run of theirs in flight makes
    the edge ``busy``: a warning, the job not submitted)."""

    def run(session: date) -> Outcome:
        edges = [
            e
            for e in load_all_edges(configs)
            if e.status not in CLOSED and (e.screeners or e.baselines)
        ]
        stored = stored_outcome_sessions(reader)
        if not edges or not stored:
            reason = "no open edge to evaluate" if not edges else "no outcomes stored"
            return Outcome(StepStatus.SKIPPED, {"evaluations": []}, reason)
        summaries, short, warnings = [], [], []
        for edge in edges:
            mode = "audit" if audit_due(backend, edge, session) else "incremental"
            params = {
                "edge": edge.id,
                "start": stored[0].isoformat(),
                "end": stored[-1].isoformat(),
                "mode": mode,
                "session": session.isoformat(),  # the audit rule counts sessions
                "trigger": "nightly",
            }
            summary: dict[str, Any] = {"edge": edge.id, "owner": edge.owner, "mode": mode}
            try:
                with claim_edge_eval(backend, edge.owner) if backend else nullcontext():
                    job = jobs.run("edge-eval", params, UserContext(edge.owner), force=True)
            except EdgeEvalBusyError as busy:
                summaries.append({**summary, "status": "busy", "error": str(busy)})
                warnings.append(
                    {"name": "edge_eval_busy", "status": "WARN", "detail": f"{edge.id}: {busy}"}
                )
                continue
            summaries.append(
                {**summary, "job_id": job.job_id, "status": job.status.value}
                | ({"error": job.error} if job.error else {})
                | {k: job.result[k] for k in ("run_id", "legs") if k in job.result}
                | ({"effective_mode": job.result["mode"]} if "mode" in job.result else {})
            )
            if job.status is not JobStatus.COMPLETE:
                short.append(f"{edge.owner}/{edge.id} {job.status.value}")
        result = {"evaluations": summaries}
        if short:
            reason = f"edge evaluations not complete: {', '.join(short)}"
            return Outcome(StepStatus.FAILED, result, reason, warnings)
        return Outcome(StepStatus.SUCCEEDED, result, None, warnings)

    return run
