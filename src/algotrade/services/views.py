"""Build the ``FeatureView`` screeners consume from stored feature tables."""

import math
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue, FeatureView
from algotrade.data import StoreReader
from algotrade.storage.tables.schemas import COMMON


def to_value(value: Any) -> FeatureValue:
    """Normalise pandas/numpy scalars into plain FeatureView values."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return to_value(value.item())
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def feature_view(
    reader: StoreReader,
    tables: Sequence[str],
    session_date: date,
    instruments: Sequence[str],
    as_of: datetime | None = None,
) -> FeatureView:
    """One row per instrument; instruments without features get an empty row (fail closed)."""
    rows: dict[str, dict[str, FeatureValue]] = {i: {} for i in instruments}
    for table in tables:
        frame = reader.require(
            table, session_date, f"algotrade-ingest features --date {session_date}", as_of
        )
        columns = [c for c in frame.columns if c not in (*COMMON, "instrument_id")]
        for record in frame.to_dict("records"):
            if record["instrument_id"] in rows:
                rows[record["instrument_id"]].update({c: to_value(record[c]) for c in columns})
    return FeatureView(session_date, rows)
