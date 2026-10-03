"""The nightly workflow: an ordered list of registry tasks, then screens and the raw purge.

Each task runs through ``tasks/registry.py`` with the same defaults as its CLI command. A
task is skipped (and reported as such) when a source it needs is not configured or its
``skip`` rule says so (e.g. the universe in CSV-import mode). Exchange calendar, locks and
per-task isolation come with ``workflows/`` (roadmap R5).
"""

from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from algotrade.services.configs import scheduled
from algotrade.services.exports import run_exports
from algotrade.services.jobs import JobContext
from algotrade.services.screening import run_screener
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.settings import SourcesSettings
from algotrade_ingestion.tasks.framework import TaskContext
from algotrade_ingestion.tasks.registry import run_task, task

SCREENS = "screens"  # not an ingestion task: scheduled screeners + exports (services)
NIGHTLY = (
    "universe-build",
    "company-details",
    "earnings",
    "bars",
    "corporate-actions",
    "chains",
    "features",
    SCREENS,
    "quality",
)


def skip_reason(name: str, ctx: TaskContext) -> str | None:
    spec = task(name)
    missing = [s for s in spec.sources if s not in ctx.sources]
    if missing:
        reasons = sorted({ctx.unavailable.get(s, f"{s} is not configured") for s in missing})
        return f"skipped: {'; '.join(reasons)}"
    return spec.skip(ctx) if spec.skip else None


def _screens(ctx: TaskContext, session: date, export_dir: Path | None) -> dict[str, Any]:
    assert ctx.configs is not None
    audits: list[dict[str, Any]] = []
    exports: list[str] = []
    for config in scheduled(ctx.configs, "nightly"):
        if config.config.kind != "screener":
            continue
        outcome = run_screener(ctx.reader, ctx.writer, config, session)
        audits.append(outcome.audit)
        if export_dir is not None:
            exports.extend(str(p) for p in run_exports(outcome, config, export_dir))
    return {"screens": audits, "exports": exports}


def run_nightly(
    ctx: TaskContext, session: date, export_dir: Path | None = None, workers: int | None = None
) -> dict[str, Any]:
    """Run ``NIGHTLY`` in order; -> per-task stats (or skip reasons), screens, ``_partial``."""
    result: dict[str, Any] = {}
    partial = False
    for name in NIGHTLY:
        if name == SCREENS:
            result.update(_screens(ctx, session, export_dir))
            partial |= any(a["coverage"] != "COMPLETE" for a in result["screens"])
            continue
        key = name.replace("-", "_")
        reason = skip_reason(name, ctx)
        if reason is not None:
            result[key] = reason
            continue
        record = run_task(name, ctx, {"session": session, "workers": workers})
        result[key] = record.stats
        partial |= record.status is not RunStatus.COMPLETE
    s = ctx.settings
    ctx.writer.raw.purge_before(session - timedelta(s.raw_retention_days))
    ctx.writer.staging.purge_before(session - timedelta(s.staging_retention_days))
    return {**result, "_partial": partial}


def nightly_job(params: Mapping[str, Any], ctx: JobContext) -> Mapping[str, Any]:
    """Job handler for the nightly workflow. params: ``session``, ``export_dir``, ``workers``.
    Resources: ``reader``, ``writer``, ``configs``, ``sources`` (by name), ``sources_settings``,
    ``unavailable`` (source -> why it was not built)."""
    r = ctx.resources
    task_ctx = TaskContext(
        r["reader"],
        r["writer"],
        r.get("sources", {}),
        r.get("sources_settings") or SourcesSettings(),
        r["configs"],
        user=ctx.user.user_id,
        unavailable=r.get("unavailable", {}),
    )
    export_dir = Path(params["export_dir"]) if params.get("export_dir") else None
    workers = int(params["workers"]) if params.get("workers") else None
    return run_nightly(task_ctx, date.fromisoformat(params["session"]), export_dir, workers)
