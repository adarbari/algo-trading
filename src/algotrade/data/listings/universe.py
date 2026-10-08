"""``universe_asof``: which listed stocks and ETFs existed on a session (edges ED6, ADR 0013).

The listing history is a full copy per pull session, stamped with its pull time (2026 for a
name listed in 2010), so the read takes the **latest snapshot** whatever the session and says
which (``Universe.snapshot``, ADR 0036's rule for snapshot tables). That is the identity
exception: the table says *what was listed*, never what was known on S. Do not read it for
anything else on an old S.

A listing is in when ``start_date <= S <= end_date`` (a null ``end_date`` is open), it has a
trusted ``instrument_id``, and, for a stock, ADR 0013's rule holds at S: it was an S&P 500
member at S (``sp500_members``, ids; the history comes with ED6b-3) or its exchange is
NASDAQ. ETFs are all in.

``end_date`` is the vendor's last trading day, which exists only for names that have since
delisted: used as a feature, label or sort key it leaks the future. It is read **here and
only here**, to test membership at S, and is not returned.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.reference import REFERENCE_HINT, read_snapshot
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/listing_history"
COLUMNS = ["instrument_id", "ticker", "exchange", "asset_type", "start_date"]
NASDAQ = "NASDAQ"
ETF = "ETF"


@dataclass(frozen=True)
class Universe:
    """The names listed on a session. ``snapshot`` is the listing snapshot used (the latest);
    ``without_id`` counts listings in the window that have no trusted id yet (not returned)."""

    session: date
    snapshot: date
    instruments: pd.DataFrame  # ``COLUMNS``; never ``end_date``
    without_id: int = 0


def listed_asof(listings: pd.DataFrame, session: date, sp500_members: Collection[str]) -> Universe:
    """The rule on a frame of listing rows (``snapshot`` is filled by ``universe_asof``)."""
    start = pd.to_datetime(listings["start_date"]).dt.date
    end = pd.to_datetime(listings["end_date"]).dt.date
    window = listings[(start <= session) & (end.isna() | (end >= session))]
    has_id = window["instrument_id"].notna() & (window["instrument_id"].astype(str) != "")
    usable = window[has_id]
    is_etf = usable["asset_type"].astype(str).str.upper().eq(ETF)
    nasdaq = usable["exchange"].astype(str).str.upper().eq(NASDAQ)
    member = usable["instrument_id"].astype(str).isin(set(sp500_members))
    kept = usable[is_etf | nasdaq | member]
    out = kept[COLUMNS].sort_values(["ticker", "start_date"], kind="stable")
    return Universe(session, session, out.reset_index(drop=True), int((~has_id).sum()))


def universe_asof(reader: StoreReader, session: date, sp500_members: Collection[str]) -> Universe:
    """The universe on ``session`` from the latest ``instruments/listing_history`` snapshot.
    ``sp500_members``: instrument ids that were S&P 500 members on ``session`` (a parameter
    until ED6b-3 provides the history; no default, so a caller cannot forget it)."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    found = listed_asof(frame, session, sp500_members)
    return Universe(session, snap.snapshot_date, found.instruments, found.without_id)
