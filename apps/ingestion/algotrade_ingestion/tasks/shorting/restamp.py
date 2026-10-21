"""``restamp-known-from``: move the stored FINRA rows' ``known_from`` to the publication schedule
without refetching (ADR 0050, amendment 2026-10-20, repair).

Rows stored before the schedule rule carry the session after their fetch. ``daily.row_known_from``
would repair them on a ``--force`` refetch, which re-downloads every date (about 50 minutes, all
of it FINRA latency); the values are already stored, so this task applies the same rule to them
locally: an unflagged row gets ``min(stored, schedule)``, a flagged row (``revision_flag``) keeps
its stamp. Values are never touched. A row whose partition holds an earlier run with different
values for its key was restated, and a row absent from the earliest run was added later: its stamp
is late on purpose, so it is kept, never washed out to the schedule date. One run restates every
changed partition and publishes them together; the ingest lock the CLI holds covers the reads
through the commit. ``dry_run`` counts only.
"""

from collections.abc import Callable
from datetime import date

import pandas as pd

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext
from algotrade_ingestion.tasks.shorting import schedule, short_interest, short_volume
from algotrade_ingestion.tasks.shorting.daily import META

TASK = "restamp_known_from"
KEYS = ["instrument_id", "ts"]
SCHEDULES: dict[str, Callable[[date], date]] = {
    short_interest.TABLE: schedule.short_interest_known_from,
    short_volume.TABLE: schedule.short_volume_known_from,
}


def _restated(merged: pd.DataFrame, runs: list[pd.DataFrame]) -> pd.Series:
    """True per row of ``merged`` that was not in the partition's EARLIEST run as it is now (a
    row FINRA added after publication, picked up by a later fetch, is known from that fetch) or
    whose key has, in any run, other values (a restatement). ``runs``: oldest first, empty for a
    one-run partition, where neither can happen."""
    values = [c for c in merged.columns if c not in META and c not in KEYS]
    keyed = merged.set_index(KEYS)[values]
    out = pd.Series(False, index=keyed.index)
    if runs:
        out |= ~keyed.index.isin(runs[0].set_index(KEYS).index)
    for run in runs:
        other = run.drop_duplicates(KEYS).set_index(KEYS)[values].reindex(keyed.index)
        seen = other.notna().any(axis=1)
        differs = ~((other == keyed) | (other.isna() & keyed.isna())).all(axis=1)
        out |= seen & differs
    return pd.Series(out.to_numpy(), index=merged.index)


def restamped(
    frame: pd.DataFrame, known: Callable[[date], date], runs: list[pd.DataFrame]
) -> pd.DataFrame:
    """``frame`` (a partition as read) with ``known_from`` lowered to the schedule where allowed."""
    flag = frame["revision_flag"] if "revision_flag" in frame else pd.Series("", index=frame.index)
    keep = (flag.fillna("").astype(str).str.strip() != "") | _restated(frame, runs)
    sched = frame["ts"].map(lambda ts: known(ts.date()))
    stamps = [
        old if kept else min(old, new)
        for old, new, kept in zip(frame["known_from"], sched, keep, strict=True)
    ]
    return frame.assign(known_from=pd.Series(stamps, index=frame.index, dtype=object))


def restamp(ctx: TaskContext, session: date, dry_run: bool = False) -> RunRecord:
    """Restamp both FINRA tables over every stored partition; ``dry_run`` publishes nothing."""
    tables = ctx.writer.backend.tables
    changed: dict[str, int] = {}
    with IngestRun(ctx, TASK, session) as run:
        for table, known in SCHEDULES.items():
            changed[table] = 0
            for day in run.reader.dates(table):
                frame = run.reader.table(table, day)
                if frame is None or frame.empty:
                    continue
                ids = tables.partition_runs(table, day)
                runs = [r for i in ids if (r := run.reader.read_run(table, day, i)) is not None]
                out = restamped(frame, known, runs if len(runs) > 1 else [])
                n = int((out["known_from"] != frame["known_from"]).sum())
                changed[table] += n
                if n and not dry_run:
                    run.rewrite(table, day, out)
                run.record_item(f"{table}:{day.isoformat()}", f"OK: {n} restamped")
        run.stats.update(restamped=changed, dry_run=dry_run)
    return run.record
