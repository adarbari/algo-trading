"""Conversion between pandas DataFrames (I/O format) and core ``PriceSeries``."""

import numpy as np
import pandas as pd

from algotrade.core.series import FIELDS, PriceSeries

TIMESTAMP_COLUMN = "timestamp"
COLUMNS = (TIMESTAMP_COLUMN, *FIELDS)


def frame_to_series(symbol: str, frame: pd.DataFrame) -> PriceSeries:
    """Convert a validated OHLCV frame (see ``validate_ohlcv``) to a ``PriceSeries``."""
    ts = pd.to_datetime(frame[TIMESTAMP_COLUMN], utc=True).dt.tz_localize(None)
    return PriceSeries(
        instrument_id=symbol,
        timestamps=ts.to_numpy(dtype="datetime64[ns]").copy(),
        **{f: frame[f].to_numpy(dtype=np.float64).copy() for f in FIELDS},
    )


def series_to_frame(series: PriceSeries) -> pd.DataFrame:
    data: dict[str, object] = {TIMESTAMP_COLUMN: pd.to_datetime(series.timestamps, utc=True)}
    data.update({f: series.field(f) for f in FIELDS})
    return pd.DataFrame(data)
