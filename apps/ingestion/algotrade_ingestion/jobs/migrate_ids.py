"""``migrate-ids``: move stored data from symbol ids to FIGI ids, append-only (ADR 0018).

Reads the latest ``instruments/id_map`` and, for every table partition whose latest run holds
a mapped id (``instrument_id``, ``underlying_id`` or ``parent_id``), writes the rewritten rows
as a **new run** with a later ``knowledge_ts``. Old runs are never touched, so reads ``as_of``
before the migration still see the old ids. A row is mapped only if it was known before the
upgrade was recorded (``known_at``); later rows under the same symbol id belong to whatever
listing holds that symbol now. Re-running maps nothing (idempotent).
"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import pandas as pd

from algotrade.core.errors import DataValidationError
from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.jobs.instrument_ids import ID_MAP

JOB = "migrate_ids"
ID_COLUMNS = ("instrument_id", "underlying_id", "parent_id")

type IdMap = Mapping[str, list[tuple[pd.Timestamp, str]]]  # old id -> [(known_at, new id)]


def load_id_map(reader: StoreReader) -> IdMap:
    day = reader.latest_date(ID_MAP)
    frame = reader.table(ID_MAP, day) if day is not None else None
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


def migrate_ids(
    writer: StoreWriter,
    reader: StoreReader,
    dry_run: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunRecord:
    now = clock()
    run_id = new_run_id(JOB, now.date(), now)
    id_map = load_id_map(reader)
    tables: dict[str, dict[str, int]] = {}
    failed: list[str] = []
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
            if dry_run:
                continue
            try:
                stamped = out.assign(knowledge_ts=pd.Timestamp(now), run_id=run_id)
                writer.write_table(table, day, run_id, stamped)
            except DataValidationError as exc:  # e.g. old and new id in one partition
                failed.append(f"{table} {day.isoformat()}: {exc}")
    stats = {
        "dry_run": dry_run,
        "mapped_ids": len(id_map),
        "tables": tables,
        "failed": failed[:20],
        "failed_count": len(failed),
    }
    status = RunStatus.PARTIAL if failed else RunStatus.COMPLETE
    record = RunRecord(run_id, JOB, now.date(), now, status, clock(), stats=stats)
    if not dry_run:
        writer.save_run(record)
    return record
