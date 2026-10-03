"""``retire-features``: delete a superseded feature group's stored tables (ADR 0023 step 3).

A group version replaced by a newer one (``features.registry.SUPERSEDED``: ``price_stats@v1``
by ``price_stats@v2`` and expression features, ...) stays readable until its table is
retired. Retiring first checks that the replacement (``Superseded.by``) has a partition for
every session the old table has: a session it lacks fails the run (backfill it with
``algotrade-ingest rollups --from D --to D``), and nothing is deleted. ``dry_run`` reports
the sessions and sizes only. The run record keeps what was deleted (``bytes_freed``).
"""

from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import ROLLUP_TABLE_PREFIX
from algotrade.features.registry import SUPERSEDED
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "retire_features"
SHOWN = 5  # uncovered sessions listed in the error and stats


def retire(ctx: TaskContext, session: date, group: str, dry_run: bool = False) -> RunRecord:
    """Delete ``rollups/instrument/<group>`` once its replacement covers its sessions."""
    if group not in SUPERSEDED:
        known = ", ".join(sorted(SUPERSEDED))
        raise ConfigurationError(f"{group} is not a superseded feature group ({known})")
    by = SUPERSEDED[group].by
    old, new = f"{ROLLUP_TABLE_PREFIX}{group}", f"{ROLLUP_TABLE_PREFIX}{by}"
    sessions = ctx.reader.dates(old)
    covered = set(ctx.reader.dates(new))
    missing = [d.isoformat() for d in sessions if d not in covered]
    with IngestRun(ctx, TASK, session) as run:
        run.stats.update(
            group=group,
            table=old,
            replacement=new,
            sessions=len(sessions),
            first=sessions[0].isoformat() if sessions else None,
            last=sessions[-1].isoformat() if sessions else None,
            bytes=ctx.writer.table_size(old),
            replacement_bytes=ctx.writer.table_size(new),
            uncovered=len(missing),
            uncovered_sessions=missing[:SHOWN],
            dry_run=dry_run,
        )
        if missing:
            raise ConfigurationError(
                f"{new} lacks {len(missing)} of {old}'s sessions (first {missing[:SHOWN]}): "
                f"backfill with algotrade-ingest rollups --from {missing[0]} --to {missing[-1]}"
            )
        if not dry_run:
            run.stats["bytes_freed"] = run.stats["bytes"]
            run.stats["partitions_deleted"] = ctx.writer.drop_table(old)
    return run.record
