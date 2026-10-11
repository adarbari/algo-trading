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
expressions).

The ``edge-signals`` step (``signal_jobs``) mirrors it: each job makes the owner's tonight picks of
its evidenced or live edges (a follower's bookmark trades nothing) and settles the open paper
trades whose outcome is stored
(``services/evaluation/forward``). When an edge the owner records is below its usual range (the
read model's live state, ADR 0064 decision 9) the step adds one WARN line naming it and keeps the
names in its result: nothing is pushed or sent. It needs ``screens`` (settlement leaves a trade
open when its outcome is not stored) and is not critical: a failed job is a warning naming the
user, never a hold on the session or a later one.

The ``edge-eval`` step (``edge_eval_jobs``) runs one ``edge-eval`` job per open edge (not
rejected or blocked, with screeners or baselines) as the edge's owner over the stored outcome
sessions (ADR 0063), under the owner's evaluation claim: ``mode="incremental"`` (reuse the stored
legs), or ``mode="audit"`` (recompute every leg, compare, rewrite the ones that differ, FAIL
naming them) on the first night of the ISO week that runs the step (the edge has no audit run
that week yet). It needs ``outcomes`` and ``screens`` and is not critical: a job that is not
COMPLETE fails the step, a warning naming the edge, never a hold on the session or a later one.
"""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.config.edges.document import CLOSED, Edge, job_name
from algotrade.config.edges.loading import load_all_edges
from algotrade.config.user import UserContext
from algotrade.core.model.errors import AlgoTradeError
from algotrade.data import StoreReader
from algotrade.services.configs import nightly_screeners
from algotrade.services.evaluation.cross_section.harness import stored_outcome_sessions
from algotrade.services.evaluation.forward.results import paper_owners
from algotrade.services.jobs import JobRecord, JobRunner, JobStatus
from algotrade.services.jobs.exclusive import EdgeEvalBusyError, claim_edge_eval
from algotrade.services.read.context import open_context
from algotrade.services.read.edge_desk.states import below_range
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.interfaces import Backend
from algotrade_ingestion.workflows.nightly.steps import Outcome, StepStatus

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


def _below_range(
    reader: StoreReader, configs: ConfigStore, owner: UserContext, session: date
) -> list[dict[str, str]]:
    """The edges ``owner`` records that are below their usual range on ``session``, by the read
    model's live state (empty when the session cannot be read: the line is a courtesy, never a
    reason to fail the step)."""
    try:
        found = below_range(open_context(reader, configs, owner, session))
    except AlgoTradeError:
        return []
    return [{"user": owner.user_id, "edge": s.edge_id, "headline": s.headline} for s in found]


def signal_jobs(jobs: JobRunner, configs: ConfigStore, reader: StoreReader) -> ScreenStep:
    """The edge-signals step (a job per record owner), submitting through ``jobs``."""

    def run(session: date) -> Outcome:
        summaries, short, below = [], [], []
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
                below += _below_range(reader, configs, user, session)
        result: dict[str, Any] = {"signals": summaries}
        warnings = []
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


def audited_this_week(backend: Backend | None, edge: Edge, session: date) -> bool:
    """The edge already has an audit run in the ISO week of ``session`` (ADR 0063 amendment 6):
    the audit is due on the week's first night that runs the step, not on a fixed weekday, so a
    catch-up night that skipped the Monday still audits on the Tuesday."""
    if backend is None:
        return False
    week = session.isocalendar()[:2]
    return any(
        r.stats.get("mode") == "audit" and r.started_at.isocalendar()[:2] == week
        for r in backend.runs.find(job_name(edge.id, edge.owner))
    )


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
            mode = "incremental" if audited_this_week(backend, edge, session) else "audit"
            params = {
                "edge": edge.id,
                "start": stored[0].isoformat(),
                "end": stored[-1].isoformat(),
                "mode": mode,
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
            )
            if job.status is not JobStatus.COMPLETE:
                short.append(f"{edge.owner}/{edge.id} {job.status.value}")
        result = {"evaluations": summaries}
        if short:
            reason = f"edge evaluations not complete: {', '.join(short)}"
            return Outcome(StepStatus.FAILED, result, reason, warnings)
        return Outcome(StepStatus.SUCCEEDED, result, None, warnings)

    return run
