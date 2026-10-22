"""``screen-values-recluster``: rewrite the stored ``results/rule_screen`` and
``results/rule_screen_values`` files of earlier sessions in the layout the writer gives new ones
(``TableSpec.cluster_by``: sorted by ``instrument_id``, 8,192-row row groups), so a read of a few
instruments skips most of each file's row groups instead of decoding it whole. A file written
before stays correct without it (a reader filters whole groups it cannot skip); this task only
makes the old ones fast.

One run is one atomic publish through the live path's ``ResultWriter.publishing`` (ADR 0022):
the run's rows are read back as they are, written again under the same run id and the same
``knowledge_ts`` (point in time: the rows were knowable when the run ended, never "now"; the
commit is stamped with it, as ``screen-runs-backfill`` does), and both tables of a run commit
together or neither does. Every row keeps its licence columns and its value; only the order and
the row groups change, which the task checks by reading the run back.

- Idempotent and resumable by the store itself: a run whose file's footer already shows the
  declared layout (``ResultWriter.run_layouts``) is skipped, so a run cut short, or one limited
  by ``--limit``, is finished by running it again; a second run with nothing left writes nothing.
- Runs under the ingest run lock and the lowered priority every ingest command takes
  (``cli/main.py``), so it never overlaps the nightly; progress is saved to the run record after
  each session. The superseded file of a run stays until the partition's orphans are swept.
- Owner-run, never in the nightly: ``algotrade-ingest run screen-values-recluster --from D1 --to
  D2 [--limit N]``.
"""

from collections import Counter
from datetime import date

import pandas as pd

from algotrade.services.screening.rule_results import RULE_SCREEN, RULE_SCREEN_VALUES
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import result_table
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "screen_values_recluster"
SHOWN = 20  # runs whose rows changed on the way, listed in the run's stats
TABLES = (result_table(RULE_SCREEN), result_table(RULE_SCREEN_VALUES))


def _same_rows(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    """The two frames hold the same rows, whatever their order."""
    columns = list(before.columns)
    if sorted(columns) != sorted(after.columns) or len(before) != len(after):
        return False
    one = before.sort_values(columns, kind="stable").reset_index(drop=True)
    two = after[columns].sort_values(columns, kind="stable").reset_index(drop=True)
    return bool(one.equals(two))


class _Pass:
    """One recluster run's state: what each run did, and what to report."""

    def __init__(self, run: IngestRun, limit: int | None) -> None:
        self.run, self.limit = run, limit
        self.counts: Counter[str] = Counter()
        self.changed: list[str] = []

    def todo(self, day: date) -> dict[str, list[str]]:
        """The runs of ``day`` whose file is not laid out as declared, with their tables."""
        found: dict[str, list[str]] = {}
        for table in TABLES:
            for run_id, laid_out in self.run.writer.run_layouts(table, day).items():
                if laid_out:
                    self.counts["already_clustered"] += 1
                else:
                    found.setdefault(run_id, []).append(table)
        return dict(sorted(found.items()))

    def rewrite(self, day: date, run_id: str, tables: list[str]) -> None:
        """Rewrite one run's files (all its tables in one publish), or note why not."""
        run, reader, writer = self.run, self.run.ctx.reader, self.run.writer
        key = f"{day.isoformat()}/{run_id}"
        if self.limit is not None and self.counts["reclustered"] >= self.limit:
            return self._note(key, "NOT_REACHED", "not_reached")
        try:
            frames = {t: reader.read_run(t, day, run_id) for t in tables}
            held = {t: f for t, f in frames.items() if f is not None and not f.empty}
            if not held:  # superseded since the listing
                return self._note(key, "NO_ROWS", "no_rows")
            at = max(pd.Timestamp(f["knowledge_ts"].max()) for f in held.values())
            with writer.publishing(run_id, at.to_pydatetime()):  # every table or none
                for table, frame in held.items():
                    name = table.removeprefix("results/")
                    writer.write_result(name, day, run_id, frame, pending=True)
            back = {t: reader.read_run(t, day, run_id) for t in held}
        except Exception as exc:  # one run's failure never stops the others
            return run.fail(key, f"{type(exc).__name__}: {exc}", kind="FAILED")
        if any(b is None or not _same_rows(held[t], b) for t, b in back.items()):
            self.changed.append(key)
            return self._note(key, "MISMATCH: rows differ after the rewrite", "mismatch")
        return self._note(key, "OK", "reclustered")

    def _note(self, key: str, status: str, count: str) -> None:
        self.run.record_item(key, status)
        self.counts[count] += 1

    def finish(self, days: list[date], start: date | None, end: date | None) -> None:
        run, counts = self.run, self.counts
        run.stats.update(counts)
        run.stats.update(
            window=[start and start.isoformat(), end and end.isoformat()],
            first=days[0].isoformat() if days else None,
            last=days[-1].isoformat() if days else None,
            sessions=len(days),
            limit=self.limit,
            changed=self.changed[:SHOWN],
        )
        if self.changed:
            run.partial(f"{len(self.changed)} runs read back with different rows: check them")
        if counts["not_reached"]:
            run.partial(f"{counts['not_reached']} runs left by --limit: run it again to continue")


def recluster_screen_values(
    ctx: TaskContext, start: date | None, end: date | None, limit: int | None
) -> RunRecord:
    """Rewrite every run of the sessions in [``start``, ``end``] (default: all) whose
    ``rule_screen`` / ``rule_screen_values`` file is not clustered, at most ``limit`` runs this
    run, oldest session first."""
    reader = ctx.reader
    days = sorted({d for t in TABLES for d in reader.dates(t) if (start or d) <= d <= (end or d)})
    with IngestRun(ctx, TASK, days[-1] if days else (end or ctx.clock().date())) as run:
        work = _Pass(run, limit)
        for index, day in enumerate(days):
            for run_id, tables in work.todo(day).items():
                work.rewrite(day, run_id, tables)
            run.stats["progress"] = {
                "sessions_done": index + 1,
                "sessions": len(days),
                "last": day.isoformat(),
            }
            run.stats.update(work.counts)
            run.checkpoint()
        work.finish(days, start, end)
    return run.record
