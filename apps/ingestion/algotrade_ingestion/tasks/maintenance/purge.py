"""Retention: delete raw vendor responses, unfinished-run scratch, and the uncommitted table
writes of runs that crashed (ADR 0022), older than N days.

Windows default to ``config/site/sources.toml``: raw responses are kept per raw source for
its section's ``raw_retention_days`` (``ctx.raw_sections``, from the source registry, maps
each raw source name to its section, e.g. ``sec_edgar`` -> ``[sec_edgar]``), else the global
``raw_retention_days``; an
explicit ``keep_days`` applies to every source. Scratch and uncommitted writes use
``staging_retention_days``. The nightly workflow runs this last, after every session.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

from algotrade.config.site.settings import SourcesSettings
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "purge_raw"


def raw_keep_days(
    settings: SourcesSettings,
    sources: list[str],
    sections: Mapping[str, str],
    keep_days: int | None = None,
) -> dict[str, int]:
    """Days of raw responses to keep for each stored raw source: ``keep_days`` when given,
    else its section's ``raw_retention_days``, else the global window (also for raw sources
    the registry does not know, e.g. fixtures)."""
    out = {}
    for source in sources:
        if keep_days is not None:
            out[source] = keep_days
            continue
        section = sections.get(source)
        own = settings.vendor(section).raw_retention_days if section else None
        out[source] = settings.raw_retention_days if own is None else own
    return out


def purge(
    ctx: TaskContext,
    session: date,
    keep_days: int | None = None,
    staging_keep_days: int | None = None,
) -> RunRecord:
    """Purge each raw source's files dated before ``session - <its window>``, staging runs
    before ``session - staging_keep_days``, and uncommitted table writes last made before then."""
    raw = ctx.writer.raw
    windows = raw_keep_days(ctx.settings, raw.sources(), ctx.raw_sections, keep_days)
    staging_days = (
        ctx.settings.staging_retention_days if staging_keep_days is None else staging_keep_days
    )
    staging_cutoff = session - timedelta(staging_days)
    with IngestRun(ctx, TASK, session) as run:
        unpublished = datetime.combine(staging_cutoff, time(), UTC)
        removed = {
            s: raw.purge_before(session - timedelta(d), source=s) for s, d in windows.items()
        }
        run.stats.update(
            unpublished_runs_removed=ctx.writer.purge_pending_before(unpublished),
            raw_files_removed=sum(removed.values()),
            raw_files_removed_by_source=removed,
            staging_runs_removed=ctx.writer.staging.purge_before(staging_cutoff),
            keep_days=ctx.settings.raw_retention_days if keep_days is None else keep_days,
            raw_keep_days=windows,
            staging_keep_days=staging_days,
        )
    return run.record
