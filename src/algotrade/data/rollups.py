"""Stored rollup rows (``rollups/instrument/<name>@v<N>``, ``rollups/market/<name>@v<N>``): a
range of sessions, one session, or one instrument's latest row.

``rollup_rows``: for the rollup framework, when one rollup reads another's output
(``iv_history@v2`` reads 252 sessions of ``iv30@v1``; ``data.feature_inputs``), and for the
read model's range reads (feature series); ``rollup_on`` one session's rows for a consumer
comparing them (the live verification); ``group_view`` the fields of feature groups for one
session of some entities that are not instruments (a market group's ``MKT:US`` row, ADR 0047;
instruments go through ``reference.instrument_view``). ``feature_rows``: for the read path of
expression features (``services.features``), only the columns a formula needs. Each partition is one
session's rows from the latest run that wrote it (or the run current at ``as_of``). The stamp
columns (``knowledge_ts``, ``source``, ``run_id``) are dropped; ``session_date`` is kept as a
``date``.
"""

from collections.abc import Collection, Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.fields import field_source, group_of_table
from algotrade.data.reference import join_fields, snapshot
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
    return _rows(reader.table_range(table, start, end, as_of, instruments))


def feature_rows(
    reader: StoreReader,
    table: str,
    columns: Collection[str],
    start: date,
    end: date,
    as_of: datetime | None = None,
    instruments: Sequence[str] | None = None,
) -> pd.DataFrame | None:
    """``session_date``, ``instrument_id`` and ``columns`` (a column a partition lacks is
    null) for ``start..end`` in date order (only ``instruments``' rows when given), reading
    nothing else; ``None`` when nothing is stored."""
    read = reader.table_range(table, start, end, as_of, instruments, sorted(columns))
    frame = _rows(read, False)
    if frame is None:
        return None
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[["session_date", "instrument_id", *sorted(columns)]]


def _rows(frame: pd.DataFrame | None, ordered: bool = True) -> pd.DataFrame | None:
    """Stamps dropped, ``session_date`` as dates; sorted by session and instrument when
    ``ordered`` (else in date order, as read)."""
    if frame is None or frame.empty:
        return None
    frame = frame.drop(columns=[c for c in STAMPS if c in frame.columns])
    if frame["session_date"].dtype != object:  # stored as date32: already dates
        frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    if ordered:
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


def group_view(
    reader: StoreReader,
    session: date,
    fields: Sequence[str],
    ids: Sequence[str],
    as_of: datetime | None = None,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """``instrument_id`` (each of ``ids``) and each of ``fields`` (feature group fields only,
    ``market.<group>@v<N>.<column>``) from exactly ``session``'s partition -> (the frame, the
    tables with no partition for it, whose fields are absent)."""
    wanted: dict[str, list[tuple[str, str]]] = {}
    for name in fields:
        table, column = field_source(name)
        if group_of_table(table) is None:
            raise ValueError(f"{name}: not a feature group field")
        wanted.setdefault(table, []).append((name, column))
    out = pd.DataFrame({"instrument_id": [str(i) for i in ids]})
    missing = []
    for table, columns in wanted.items():
        frame = reader.table(table, session, as_of, list(ids))
        if frame is None:
            missing.append(table)
            continue
        out = join_fields(out, frame, columns)
    return out, tuple(sorted(missing))
