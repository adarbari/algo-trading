"""Columnar OHLCV container used by the engine and exposed (read-only) to strategies."""

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
