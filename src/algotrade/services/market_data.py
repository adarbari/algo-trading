"""Turn stored (unadjusted) bars into the aligned ``PriceSeries`` engines consume.

Corporate actions are applied here, at read time (ADR 0016), from ``events/split`` and
``events/dividend``:

- ``none``:         prices as traded
- ``splits``:       earlier bars divided by each later split ratio (volume multiplied), so a
                    split is not a price jump; the default for backtests
- ``total_return``: splits, plus earlier bars scaled by ``1 - dividend / previous close`` at
                    each ex-date, so returns include dividends
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.core.errors import ConfigurationError
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


ADJUSTMENTS = ("none", "splits", "total_return")
_PRICES = ["open", "high", "low", "close"]
_ALL_TIME = date(1900, 1, 1)


def _events(
    reader: StoreReader, table: str, instruments: Sequence[str], end: date, as_of: datetime | None
) -> tuple[pd.DataFrame, list[str]]:
    """Every event known up to ``end`` (union of snapshots, latest knowledge per event)."""
    frame = reader.table_range(table, _ALL_TIME, end, as_of, instruments)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["instrument_id", "ts"]), []
    runs = sorted(map(str, frame["run_id"].unique()))
    frame = frame.sort_values("knowledge_ts").drop_duplicates(["instrument_id", "ts"], keep="last")
    return frame.reset_index(drop=True), runs


def adjust_bars(
    bars: pd.DataFrame, splits: pd.DataFrame, dividends: pd.DataFrame, mode: str
) -> pd.DataFrame:
    """Back-adjust bars (sorted by instrument, ts) for corporate actions after each bar."""
    if mode not in ADJUSTMENTS:
        raise ConfigurationError(f"price adjustment must be one of {ADJUSTMENTS}, got {mode!r}")
    if mode == "none" or bars.empty:
        return bars
    out = bars.copy()
    ids = out["instrument_id"].to_numpy(dtype=str)
    ts = pd.to_datetime(out["ts"], utc=True).to_numpy()
    close = out["close"].to_numpy(dtype=float)
    price_factor = np.ones(len(out))
    volume_factor = np.ones(len(out))
    if not splits.empty:
        split_ids = splits["instrument_id"].to_numpy(dtype=str)
        split_ts = pd.to_datetime(splits["ts"], utc=True).to_numpy()
        for iid, when, ratio in zip(
            split_ids, split_ts, splits["ratio"].to_numpy(dtype=float), strict=True
        ):
            before = (ids == iid) & (ts < when)
            price_factor[before] /= ratio
            volume_factor[before] *= ratio
    if mode == "total_return" and not dividends.empty:
        div_ids = dividends["instrument_id"].to_numpy(dtype=str)
        div_ts = pd.to_datetime(dividends["ts"], utc=True).to_numpy()
        amounts = dividends["cash_amount"].to_numpy(dtype=float)
        for iid, when, amount in zip(div_ids, div_ts, amounts, strict=True):
            before = (ids == iid) & (ts < when)
            if before.any():
                previous_close = close[before][-1]  # unadjusted basis, as the cash amount is
                if previous_close > amount:
                    price_factor[before] *= 1 - amount / previous_close
    out[_PRICES] = out[_PRICES].to_numpy() * price_factor[:, None]
    out["volume"] = out["volume"].to_numpy() * volume_factor
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
    adjustment: str = "splits",
) -> PriceData:
    """Aligned, corporate-action-adjusted series plus contract terms (as of ``start``)."""
    bars = reader.bars(interval, start, end, instruments, as_of)
    reference = reader.instruments(start, instruments, as_of)
    versions = {
        f"bars/{interval}": sorted(map(str, bars["run_id"].unique())),
        "instruments/reference": sorted(map(str, reference["run_id"].unique())),
    }
    if adjustment != "none":
        splits, split_runs = _events(reader, "events/split", instruments, end, as_of)
        dividends, dividend_runs = _events(reader, "events/dividend", instruments, end, as_of)
        bars = adjust_bars(bars, splits, dividends, adjustment)
        versions.update(
            {
                k: v
                for k, v in (("events/split", split_runs), ("events/dividend", dividend_runs))
                if v
            }
        )
    terms = reader.instrument_terms(start, instruments)
    return PriceData(align(frame_to_series(bars)), terms, versions)
