"""Columnar OHLCV container used by the engine and exposed (read-only) to strategies."""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
TimeArray = npt.NDArray[np.datetime64]

FIELDS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True, slots=True)
class PriceSeries:
    """OHLCV bars for one instrument. Arrays are made read-only on construction."""

    instrument_id: str
    timestamps: TimeArray
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    volume: FloatArray

    def __post_init__(self) -> None:
        n = len(self.timestamps)
        for name in FIELDS:
            arr = getattr(self, name)
            if len(arr) != n:
                raise ValueError(f"{self.instrument_id}.{name} has {len(arr)} rows, expected {n}")
            arr.setflags(write=False)
        self.timestamps.setflags(write=False)

    def __len__(self) -> int:
        return len(self.timestamps)

    def field(self, name: str) -> FloatArray:
        if name not in FIELDS:
            raise KeyError(f"Unknown field {name!r}; expected one of {FIELDS}")
        arr: FloatArray = getattr(self, name)
        return arr


def align(series: Mapping[str, PriceSeries]) -> dict[str, PriceSeries]:
    """Restrict every series to the timestamps present in *all* of them.

    Dropping (rather than forward-filling) keeps the engine honest: a strategy never
    trades on a bar that did not exist for one of its instruments.
    """
    if not series:
        return {}
    common: TimeArray | None = None
    for s in series.values():
        common = s.timestamps if common is None else np.intersect1d(common, s.timestamps)
    assert common is not None
    out: dict[str, PriceSeries] = {}
    for instrument, s in series.items():
        mask = np.isin(s.timestamps, common)
        out[instrument] = PriceSeries(
            instrument_id=instrument,
            timestamps=s.timestamps[mask].copy(),
            **{f: s.field(f)[mask].copy() for f in FIELDS},
        )
    return out


def panel(series: Mapping[str, PriceSeries]) -> dict[str, PriceSeries]:
    """Put every series on the UNION of their timestamps, NaN where an instrument has no bar.

    For a changing tradable set (``rebalance_selection``), where ``align`` would drop every
    session some instrument ever selected lacks. NaN is never filled: the engine treats an
    instrument as tradable on a bar only when the bar exists (``engines.backtest.universe``).
    """
    if not series:
        return {}
    timeline = np.unique(np.concatenate([s.timestamps for s in series.values()]))
    out: dict[str, PriceSeries] = {}
    for instrument, s in series.items():
        rows = np.searchsorted(timeline, s.timestamps)
        fields = {}
        for f in FIELDS:
            values = np.full(len(timeline), np.nan)
            values[rows] = s.field(f)
            fields[f] = values
        out[instrument] = PriceSeries(instrument, timeline.copy(), **fields)
    return out
