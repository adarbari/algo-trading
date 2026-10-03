"""Turn stored bars into the aligned ``PriceSeries`` engines consume."""

from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class PriceData:
    """Aligned series, contract terms, and exactly which stored runs they came from."""

    series: dict[str, PriceSeries]
    terms: dict[str, Instrument]
    versions: dict[str, list[str]]  # table -> run ids read (for reproducibility)


def load_price_data(
    reader: StoreReader,
    instruments: Sequence[str],
    start: date,
    end: date,
    interval: str = "1d",
    as_of: datetime | None = None,
) -> PriceData:
    """Aligned series plus contract terms (as of ``start``) for a backtest."""
    bars = reader.bars(interval, start, end, instruments, as_of)
    reference = reader.instruments(start, instruments, as_of)
    versions = {
        f"bars/{interval}": sorted(map(str, bars["run_id"].unique())),
        "instruments/reference": sorted(map(str, reference["run_id"].unique())),
    }
    terms = reader.instrument_terms(start, instruments)
    return PriceData(align(frame_to_series(bars)), terms, versions)
