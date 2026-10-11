"""``listing_tickers``: the ticker a listing carried on a session, from the listing history, for a
name no reference snapshot ever held (a delisted pick of an edge's ledger, ``EQ:TIINGO:<perma>``).

The listing history is one full copy per pull session, so the read takes its latest snapshot (the
identity exception of ``universe``): what a listing was CALLED. Point in time is kept by the
dates, not the snapshot: a ticker is offered for a session only from the listing's own
``start_date`` (the latest listing row of the id that started on or before it); a name listed
after the session has none (never a later ticker). The vendor's ``end_date`` is not read (a
delisted name keeps its last ticker for every session it was listed). Read once per snapshot
by the caller's cache, never per row."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.listings.universe import TABLE
from algotrade.data.reference import REFERENCE_HINT, read_snapshot
from algotrade.storage.tables.readers import StoreReader


@dataclass(frozen=True)
class ListingTickers:
    """Every trusted-id listing's tickers by ``instrument_id``, oldest start first, and the
    listing ``snapshot`` they were read from."""

    snapshot: date
    by_id: dict[str, tuple[tuple[date, str], ...]]

    def on(self, instrument_id: str, session: date) -> str | None:
        """The ticker of ``instrument_id`` on ``session``: the latest listing row that started on
        or before it (None: no such row, or the name was not yet listed)."""
        found = [t for start, t in self.by_id.get(instrument_id, ()) if start <= session]
        return found[-1] if found else None


def listing_tickers(reader: StoreReader) -> ListingTickers:
    """The tickers of every listing with a trusted id in the latest listing snapshot."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    ids = frame["instrument_id"].notna() & (frame["instrument_id"].astype(str) != "")
    kept = frame[ids]
    starts = pd.to_datetime(kept["start_date"]).dt.date
    rows = sorted(
        zip(kept["instrument_id"].astype(str), starts, kept["ticker"].astype(str), strict=True),
        key=lambda r: (r[0], r[1]),
    )
    by_id: dict[str, list[tuple[date, str]]] = {}
    for iid, start, ticker in rows:
        by_id.setdefault(iid, []).append((start, ticker))
    return ListingTickers(snap.snapshot_date, {i: tuple(v) for i, v in by_id.items()})
