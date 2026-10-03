"""Time helpers. All timestamps inside algotrade are UTC."""

from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt


def to_utc_datetime(value: np.datetime64) -> datetime:
    """Convert a numpy datetime64 (interpreted as UTC) to an aware ``datetime``."""
    micros = value.astype("datetime64[us]").astype(np.int64)
    return datetime.fromtimestamp(int(micros) / 1_000_000, tz=UTC)


def business_days(start: str, n: int) -> npt.NDArray[np.datetime64]:
    """``n`` consecutive weekdays (no holiday calendar) from ``start``, as datetime64[ns]."""
    first = np.busday_offset(np.datetime64(start, "D"), 0, roll="forward")
    days = np.busday_offset(first, np.arange(n), roll="forward")
    return days.astype("datetime64[ns]")
