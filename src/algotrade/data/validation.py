"""Sanity checks every dataset must pass before it reaches a strategy.

Bad data silently produces great-looking backtests, so we fail loudly instead.
"""

import pandas as pd

from algotrade.core.errors import DataValidationError
from algotrade.data.frames import COLUMNS, TIMESTAMP_COLUMN

PRICE_COLUMNS = ("open", "high", "low", "close")


def validate_ohlcv(frame: pd.DataFrame, source: str) -> None:
    """Raise ``DataValidationError`` listing every problem found in ``frame``."""
    missing = [c for c in COLUMNS if c not in frame.columns]
    if missing:
        raise DataValidationError(source, [f"missing columns: {missing}"])
    if frame.empty:
        raise DataValidationError(source, ["no rows"])

    problems: list[str] = []
    if frame[list(COLUMNS)].isna().to_numpy().any():
        problems.append("contains NaN values")

    ts = pd.to_datetime(frame[TIMESTAMP_COLUMN], utc=True)
    if not ts.is_monotonic_increasing:
        problems.append("timestamps are not sorted ascending")
    if ts.duplicated().any():
        problems.append(f"{int(ts.duplicated().sum())} duplicate timestamps")

    prices = frame[list(PRICE_COLUMNS)]
    if (prices <= 0).to_numpy().any():
        problems.append("non-positive prices")
    if (frame["volume"] < 0).any():
        problems.append("negative volume")

    body_high = frame[["open", "close"]].max(axis=1)
    body_low = frame[["open", "close"]].min(axis=1)
    if (frame["high"] < body_high).any():
        problems.append("high below open/close")
    if (frame["low"] > body_low).any():
        problems.append("low above open/close")

    if problems:
        raise DataValidationError(source, problems)
