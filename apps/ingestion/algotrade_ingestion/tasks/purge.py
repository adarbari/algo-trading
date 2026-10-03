"""Retention: delete raw vendor responses and unfinished-run scratch older than N days.

Windows default to ``raw_retention_days`` / ``staging_retention_days`` in
``config/site/sources.toml``. The nightly workflow runs this last, after every session.
"""

from datetime import date, timedelta

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework import IngestRun, TaskContext

TASK = "purge_raw"


def purge(
    ctx: TaskContext,
    session: date,
    keep_days: int | None = None,
    staging_keep_days: int | None = None,
) -> RunRecord:
    """Purge raw files dated before ``session - keep_days`` and staging runs before
    ``session - staging_keep_days``."""
    raw_days = ctx.settings.raw_retention_days if keep_days is None else keep_days
    staging_days = (
        ctx.settings.staging_retention_days if staging_keep_days is None else staging_keep_days
    )
    with IngestRun(ctx, TASK, session) as run:
        run.stats.update(
            raw_files_removed=ctx.writer.raw.purge_before(session - timedelta(raw_days)),
            staging_runs_removed=ctx.writer.staging.purge_before(session - timedelta(staging_days)),
            keep_days=raw_days,
            staging_keep_days=staging_days,
        )
    return run.record
