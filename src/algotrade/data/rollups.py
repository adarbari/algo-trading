"""Stored rollup rows (``rollups/instrument/<name>@v<N>``) over a range of sessions.

Used by the rollup framework when one rollup reads another's output (``iv_history@v1``
reads 252 sessions of ``iv30@v1``). Each partition is one session's rows from the latest
run that wrote it (or the run current at ``as_of``). The stamp columns (``knowledge_ts``,
``source``, ``run_id``) are dropped; ``session_date`` is kept as a ``date``.
"""

from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

STAMPS = ("knowledge_ts", "source", "run_id")


def rollup_rows(
    reader: StoreReader, table: str, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """Rows with ``start <= session_date <= end`` sorted by (session_date, instrument_id),
    or ``None`` when nothing is stored in the range."""
    frame = reader.table_range(table, start, end, as_of)
    if frame is None or frame.empty:
        return None
    frame = frame.drop(columns=[c for c in STAMPS if c in frame.columns])
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    frame = frame.sort_values(["session_date", "instrument_id"], kind="stable")
    return frame.reset_index(drop=True)
