"""Time helpers. All timestamps inside algotrade are UTC."""

from datetime import UTC, datetime

import numpy as np


def to_utc_datetime(value: np.datetime64) -> datetime:
    """Convert a numpy datetime64 (interpreted as UTC) to an aware ``datetime``."""
    micros = value.astype("datetime64[us]").astype(np.int64)
    return datetime.fromtimestamp(int(micros) / 1_000_000, tz=UTC)
