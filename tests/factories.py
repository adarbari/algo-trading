"""Small builders for test data. Prefer these over hand-rolled arrays in tests."""

from collections.abc import Sequence
from datetime import UTC, datetime

import numpy as np

from algotrade.core.series import PriceSeries
from algotrade.core.types import Fill, Side
from algotrade.data.synthetic import business_days

T0 = datetime(2024, 1, 2, tzinfo=UTC)


def series_from_closes(
    closes: Sequence[float], symbol: str = "TEST", opens: Sequence[float] | None = None
) -> PriceSeries:
    c = np.asarray(closes, dtype=np.float64)
    o = np.asarray(opens if opens is not None else closes, dtype=np.float64)
    return PriceSeries(
        symbol=symbol,
        timestamps=business_days("2024-01-01", len(c)),
        open=o,
        high=np.maximum(o, c) * 1.01,
        low=np.minimum(o, c) * 0.99,
        close=c,
        volume=np.full(len(c), 1_000.0),
    )


def fill(
    symbol: str = "TEST", side: Side = Side.BUY, qty: float = 10, price: float = 100.0,
    commission: float = 0.0,
) -> Fill:  # fmt: skip
    return Fill(symbol, side, qty, price, commission, T0)
