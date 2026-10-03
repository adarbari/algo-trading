"""``migrate-ids``: move stored data from symbol ids to FIGI ids, append-only (ADR 0018).

Reads the latest ``instruments/id_map`` and, for every table partition whose latest run holds
a mapped id (``instrument_id``, ``underlying_id`` or ``parent_id``), writes the rewritten rows
as a **new run** with a later ``knowledge_ts``. Old runs are never touched, so reads ``as_of``
before the migration still see the old ids. A row is mapped only if it was known before the
upgrade was recorded (``known_at``); later rows under the same symbol id belong to whatever
listing holds that symbol now. Re-running maps nothing (idempotent).
"""

from collections.abc import Mapping
from datetime import date

import pandas as pd

from algotrade.core.errors import DataValidationError
from algotrade.data import StoreReader
from algotrade.data.reference import snapshot
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework import IngestRun, TaskContext
from algotrade_ingestion.tasks.instrument_ids import ID_MAP

TASK = "migrate_ids"
ID_COLUMNS = ("instrument_id", "underlying_id", "parent_id")

type IdMap = Mapping[str, list[tuple[pd.Timestamp, str]]]  # old id -> [(known_at, new id)]


def load_id_map(reader: StoreReader) -> IdMap:
    latest = snapshot(reader, ID_MAP)  # the map is cumulative: the latest has every upgrade
    frame = reader.table(ID_MAP, latest.snapshot_date) if latest is not None else None
    out: dict[str, list[tuple[pd.Timestamp, str]]] = {}
    if frame is None:
        return out
    known = pd.to_datetime(frame["known_at"], utc=True)
    for old, new, at in zip(frame["old_id"], frame["new_id"], known, strict=True):
        out.setdefault(str(old), []).append((at, str(new)))
    return {k: sorted(v) for k, v in out.items()}


def remap(frame: pd.DataFrame, id_map: IdMap) -> tuple[pd.DataFrame, int]:
    """-> (frame with mapped ids, rows changed). Pure; the input is not modified."""
    knowledge = pd.to_datetime(frame["knowledge_ts"], utc=True)
    out, changed = frame.copy(), pd.Series(False, index=frame.index)
    for column in (c for c in ID_COLUMNS if c in frame.columns):
        values = frame[column]
        mapped = values.astype(object).copy()
        for old in set(values.dropna().astype(str)) & set(id_map):
            pending = values.astype(str).eq(old)
            for known_at, new in id_map[old]:
                hit = pending & (knowledge < known_at)
                mapped[hit] = new
                pending &= ~hit
        moved = mapped.ne(values.astype(object)) & values.notna()
        if moved.any():
            out[column] = mapped
            changed |= moved
    return out, int(changed.sum())


def migrate_ids(ctx: TaskContext, dry_run: bool = False) -> RunRecord:
    reader = ctx.reader
    id_map = load_id_map(reader)
    tables: dict[str, dict[str, int]] = {}
    with IngestRun(ctx, TASK, ctx.clock().date(), save=not dry_run) as run:
        for table in reader.table_names() if id_map else []:
            if table == ID_MAP:
                continue
            for day in reader.dates(table):
                frame = reader.table(table, day)
                if frame is None or frame.empty or "knowledge_ts" not in frame.columns:
                    continue
                out, rows = remap(frame, id_map)
                if not rows:
                    continue
                counts = tables.setdefault(table, {"partitions": 0, "rows": 0})
                counts["partitions"] += 1
                counts["rows"] += rows
                if not dry_run:
                    _rewrite(run, table, day, out)
        failed = run.failures()
        run.stats.update(
            dry_run=dry_run,
            mapped_ids=len(id_map),
            tables=tables,
            failed=failed[:20],
            failed_count=len(failed),
        )
    return run.record


def _rewrite(run: IngestRun, table: str, day: date, frame: pd.DataFrame) -> None:
    try:
        run.rewrite(table, day, frame)
    except DataValidationError as exc:  # e.g. old and new id in one partition
        run.fail(f"{table} {day.isoformat()}", str(exc), kind="FAILED")
