"""The order the FMP rotation takes its due names in: market capitalisation, largest first.

The free FMP plan is gated by symbol and covers mostly mega and large caps, while a refused name
still costs a call (measured 2026-10-22), so the names that can answer are asked first and the
refusals last. The cap is shares outstanding x close from the newest roll-ups on or before the
session (read through ``algotrade.data.rollups``, as ``tasks/reference/shares.py`` does); a name
without one goes last; ties keep the order given (``due_keys``: new names by symbol, then the
stalest), so the order is deterministic and an unknown cap does not undo the rotation.
"""

from collections.abc import Iterable, Mapping
from datetime import date

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.rollups import rollup_as_of

FUNDAMENTALS = "rollups/instrument/fundamentals@v5"
PRICE_STATS = "rollups/instrument/price_stats@v2"


def market_caps(reader: StoreReader, session: date) -> dict[str, float]:
    """``instrument_id`` -> shares outstanding x close, from the roll-ups as of ``session``;
    an id missing either input is absent."""
    stats = rollup_as_of(reader, PRICE_STATS, session)
    shares = rollup_as_of(reader, FUNDAMENTALS, session)
    if stats is None or shares is None:
        return {}
    close, count = stats[1], shares[1]
    if "close" not in close.columns or "shares_outstanding" not in count.columns:
        return {}
    price = close.set_index(close["instrument_id"].astype(str))["close"]
    held = count.set_index(count["instrument_id"].astype(str))["shares_outstanding"]
    product = (held * price).dropna()
    return {str(i): float(v) for i, v in product.items()}


def by_market_cap(
    symbols: Iterable[str], id_of: Mapping[str, str], caps: Mapping[str, float]
) -> list[str]:
    """``symbols`` largest cap first; no cap last; ties keep their order (the sort is stable)."""

    def key(symbol: str) -> tuple[bool, float]:
        cap = caps.get(id_of[symbol])
        if cap is None or pd.isna(cap):
            return (True, 0.0)
        return (False, -cap)

    return sorted(symbols, key=key)
