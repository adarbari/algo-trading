"""The readings of a stored chain the positioning groups share (``docs/data/positioning.md``,
"Shared rules").

- ``closing_spots``: ``S0``, the underlying quote's ``close`` when positive, else its ``price``
  (the feed's ``price`` carries after-hours trades while option quotes are closing quotes, so
  ``close`` is the spot that goes with them); NaN when neither is positive.
- ``expiry_days`` / ``days_to``: an expiry column as calendar days (``datetime64[D]``) and the
  days from the session to each, without building a ``date`` per quote.
- ``two_sided_mid``: the mid of a quote with ``bid > 0`` and ``ask > bid``, else NaN; the
  relative spread ``(ask - bid) / mid`` of the same quote.

The table names are ``options/iv30.py``'s: the same inputs, read the same way.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.rollups.options.iv30 import OPTIONS, UNDERLYINGS, by_id

__all__ = [
    "OPTIONS",
    "UNDERLYINGS",
    "closing_spots",
    "days_to",
    "expiry_days",
    "relative_spread",
    "two_sided_mid",
]


def closing_spots(underlyings: pd.DataFrame | None) -> pd.Series:
    """``S0`` by underlying id (str): ``close`` when positive, else ``price`` when positive,
    else NaN; an id quoted twice keeps its latest row (``by_id``). Empty without quotes."""
    if underlyings is None or underlyings.empty:
        return pd.Series(dtype=float)
    nothing = pd.Series(np.nan, index=underlyings.index)
    close = pd.to_numeric(underlyings.get("close", nothing), errors="coerce")
    price = pd.to_numeric(underlyings.get("price", nothing), errors="coerce")
    spot = close.where(close > 0, price.where(price > 0))
    return by_id(underlyings, spot.astype(float))


def expiry_days(expiry: pd.Series) -> np.ndarray:
    """An expiry column (dates or timestamps) as ``datetime64[D]``."""
    return pd.to_datetime(expiry).to_numpy(dtype="datetime64[D]")


def days_to(expiry: np.ndarray, session: date) -> np.ndarray:
    """Calendar days from ``session`` to each expiry (a datetime64 array of any unit)."""
    return (expiry.astype("datetime64[D]") - np.datetime64(session, "D")).astype("int64")


def two_sided_mid(bid: pd.Series, ask: pd.Series) -> np.ndarray:
    """``(bid + ask) / 2`` where the quote is two-sided (``bid > 0``, ``ask > bid``), else NaN."""
    b = pd.to_numeric(bid, errors="coerce").fillna(0).to_numpy(dtype=float)
    a = pd.to_numeric(ask, errors="coerce").fillna(0).to_numpy(dtype=float)
    return np.where((b > 0) & (a > b), (b + a) / 2, np.nan)


def relative_spread(bid: pd.Series, ask: pd.Series, mid: np.ndarray) -> np.ndarray:
    """``(ask - bid) / mid`` of a two-sided quote (``mid`` from ``two_sided_mid``), else NaN."""
    spread = pd.to_numeric(ask, errors="coerce").to_numpy(dtype=float) - pd.to_numeric(
        bid, errors="coerce"
    ).to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        relative: np.ndarray = spread / mid
    return relative
