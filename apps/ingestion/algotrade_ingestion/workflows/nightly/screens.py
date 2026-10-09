"""The nightly ``screens`` step: one ``screen`` job per screener (ADR 0033).

Screens run through the job runner (``services/jobs``), never inline (ADR 0019, R5): each
screener (every site preset as ``site``, then each user's finalised ones) becomes a ``screen``
job for its owner; exports are that job's output. The step SUCCEEDS when every job is
COMPLETE (each screener reached its coverage threshold, ADR 0039), else it FAILS naming the
screeners that did not. A screener that ran without a table none of its fields
needed (``missing_optional_tables``: an optional source's, e.g. ``ibkr_iv@v1`` with IB Gateway
down, or a required one whose coalesce fallback is present, e.g. ``iv30@v1`` before it was
stored) is a WARN check on the step, never its failure (ADR 0055, coverage of coalescing
expressions).
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.services.configs import nightly_screeners
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
