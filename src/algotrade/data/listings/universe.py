"""``universe_asof``: which listed stocks and ETFs existed on a session (edges ED6, ADR 0013).

The listing history is a full copy per pull session, stamped with its pull time (2026 for a
name listed in 2010), so the read takes the **latest snapshot** whatever the session and says
which (``Universe.snapshot``, ADR 0036's rule for snapshot tables). That is the identity
exception: the table says *what was listed*, never what was known on S. Do not read it for
anything else on an old S.

A listing is in when ``start_date <= S <= end_date`` (a null ``end_date`` is open), it has a
trusted ``instrument_id``, and, for a stock, ADR 0013's rule holds at S: it was an S&P 500
member at S (its ticker is in ``data.listings.membership``'s S&P 500 intervals on S; the
listing alive on S is the one that ticker names) or its exchange is NASDAQ. ETFs are all in.
Both snapshots used are named (``Universe.snapshot``, ``Universe.membership_snapshot``).

``end_date`` is the vendor's last trading day, which exists only for names that have since
delisted: used as a feature, label or sort key it leaks the future. It is read **here, in
``SymbolResolver.from_listings`` (both identity reads: is this listing alive on S) and by
``read_listings`` for the winners-sample runner** (which picks its strata by year of delisting,
by design: a data-quality sample, never a feature) and ``listings_over`` for ``bars-history
--from-listings`` (which fetches a listing's bars by its permaTicker and clips them to its own
dates: identity, never a feature), nowhere else, and ``universe_asof`` does not return it. The
adapter stores a live name's end as null (open).
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.listings.membership import index_members
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
    membership_snapshot: date | None = None  # the S&P 500 membership snapshot used


def listed_asof(listings: pd.DataFrame, session: date, sp500_tickers: Collection[str]) -> Universe:
    """The rule on a frame of listing rows (``snapshot`` is filled by ``universe_asof``)."""
    day = pd.Timestamp(session)
    start = pd.to_datetime(listings["start_date"])
    end = pd.to_datetime(listings["end_date"])
    window = listings[(start <= day) & (end.isna() | (end >= day))]
    has_id = window["instrument_id"].notna() & (window["instrument_id"].astype(str) != "")
    usable = window[has_id]
    is_etf = usable["asset_type"].astype(str).str.upper().eq(ETF)
    nasdaq = usable["exchange"].astype(str).str.upper().eq(NASDAQ)
    member = usable["ticker"].astype(str).isin(set(sp500_tickers))
    kept = usable[is_etf | nasdaq | member]
    out = kept[COLUMNS].sort_values(["ticker", "start_date"], kind="stable")
    return Universe(session, session, out.reset_index(drop=True), int((~has_id).sum()))


def universe_asof(reader: StoreReader, session: date) -> Universe:
    """The universe on ``session`` from the latest ``instruments/listing_history`` snapshot and
    the latest S&P 500 membership snapshot (both named in the result)."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    members = index_members(reader, session)
    found = listed_asof(frame, session, members.tickers)
    return Universe(
        session, snap.snapshot_date, found.instruments, found.without_id, members.snapshot
    )


def listings_over(reader: StoreReader, since: date, until: date) -> tuple[pd.DataFrame, date]:
    """The listings that are in the universe on any sampled session of ``since..until`` (the two
    ends and the first day of each month between: a listing alive for less than a month between
    samples can be missed) and the listing snapshot used. Columns: ``instrument_id``, ``ticker``,
    ``perma_ticker`` (``""`` when unknown), ``start_date``, ``end_date`` (null while open) and
    ``reused`` (another listing of the snapshot has the same ticker). For the bars backfill only
    (see the module docstring)."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    days = {since, until}
    month = date(since.year, since.month, 1)
    while month <= until:
        if month >= since:
            days.add(month)
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    ids: set[str] = set()
    for day in sorted(days):
        found = listed_asof(frame, day, index_members(reader, day).tickers)
        ids |= set(found.instruments["instrument_id"])
    tickers = frame["ticker"].astype(str)
    out = frame.assign(reused=tickers.map(tickers.value_counts()).gt(1))
    out = out[out["instrument_id"].isin(ids)].drop_duplicates("instrument_id")
    out = out.assign(
        perma_ticker=out["perma_ticker"].fillna("").astype(str),
        start_date=pd.to_datetime(out["start_date"]).dt.date,
        end_date=pd.to_datetime(out["end_date"]).dt.date.where(out["end_date"].notna(), None),
    )
    cols = ["instrument_id", "ticker", "perma_ticker", "start_date", "end_date", "reused"]
    return out[cols].sort_values(["ticker", "start_date"]).reset_index(
        drop=True
    ), snap.snapshot_date


def read_listings(reader: StoreReader) -> tuple[pd.DataFrame, date]:
    """Every row of the latest ``instruments/listing_history`` snapshot, ``end_date`` included,
    and that snapshot's date. For the winners-sample runner only (see the module docstring)."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    return frame, snap.snapshot_date
