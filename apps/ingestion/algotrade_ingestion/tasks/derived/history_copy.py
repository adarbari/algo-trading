"""The ``history-copy`` task (ADR 0060): keep the derived history copies current after a night's
publishing, so long range reads (Explore charts, market history) read one file per year.

Which tables comes from ``nightly.toml [history_copy]``: every table under ``market_prefix``
for all the years it has partitions, and each of ``instrument_tables`` for the last
``recent_years`` calendar years (older years are removed, which is how the disk budget holds).
``TableStore.build_history`` rebuilds only the years whose partitions changed, so a night
rebuilds the session's year. The task writes no table and no run's publish: a failure or a skip
leaves the earlier copy in place and reads fall back to the partitions, which is why the step is
optional. It skips a table, with a reason the acceptance check turns into a WARN, when

- the disk has less free than ``free_disk_floor_gb`` plus the table's current copy (a rebuilt
  year exists twice for a moment), or
- the instrument tables' copies already hold ``budget_gb`` (a table not yet copied is not started).
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

from algotrade.config.site.nightly import HistoryCopySettings, NightlySettings
from algotrade.config.site.settings import load_nightly
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.maintenance.quality import Check

TASK = "history-copy"
GB = 1024**3


def settings_of(ctx: TaskContext) -> HistoryCopySettings:
    nightly = load_nightly(ctx.configs) if ctx.configs is not None else NightlySettings()
    return nightly.history_copy


def skip_reason(ctx: TaskContext) -> str | None:
    """The nightly's skip rule: the step is switched off (``[history_copy] enabled``)."""
    return None if settings_of(ctx).enabled else "skipped: [history_copy] enabled = false"


def build_copies(ctx: TaskContext, session: date) -> RunRecord:
    """Bring every configured table's history copy up to date as of ``session``."""
    cfg = settings_of(ctx)
    built: dict[str, list[int]] = {}
    skipped: dict[str, str] = {}
    market = sorted(
        t for t in ctx.reader.table_names() if cfg.market_prefix and t.startswith(cfg.market_prefix)
    )
    recent = [session.year - k for k in range(cfg.recent_years)]
    instrument_bytes = sum(ctx.writer.history_size(t) for t in cfg.instrument_tables)
    with IngestRun(ctx, TASK, session) as run:
        for table, years, budgeted in (
            *((t, sorted({d.year for d in ctx.reader.dates(t)}), False) for t in market),
            *((t, recent, True) for t in cfg.instrument_tables),
        ):
            held = ctx.writer.history_size(table)
            if budgeted and held == 0 and instrument_bytes >= cfg.budget_gb * GB:
                skipped[table] = f"the instrument copies already hold {cfg.budget_gb} GB"
                continue
            free = ctx.writer.free_bytes()
            if free < cfg.free_disk_floor_gb * GB + held:
                skipped[table] = (
                    f"{free / GB:.1f} GB free, below the {cfg.free_disk_floor_gb} GB floor"
                )
                continue
            try:
                built[table] = ctx.writer.build_history(table, years)
            except (OSError, ValueError) as exc:  # no instrument_id column, a full disk, ...
                skipped[table] = f"{type(exc).__name__}: {exc}"
                continue
            if budgeted:
                instrument_bytes += ctx.writer.history_size(table) - held
        run.stats.update(
            built={t: y for t, y in built.items() if y},
            skipped=skipped,
            instrument_copy_bytes=instrument_bytes,
            budget_gb=cfg.budget_gb,
        )
    return run.record


def check_history_copy(stats: Mapping[str, Any], session: date) -> list[Check]:
    """One WARN per table the step skipped, and one when the instrument copies exceed the
    budget (never a FAIL: a missing copy only means reads use the partitions)."""
    checks = [
        Check("history_copy", "WARN", f"{table}: {why}", data={"table": table})
        for table, why in stats.get("skipped", {}).items()
    ]
    used, budget = stats.get("instrument_copy_bytes", 0), stats.get("budget_gb", 0) * GB
    if used > budget:
        checks.append(
            Check(
                "history_copy_budget",
                "WARN",
                f"instrument copies {used / GB:.2f} GB > {budget / GB:.1f} GB",
            )
        )
    return checks
