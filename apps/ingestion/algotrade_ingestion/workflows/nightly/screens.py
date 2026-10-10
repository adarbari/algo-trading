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
(``services/evaluation/forward``). It needs ``screens`` (settlement leaves a trade open when its
outcome is not stored) and is not critical: a failed job is a warning naming the user, never a
hold on the session or a later one.

The ``edge-eval`` step (``edge_eval_jobs``) runs one ``edge-eval`` job per open edge (not rejected
or blocked, with screeners or baselines) as the edge's owner over the stored outcome sessions
(ADR 0063): ``mode="incremental"`` (reuse the stored legs) on a session, ``mode="audit"``
(recompute every leg, compare, rewrite the ones that differ, FAIL naming them) on the first
session of its ISO week. It needs ``outcomes`` and ``screens`` and is not critical: a job that is
not COMPLETE fails the step, a warning naming the edge, never a hold on the session or a later one.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.config.edges.document import CLOSED
from algotrade.config.edges.loading import load_all_edges
from algotrade.config.user import UserContext
from algotrade.core.time.calendar import previous_session
from algotrade.data import StoreReader
from algotrade.services.configs import nightly_screeners
from algotrade.services.evaluation.cross_section.harness import stored_outcome_sessions
from algotrade.services.evaluation.forward.results import paper_owners
from algotrade.services.jobs import JobRecord, JobRunner, JobStatus
from algotrade.storage.configs.store import ConfigStore
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


def signal_jobs(jobs: JobRunner, configs: ConfigStore, reader: StoreReader) -> ScreenStep:
    """The edge-signals step (a job per record owner), submitting through ``jobs``."""

    def run(session: date) -> Outcome:
        summaries, short = [], []
        for user in paper_owners(reader, configs, session):
            job = jobs.run("edge-signals", {"session": session.isoformat()}, user, force=True)
            summaries.append(
                {"user": user.user_id, "job_id": job.job_id, "status": job.status.value}
                | ({"error": job.error} if job.error else {})
                | dict(job.result)
            )
            if job.status is not JobStatus.COMPLETE:
                short.append(f"{user.user_id} {job.status.value}")
        result = {"signals": summaries}
        if short:
            return Outcome(
                StepStatus.FAILED, result, f"edge signals not complete: {', '.join(short)}"
            )
        return Outcome(StepStatus.SUCCEEDED, result, None)

    return run


def audit_session(session: date) -> bool:
    """The first session of its ISO week by the trading calendar: the night of the weekly audit
    (ADR 0063 amendment 6; no weekly workflow exists to hold it)."""
    return previous_session(session).isocalendar()[:2] != session.isocalendar()[:2]


def edge_eval_jobs(jobs: JobRunner, configs: ConfigStore, reader: StoreReader) -> ScreenStep:
    """The edge-eval step (a job per open edge, as its owner), submitting through ``jobs``."""

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
        mode = "audit" if audit_session(session) else "incremental"
        summaries, short = [], []
        for edge in edges:
            params = {
                "edge": edge.id,
                "start": stored[0].isoformat(),
                "end": stored[-1].isoformat(),
                "mode": mode,
                "trigger": "nightly",
            }
            job = jobs.run("edge-eval", params, UserContext(edge.owner), force=True)
            summaries.append(
                {"edge": edge.id, "owner": edge.owner, "mode": mode, "job_id": job.job_id}
                | {"status": job.status.value}
                | ({"error": job.error} if job.error else {})
                | {
                    k: job.result[k]
                    for k in ("run_id", "legs_reused", "legs_computed")
                    if k in job.result
                }
            )
            if job.status is not JobStatus.COMPLETE:
                short.append(f"{edge.owner}/{edge.id} {job.status.value}")
        result = {"evaluations": summaries, "mode": mode}
        if short:
            return Outcome(
                StepStatus.FAILED, result, f"edge evaluations not complete: {', '.join(short)}"
            )
        return Outcome(StepStatus.SUCCEEDED, result, None)

    return run
