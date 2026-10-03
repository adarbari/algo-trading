"""Helpers shared by ingestion jobs."""

from datetime import date, datetime

import pandas as pd

from algotrade.storage.resolver import SymbolResolver


def stamp(
    frame: pd.DataFrame, session_date: date, now: datetime, source: str, run_id: str
) -> pd.DataFrame:
    """Add the point-in-time columns every stored row needs (ADR 0007)."""
    out = frame.copy()
    out["session_date"] = session_date
    out["knowledge_ts"] = pd.Timestamp(now)
    out["source"] = source
    out["run_id"] = run_id
    return out


def with_ids(
    frame: pd.DataFrame, resolver: SymbolResolver, keep_symbol: bool = True
) -> tuple[pd.DataFrame, int]:
    """Resolve a vendor frame keyed by ``symbol`` to ``instrument_id`` (ADR 0018).

    -> (frame, symbols the reference did not know). Frames that already carry ids pass."""
    if "instrument_id" in frame.columns or (frame.empty and "symbol" not in frame.columns):
        return frame, 0
    out, unknown = resolver.resolve(frame)
    return (out if keep_symbol else out.drop(columns="symbol")), unknown
