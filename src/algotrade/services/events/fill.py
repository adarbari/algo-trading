"""The order in which a budgeted history backfill takes names, as of a session (ADR 0050).

``fill_order`` ranks every ticker of the session's reference snapshot by how useful its history
is to the event study, so a vendor with a monthly symbol cap (Tiingo's free tier) covers the
most useful names first and, month after month, the whole optionable universe:

1. optionable names first (a row in ``option_liquidity@v1``: the nightly found a chain to grade),
2. then ``iv_history@v2.iv30`` descending (the more volatile the name, the more its events move it),
3. then ``price_stats@v2.adv_usd_20d`` descending (the more liquid, the more it matters),
4. then the symbol, so the order is the same on every run.

Every rollup is read through ``data.rollups.rollup_as_of`` (the newest partition on or before the
session, never a later one); a name a rollup does not hold, or a rollup that is not stored, ranks
last on that key. Choosing which of the names still lack history is the caller's (it knows what
earlier runs fetched). Read-only.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.fields import rollup_table
from algotrade.data import StoreReader
from algotrade.data.reference import resolver
from algotrade.data.rollups import rollup_as_of
from algotrade.services.events.scope import LIQUIDITY

IV_HISTORY = rollup_table("instrument", "iv_history@v2")
PRICE_STATS = rollup_table("instrument", "price_stats@v2")


@dataclass(frozen=True)
class FillCandidate:
    """One ticker of the universe with the keys it is ranked by (``None``: not stored)."""

    instrument_id: str
    symbol: str
    optionable: bool
    iv30: float | None
    adv_usd_20d: float | None


def _column(reader: StoreReader, table: str, column: str, session: date) -> dict[str, float]:
    """``column`` of ``table`` as of ``session`` by instrument (missing values left out)."""
    found = rollup_as_of(reader, table, session)
    if found is None or column not in found[1].columns:
        return {}
    rows = found[1][["instrument_id", column]].dropna()
    return dict(zip(rows["instrument_id"].astype(str), rows[column].astype(float), strict=True))


def _optionable(reader: StoreReader, session: date) -> set[str]:
    found = rollup_as_of(reader, LIQUIDITY, session)
    return set() if found is None else set(found[1]["instrument_id"].astype(str))


def _rank(value: float | None) -> float:
    """Descending order as an ascending key; a missing value last."""
    return float("inf") if value is None or pd.isna(value) else -value


def fill_order(reader: StoreReader, session: date) -> list[FillCandidate]:
    """Every ticker of the reference snapshot as of ``session``, most useful first."""
    symbols = resolver(reader, session).symbols
    optionable = _optionable(reader, session)
    iv30 = _column(reader, IV_HISTORY, "iv30", session)
    adv = _column(reader, PRICE_STATS, "adv_usd_20d", session)
    found = [
        FillCandidate(i, str(s), i in optionable, iv30.get(i), adv.get(i))
        for i, s in symbols.items()
        if str(s).strip()
    ]
    return sorted(
        found,
        key=lambda c: (
            not c.optionable,
            _rank(c.iv30),
            _rank(c.adv_usd_20d),
            c.symbol,
            c.instrument_id,
        ),
    )
