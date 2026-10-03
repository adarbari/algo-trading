"""Bars: read stored (unadjusted) bars and turn them into the aligned ``PriceSeries`` engines use.

Corporate actions are applied here, at read time (ADR 0016), from ``events/split`` and
``events/dividend`` read by event date (``data.events``):

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

from algotrade.core.errors import ConfigurationError, MissingDataError
from algotrade.core.fields import REFERENCE_TABLE
from algotrade.core.instruments import Instrument
from algotrade.core.series import FIELDS, PriceSeries, align
from algotrade.data.events import read_events
from algotrade.data.reference import REFERENCE_HINT, Snapshot, instrument_terms, read_snapshot
from algotrade.storage.readers import StoreReader


def bars(
    reader: StoreReader,
    interval: str,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Bars for ``start <= session_date <= end``, sorted by (instrument_id, ts).

    Raises ``MissingDataError`` when nothing is stored; backtests never fetch (ADR 0008).
    """
    table = f"bars/{interval}"
    frame = reader.table_range(table, start, end, as_of, instruments)
    if frame is None:
        hint = f"run the ingestion job that loads {table} for {start}..{end}"
        raise MissingDataError(table, f"no bars between {start} and {end}", hint)
    return frame.sort_values(["instrument_id", "ts"], kind="stable").reset_index(drop=True)


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
    reference: Snapshot  # the reference snapshot used; pre_snapshot = survivorship bias


def load_price_data(
    reader: StoreReader,
    instruments: Sequence[str],
    start: date,
    end: date,
    interval: str = "1d",
    as_of: datetime | None = None,
    adjustment: str = "splits",
) -> PriceData:
    """Aligned, corporate-action-adjusted series plus contract terms (as of ``start``).

    Splits and dividends are those whose event date falls in ``start..end``, wherever
    they were stored (``data.events``)."""
    frame = bars(reader, interval, start, end, instruments, as_of)
    reference, snapshot = read_snapshot(
        reader, REFERENCE_TABLE, start, REFERENCE_HINT, as_of, instruments
    )
    versions = {
        f"bars/{interval}": sorted(map(str, frame["run_id"].unique())),
        REFERENCE_TABLE: sorted(map(str, reference["run_id"].unique())),
    }
    if adjustment != "none":
        splits = read_events(reader, "events/split", start, end, instruments, as_of)
        dividends = read_events(reader, "events/dividend", start, end, instruments, as_of)
        frame = adjust_bars(frame, splits.frame, dividends.frame, adjustment)
        versions.update(
            {
                k: e.runs
                for k, e in (("events/split", splits), ("events/dividend", dividends))
                if e.runs
            }
        )
    terms = instrument_terms(reader, start, instruments, as_of)
    return PriceData(align(frame_to_series(frame)), terms, versions, snapshot)
