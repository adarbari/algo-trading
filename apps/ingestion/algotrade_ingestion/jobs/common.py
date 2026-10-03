"""Helpers shared by ingestion jobs."""

from datetime import date, datetime

import pandas as pd


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
