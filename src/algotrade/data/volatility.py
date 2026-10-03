"""IBKR's implied and historical vol per underlying and session (``volatility/ibkr_iv30``).

One partition per session; runs merge (a history backfill writes many sessions, the nightly
snapshot one), the latest run's row winning per instrument (``storage/backends``). Rows carry
``iv30_ibkr`` / ``hv30_ibkr`` (decimals, IB's 30-day vols) and ``source_kind`` (``history``:
IB's daily bar, ``snapshot``: the streamed value after the close). ADR 0028.
"""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

IBKR_IV30 = "volatility/ibkr_iv30"
COLUMNS = ("session_date", "instrument_id", "symbol", "iv30_ibkr", "hv30_ibkr", "source_kind")


def ibkr_iv30(
    reader: StoreReader,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Rows with ``start <= session_date <= end`` (only ``instruments``' when given), sorted
    by session then instrument, ``session_date`` as dates; an empty frame when none."""
    frame = reader.table_range(IBKR_IV30, start, end, as_of, instruments)
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in COLUMNS})
    out = frame.reindex(columns=list(COLUMNS))
    out["session_date"] = pd.to_datetime(out["session_date"]).dt.date
    out["instrument_id"] = out["instrument_id"].astype(str)
    return out.sort_values(["session_date", "instrument_id"], kind="stable").reset_index(drop=True)
