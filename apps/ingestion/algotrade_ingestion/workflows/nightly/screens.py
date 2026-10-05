"""The nightly ``screens`` step: one ``screen`` job per screener (ADR 0033).

Screens run through the job runner (``services/jobs``), never inline (ADR 0019, R5): each
screener (every site preset as ``site``, then each user's finalised ones) becomes a ``screen``
job for its owner; exports are that job's output. The step is COMPLETE when every job is,
FAILED when every job failed, else PARTIAL.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from algotrade.services.configs import nightly_screeners
from algotrade.services.jobs import JobRecord, JobRunner
from algotrade.storage.configs.store import ConfigStore
from algotrade_ingestion.workflows.nightly.steps import Outcome, StepStatus, step_status

type ScreenStep = Callable[[date], Outcome]


def _summary(config_id: str, job: JobRecord) -> dict[str, Any]:
    out: dict[str, Any] = {"job_id": job.job_id, "config": config_id, "status": job.status.value}
    if job.error:
        out["error"] = job.error
    return {**out, **job.result}


def screen_jobs(jobs: JobRunner, configs: ConfigStore, export_dir: Path | None) -> ScreenStep:
    """The screens step, submitting through ``jobs`` (run in the nightly's own thread)."""

    def run(session: date) -> Outcome:
        summaries, statuses = [], []
        for config in nightly_screeners(configs):
            params = {
                "config": config.config.id,
                "session": session.isoformat(),
                "export_dir": str(export_dir) if export_dir else None,
            }
            job = jobs.run("screen", params, config.user, force=True)
            summaries.append(_summary(config.config.id, job))
            statuses.append(step_status(job.status))
        if statuses and all(s is StepStatus.FAILED for s in statuses):
            status = StepStatus.FAILED
        elif all(s is StepStatus.COMPLETE for s in statuses):
            status = StepStatus.COMPLETE
        else:
            status = StepStatus.PARTIAL
        return Outcome(status, {"screens": summaries})

    return run
