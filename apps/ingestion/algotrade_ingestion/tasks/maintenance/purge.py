"""Retention: delete raw vendor responses, unfinished-run scratch, the uncommitted table
writes of runs that crashed (ADR 0022), old ``live/option_quotes`` partitions (the API's
recorded live quotes, ADR 0028; ``live_retention_days``, 7) and the edge trade ledger's
partitions (``results/edge_trades``, ADR 0064: its declared 45 days) but for those of the runs
the run reader keeps (``ledger_keep``: canonical, latest per edge and user, cited), older than
N days.

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
from algotrade.data.chains import LIVE_OPTION_QUOTES
from algotrade.services.read.evaluation.runs import ledger_keep
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.edge_schemas import EDGE_TRADES
from algotrade.storage.tables.schemas import require_retention
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
    before ``session - staging_keep_days``, uncommitted table writes last made before then, and
    ``live/option_quotes`` partitions before ``session - live_retention_days``."""
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
            live_partitions_removed=ctx.writer.purge_table_before(
                LIVE_OPTION_QUOTES, session - timedelta(ctx.settings.live_retention_days)
            ),
            ledger_partitions_removed=_purge_ledger(ctx, session),
            live_keep_days=ctx.settings.live_retention_days,
            keep_days=ctx.settings.raw_retention_days if keep_days is None else keep_days,
            raw_keep_days=windows,
            staging_keep_days=staging_days,
        )
    return run.record


def _purge_ledger(ctx: TaskContext, session: date) -> int | None:
    """The ledger partitions older than its retention but the kept runs'; None (nothing purged)
    without the configs the keep list is read from: never a purge that could drop a kept run."""
    if ctx.configs is None:
        return None
    cutoff = session - timedelta(require_retention(EDGE_TRADES.name))
    keep = ledger_keep(ctx.reader, ctx.configs)
    return ctx.writer.purge_table_before(EDGE_TRADES.name, cutoff, keep)
