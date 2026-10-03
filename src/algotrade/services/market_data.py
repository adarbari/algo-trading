"""Turn stored bars into the aligned ``PriceSeries`` engines consume."""

from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.core.instruments import Instrument
from algotrade.core.series import FIELDS, PriceSeries, align
from algotrade.storage.readers import StoreReader


def frame_to_series(bars: pd.DataFrame) -> dict[str, PriceSeries]:
    """Split a bars frame (sorted by instrument, ts) into one series per instrument."""
    out: dict[str, PriceSeries] = {}
    for instrument, rows in bars.groupby("instrument_id", sort=True):
        ts = pd.to_datetime(rows["ts"], utc=True).dt.tz_localize(None)
        out[str(instrument)] = PriceSeries(
            instrument_id=str(instrument),
            timestamps=ts.to_numpy(dtype="datetime64[ns]").copy(),
            **{f: rows[f].to_numpy(dtype=np.float64).copy() for f in FIELDS},
        )
    return out


def load_price_data(
    reader: StoreReader,
    instruments: Sequence[str],
    start: date,
    end: date,
    interval: str = "1d",
    as_of: datetime | None = None,
) -> tuple[dict[str, PriceSeries], dict[str, Instrument]]:
    """Aligned series plus contract terms (as of ``start``) for a backtest."""
    bars = reader.bars(interval, start, end, instruments, as_of)
    terms = reader.instrument_terms(start, instruments)
    return align(frame_to_series(bars)), terms
