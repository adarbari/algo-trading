"""Stored rollup rows (``rollups/instrument/<name>@v<N>``): a range of sessions, one session,
or one instrument's latest row.

``rollup_rows`` serves the rollup framework when one rollup reads another's output
(``iv_history@v1`` reads 252 sessions of ``iv30@v1``) and the explore queries (feature
series, pages); ``rollup_on`` one session's rows for a consumer comparing them (the live
verification). Each partition is one session's rows from the latest run that wrote it (or the
run current at ``as_of``). The stamp columns (``knowledge_ts``, ``source``, ``run_id``) are
dropped; ``session_date`` is kept as a ``date``.
"""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.data.reference import snapshot
from algotrade.storage.tables.readers import StoreReader

STAMPS = ("knowledge_ts", "source", "run_id")


def rollup_rows(
    reader: StoreReader,
    table: str,
    start: date,
    end: date,
    as_of: datetime | None = None,
    instruments: Sequence[str] | None = None,
) -> pd.DataFrame | None:
    """Rows with ``start <= session_date <= end`` sorted by (session_date, instrument_id)
    (only ``instruments``' rows when given), or ``None`` when nothing is stored in the range."""
    frame = reader.table_range(table, start, end, as_of, instruments)
    if frame is None or frame.empty:
        return None
    frame = frame.drop(columns=[c for c in STAMPS if c in frame.columns])
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    frame = frame.sort_values(["session_date", "instrument_id"], kind="stable")
    return frame.reset_index(drop=True)


def rollup_row(
    reader: StoreReader,
    table: str,
    instrument_id: str,
    on: date | None = None,
    as_of: datetime | None = None,
) -> tuple[date, dict[str, object]] | None:
    """One instrument's row from the latest partition of ``table`` on or before ``on`` (the
    latest when ``on`` is None) -> (its session, column -> value); ``None`` when there is no
    such partition or the instrument has no row in it."""
    snap = snapshot(reader, table, on)
    if snap is None or snap.pre_snapshot:
        return None
    frame = reader.table(table, snap.snapshot_date, as_of, [instrument_id])
    if frame is None or frame.empty:
        return None
    row = frame.drop(columns=[c for c in (*STAMPS, "session_date") if c in frame.columns])
    return snap.snapshot_date, {str(k): v for k, v in row.iloc[0].items()}


def rollup_on(
    reader: StoreReader,
    table: str,
    session: date,
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame | None:
    """One session's stored rows of a rollup (optionally only ``ids``), stamps dropped; ``None``
    when that session has none. For consumers comparing a session's values (verification)."""
    frame = reader.table(table, session, as_of, list(ids) if ids is not None else None)
    if frame is None or frame.empty:
        return None
    return frame.drop(columns=[c for c in STAMPS if c in frame.columns]).reset_index(drop=True)
