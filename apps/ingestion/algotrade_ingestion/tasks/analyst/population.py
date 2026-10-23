"""The names the analyst tasks may ask Yahoo about: the stock population of the reference.

``analyst-snapshot`` asks FMP and Finnhub about the S&P 500 plus the event-study scope list
(``snapshot.scope_names``); Yahoo, which has no daily budget and covers the small and mid caps FMP's
free plan refuses, is asked about every operating company the universe holds: the reference
snapshot's ``COMMON_STOCK`` and ``ADR`` rows (``universe.toml security_types``; ETFs and closed-end
funds have no analyst consensus, Yahoo answers 404). One reader of that population, so the nightly's
Yahoo step and the one-off ``analyst-backfill`` agree on it (ADR 0080 amendment 2026-10-23b).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.reference import instruments

TYPES = ("COMMON_STOCK", "ADR")  # the security types that report earnings and have analysts


@dataclass(frozen=True)
class Name:
    instrument_id: str
    symbol: str


def listed_names(reader: StoreReader, session: date) -> list[Name]:
    """The ``COMMON_STOCK`` and ``ADR`` rows of the reference snapshot for ``session``, by symbol
    (a row without a symbol is left out)."""
    reference = instruments(reader, session)
    if "security_type" not in reference.columns:
        return []
    held = reference[reference["security_type"].isin(TYPES)]
    found = {
        str(i): str(s)
        for i, s in zip(held["instrument_id"], held["symbol"], strict=False)
        if pd.notna(s) and isinstance(s, str) and s
    }
    return sorted((Name(i, s) for i, s in found.items()), key=lambda n: (n.symbol, n.instrument_id))
