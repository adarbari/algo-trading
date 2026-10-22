"""``screen-values-recluster``: rewrite the stored ``results/rule_screen`` and
``results/rule_screen_values`` files of earlier sessions in the layout the writer gives new ones
(``TableSpec.cluster_by``: sorted by ``instrument_id``, 8,192-row row groups), so a read of a few
instruments skips most of each file's row groups instead of decoding it whole. A file written
before stays correct without it (a reader filters whole groups it cannot skip); this task only
makes the old ones fast.

One run is one atomic publish through the live path's ``ResultWriter.publishing`` (ADR 0022):
the run's rows are read back as they are, written again under the same run id and the same
``knowledge_ts`` (point in time: the rows were knowable when the run ended, never "now"), and both
tables of a run commit together or neither does. The commit is stamped with the run's own
``visible_from`` (``TableStore.run_visible_from``), so it is visible from exactly when it was.
Every row keeps its licence columns and its value; only the order and the row groups change, which
the task checks **before** the commit: inside the publish the run's pending files are read back
(``own_run``) and compared with the rows read; a difference aborts the publish and fails the run
item, so a rewrite that changed a value never becomes visible.

- Idempotent and resumable by the store itself: a run whose file's footer already shows the
  declared layout (``ResultWriter.run_layouts``) is skipped, so a run cut short, or one limited
  by ``--limit``, is finished by running it again; a second run with nothing left writes nothing.
- Runs under the ingest run lock and the lowered priority every ingest command takes
  (``cli/main.py``), so it never overlaps the nightly; progress is saved to the run record after
  each session.
- The commit keeps the old file as the run's ``prev`` (a read in flight finishes on it). Once the
  new file is ``SWAP_GRACE_S`` old the task forgets it (``TableStore.trim_superseded``: never while
  a pin, ADR 0077, may read it) and sweeps the partition, so one file per run is left. A pass over
  every session of the window does this at the end of the run (and each session's own leftovers of
  an earlier run at its start); a run whose grace has not passed by then is trimmed by the next
  run, which writes nothing else.
- Owner-run, never in the nightly: ``algotrade-ingest run screen-values-recluster --from D1 --to
  D2 [--limit N]``.
"""

from collections import Counter
from datetime import date

import pandas as pd

from algotrade.data import StoreReader
from algotrade.services.screening.rule_results import RULE_SCREEN, RULE_SCREEN_VALUES
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import PartitionBusyError
from algotrade.storage.tables.schemas import result_table
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "screen_values_recluster"
TABLES = (result_table(RULE_SCREEN), result_table(RULE_SCREEN_VALUES))


def _same_rows(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    """The two frames hold the same rows, whatever their order."""
    columns = list(before.columns)
    if sorted(columns) != sorted(after.columns) or len(before) != len(after):
        return False
    one = before.sort_values(columns, kind="stable").reset_index(drop=True)
    two = after[columns].sort_values(columns, kind="stable").reset_index(drop=True)
    return bool(one.equals(two))


class RewriteChangedRowsError(RuntimeError):
    """The pending files of a run read back with other rows than the run held."""


class _Pass:
    """One recluster run's state: what each run did, and what to report."""

    def __init__(self, run: IngestRun, limit: int | None) -> None:
        self.run, self.limit = run, limit
        self.counts: Counter[str] = Counter()

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
            seen = [writer.run_visible_from(t, day).get(run_id) for t in held]
            at = max(v for v in seen if v is not None)  # the run's own, never "now"
            own = StoreReader(writer.backend, own_run=run_id)
            with writer.publishing(run_id, at):  # every table or none
                for table, frame in held.items():
                    name = table.removeprefix("results/")
                    writer.write_result(name, day, run_id, frame, pending=True)
                for table, frame in held.items():  # before the commit: a mismatch aborts it
                    back = own.read_run(table, day, run_id)
                    if back is None or not _same_rows(frame, back):
                        raise RewriteChangedRowsError(f"{table}: rows differ after the rewrite")
        except Exception as exc:  # one run's failure never stops the others
            return run.fail(key, f"{type(exc).__name__}: {exc}", kind="FAILED")
        return self._note(key, "OK", "reclustered")

    def tidy(self, day: date) -> None:
        """Forget the old file each run of ``day`` keeps beside its clustered one (once its grace
        has passed and no pin needs it) and sweep it: one file per run is left."""
        writer = self.run.writer
        for table in TABLES:
            try:
                runs = list(writer.run_layouts(table, day))
                self.counts["trimmed"] += writer.trim_superseded(table, day, runs)
                self.counts["swept_files"] += writer.sweep_orphans(table, day)
            except PartitionBusyError:  # a pending run wrote there: the next run tidies
                self.counts["tidy_deferred"] += 1

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
        )
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
            work.tidy(day)  # what an earlier run left
            for run_id, tables in work.todo(day).items():
                work.rewrite(day, run_id, tables)
            run.stats["progress"] = {
                "sessions_done": index + 1,
                "sessions": len(days),
                "last": day.isoformat(),
            }
            run.stats.update(work.counts)
            run.checkpoint()
        for day in days:
            work.tidy(day)  # this run's own, where the grace has passed
        work.finish(days, start, end)
    return run.record
