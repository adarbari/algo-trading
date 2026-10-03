"""Build point-in-time inputs (universe, FeatureView) from storage for screeners."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.core.errors import MissingDataError
from algotrade.core.feature_view import FeatureValue, FeatureView
from algotrade.storage.readers import StoreReader
from algotrade.storage.schemas import COMMON

UNIVERSE_HINT = "algotrade-ingest universe import --stocks <csv> --etfs <csv> --version <v>"


@dataclass(frozen=True)
class Universe:
    snapshot_date: date
    frame: pd.DataFrame  # every covered instrument; strategies narrow it with selections
    rows_loaded: int
    version: str
    last_verified: date | None

    @property
    def instruments(self) -> list[str]:
        return list(self.frame["instrument_id"])

    def is_stale(self, session_date: date, max_age_days: int) -> bool:
        reference = self.last_verified or self.snapshot_date
        return session_date - reference > timedelta(days=max_age_days)


def load_universe(
    reader: StoreReader, session_date: date, as_of: datetime | None = None
) -> Universe:
    snapshot = reader.latest_date("universe", on_or_before=session_date)
    if snapshot is None:
        raise MissingDataError(
            "universe", f"no snapshot on or before {session_date}", UNIVERSE_HINT
        )
    frame = reader.require("universe", snapshot, UNIVERSE_HINT, as_of)
    raw_verified = frame["last_verified"] if "last_verified" in frame else pd.Series(dtype=str)
    verified = pd.to_datetime(raw_verified, errors="coerce").dropna()
    return Universe(
        snapshot_date=snapshot,
        frame=frame.reset_index(drop=True),
        rows_loaded=len(frame),
        version=str(frame["universe_version"].iloc[0]) if len(frame) else "",
        # Oldest verification date: the conservative reading when rows disagree (fail closed).
        last_verified=verified.min().date() if len(verified) else None,
    )


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
