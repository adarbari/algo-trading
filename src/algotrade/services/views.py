"""Build the ``FeatureView`` screeners consume from stored feature tables and expression
features (computed on read: ``services.features``)."""

import math
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.core.views.feature_view import FeatureValue, FeatureView
from algotrade.data import StoreReader
from algotrade.services.features import read_expressions
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
    expressions: Sequence[str] = (),
) -> FeatureView:
    """One row per instrument; instruments without features get an empty row (fail closed).
    ``tables``' columns by column name; ``expressions`` (expression features) by name."""
    rows: dict[str, dict[str, FeatureValue]] = {i: {} for i in instruments}
    if expressions:
        computed = read_expressions(reader, expressions, session_date, as_of=as_of)
        for record in computed.frame.to_dict("records"):
            if record["instrument_id"] in rows:
                values = {n: to_value(record[n]) for n in expressions}
                rows[record["instrument_id"]].update(values)
    for table in tables:
        frame = reader.require(
            table, session_date, f"algotrade-ingest rollups --date {session_date}", as_of
        )
        columns = [c for c in frame.columns if c not in (*COMMON, "instrument_id")]
        for record in frame.to_dict("records"):
            if record["instrument_id"] in rows:
                rows[record["instrument_id"]].update({c: to_value(record[c]) for c in columns})
    return FeatureView(session_date, rows)
