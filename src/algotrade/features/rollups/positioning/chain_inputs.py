"""The readings of a stored chain the positioning groups share (``docs/data/positioning.md``,
"Shared rules").

- ``closing_spots``: ``S0``, the underlying quote's ``close`` when positive, else its ``price``
  (the feed's ``price`` carries after-hours trades while option quotes are closing quotes, so
  ``close`` is the spot that goes with them); NaN when neither is positive.
- ``expiry_days`` / ``days_to``: an expiry column as calendar days (``datetime64[D]``) and the
  days from the session to each, without building a ``date`` per quote.
- ``one_row_per_contract``: a contract stored twice keeps its latest row (by ``ts``), so a sum
  over the chain never counts it twice and the result does not depend on staging order.
- ``read_chain``: the session's chain as the pricing groups (``skew``, ``iv_term``) start from it:
  the Treasury curve, ``closing_spots``, the quotes (one row per contract, ``underlying_id`` a
  str, ``expiry`` a ``date``) and the ids to report (every quoted or chained underlying).
- ``two_sided_mid``: the mid of a quote with ``bid > 0`` and ``ask > bid``, else NaN; the
  relative spread ``(ask - bid) / mid`` of the same quote.

The table names are ``options/iv30.py``'s: the same inputs, read the same way.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import Inputs
from algotrade.features.rollups.options.iv30 import OPTIONS, RATES, UNDERLYINGS, by_id
from algotrade.quant.rates import YieldCurve

__all__ = [
    "OPTIONS",
    "UNDERLYINGS",
    "closing_spots",
    "days_to",
    "expiry_days",
    "one_row_per_contract",
    "read_chain",
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


def one_row_per_contract(options: pd.DataFrame) -> pd.DataFrame:
    """``options`` with one row per ``instrument_id`` (the contract): the latest ``ts``, ties
    to the later row. Unchanged (no copy) when no contract repeats."""
    if not options["instrument_id"].duplicated().any():
        return options
    ordered = options.iloc[pd.to_datetime(options["ts"]).argsort(kind="stable").to_numpy()]
    return ordered.drop_duplicates("instrument_id", keep="last").sort_index()


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


def read_chain(inputs: Inputs) -> tuple[YieldCurve, pd.Series, pd.DataFrame, pd.Index]:
    """``(curve, spots, options, ids)`` from the ``chains/option_quotes`` and ``rates/treasury``
    inputs (required) and ``chains/underlying_quotes`` (optional); ``ids`` is every underlying
    quoted or with a chain, sorted, named ``instrument_id``."""
    options, curve_rows = inputs[OPTIONS], inputs[RATES]
    assert options is not None and curve_rows is not None  # required inputs
    curve = YieldCurve.from_days(curve_rows["tenor_days"], curve_rows["rate_cont"])
    underlyings = inputs.get(UNDERLYINGS)
    quoted = set() if underlyings is None else set(underlyings["instrument_id"].astype(str))
    options = one_row_per_contract(options)
    options = options.assign(
        underlying_id=options["underlying_id"].astype(str),
        expiry=pd.to_datetime(options["expiry"]).dt.date,
    )
    ids = pd.Index(sorted(quoted | set(options["underlying_id"])), name="instrument_id")
    return curve, closing_spots(underlyings), options, ids
