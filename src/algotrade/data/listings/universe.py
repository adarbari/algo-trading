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
``SymbolResolver.from_listings`` (both identity reads: is this listing alive on S), by
``read_listings`` for the winners-sample runner** (which picks its strata by year of delisting,
by design: a data-quality sample, never a feature), by ``delisted_by`` for the outcomes task
(a name counts as delisted at T only when ``end_date <= T``, so no later delisting is known) and
by ``listings_over`` for ``bars-history --from-listings`` (which fetches a listing's bars by its
permaTicker and clips them to its own dates: identity, never a feature), nowhere else
(``tests/architecture/data/test_listing_end_date_readers.py`` scans for it), and
``universe_asof`` does not return it. The adapter stores a live name's end as null (open).

**Every read of the table goes through ``listing_frame``** (ADR 0087): the table holds every
vendor row, the ones outside the universe's scope (``scope_reason`` set: an OTC successor, a
duplicate start...) are stored and never read, and a partition written before the merge lacks the
columns it added (a single-partition read does not add absent columns), which read as null; an
absent ``scope_reason`` means every row is in scope. A row with no ``start_date`` (a Massive-only
record whose start no Tiingo row gives) is never in a window: it is counted in
``Universe.undated`` when it may be alive on S, so the run stamp can say how much is missing.
``Universe.null_type`` counts the Stock names returned with no ``security_type``;
``Universe.duplicate_id`` the listings of an id already returned (alive on S together), dropped.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.listings.membership import SP500, index_members
from algotrade.data.listings.membership import TABLE as MEMBERSHIP
from algotrade.data.reference import REFERENCE_HINT, Snapshot, read_snapshot
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/listing_history"
COLUMNS = ["instrument_id", "ticker", "exchange", "asset_type", "start_date", "security_type"]
# The columns ADR 0087 added to the table: an older partition reads them as null.
ADDED_COLUMNS = (
    "name", "vendor_type", "security_type", "cik", "figi", "share_class_figi", "vendor_exchange",
    "data_provider_perma_ticker", "id_source", "no_id_reason", "scope_reason", "vendor_end_date",
    "is_adr",
)  # fmt: skip
NASDAQ = "NASDAQ"
ETF = "ETF"
STOCK = "Stock"
TIINGO = "tiingo"


@dataclass(frozen=True)
class Universe:
    """The names listed on a session. ``snapshot`` is the listing snapshot used (the latest);
    ``without_id`` counts listings in the window that have no trusted id yet (not returned);
    ``undated`` the listings with no start date that may be alive on the session (not returned:
    possibly in the universe, never known to be); ``null_type`` the Stock names returned with no
    ``security_type``."""

    session: date
    snapshot: date
    instruments: pd.DataFrame  # ``COLUMNS``; never ``end_date``
    without_id: int = 0
    membership_snapshot: date | None = None  # the S&P 500 membership snapshot used
    undated: int = 0
    null_type: int = 0
    duplicate_id: int = 0  # listings of an id already returned, alive on the session (dropped)


def conform_listings(frame: pd.DataFrame) -> pd.DataFrame:
    """The rows in scope (``scope_reason`` null or absent), with every column ADR 0087 added
    present (null where the partition predates it)."""
    out = frame.reindex(columns=[*frame.columns, *(c for c in ADDED_COLUMNS if c not in frame)])
    return out[out["scope_reason"].isna()].reset_index(drop=True)


def listing_frame(reader: StoreReader) -> tuple[pd.DataFrame, Snapshot]:
    """The rows in scope of the latest ``instruments/listing_history`` snapshot, ``end_date``
    included, and the snapshot: the one way the table is read (see the module docstring)."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    return conform_listings(frame), snap


def listed_asof(listings: pd.DataFrame, session: date, sp500_tickers: Collection[str]) -> Universe:
    """The rule on a frame of listing rows (``snapshot`` is filled by ``universe_asof``)."""
    day = pd.Timestamp(session)
    if "security_type" not in listings:
        listings = listings.assign(security_type=None)
    start = pd.to_datetime(listings["start_date"])
    end = pd.to_datetime(listings["end_date"])
    window = listings[(start <= day) & (end.isna() | (end >= day))]
    undated = int((start.isna() & (end.isna() | (end >= day))).sum())
    has_id = window["instrument_id"].notna() & (window["instrument_id"].astype(str) != "")
    usable = window[has_id]
    is_etf = usable["asset_type"].astype(str).str.upper().eq(ETF)
    nasdaq = usable["exchange"].astype(str).str.upper().eq(NASDAQ)
    member = usable["ticker"].astype(str).isin(set(sp500_tickers))
    kept = usable[is_etf | nasdaq | member]
    out = kept[COLUMNS].sort_values(["ticker", "start_date"], kind="stable")
    # One row per instrument: two listings of one id alive on S would count a name twice (the
    # first by ticker stays; the merge keeps it from happening, this keeps a read honest).
    twice = out["instrument_id"].duplicated()
    out = out[~twice].reset_index(drop=True)
    stock = out["asset_type"].astype(str).eq(STOCK)
    return Universe(
        session, session, out, int((~has_id).sum()), undated=undated,
        null_type=int((stock & out["security_type"].isna()).sum()), duplicate_id=int(twice.sum()),
    )  # fmt: skip


def universe_asof(reader: StoreReader, session: date) -> Universe:
    """The universe on ``session`` from the latest ``instruments/listing_history`` snapshot and
    the latest S&P 500 membership snapshot (both named in the result)."""
    frame, snap = listing_frame(reader)
    members = index_members(reader, session)
    found = listed_asof(frame, session, members.tickers)
    return Universe(
        session, snap.snapshot_date, found.instruments, found.without_id, members.snapshot,
        found.undated, found.null_type, found.duplicate_id,
    )  # fmt: skip


def listings_over(reader: StoreReader, since: date, until: date) -> tuple[pd.DataFrame, date]:
    """The listings that are in the universe on ANY session of ``since..until`` (exactly: a
    listing's dates clipped to the window, and for a stock that is neither on NASDAQ nor an ETF a
    S&P 500 interval of its ticker overlapping them) and the listing snapshot used. Columns:
    ``instrument_id``, ``ticker``, ``perma_ticker`` (``""`` when unknown), ``start_date``,
    ``end_date`` (null while open) and ``reused`` (another listing of the snapshot has the same
    ticker). A listing with no start date is never in a window. For the bars backfill only (see
    the module docstring)."""
    frame, snap = listing_frame(reader)
    members, _ = read_snapshot(reader, MEMBERSHIP, None, REFERENCE_HINT)
    members = members[members["index_name"] == SP500]
    tickers = frame["ticker"].astype(str)
    out = frame.assign(
        reused=tickers.map(tickers.value_counts()).gt(1),
        perma_ticker=frame["perma_ticker"].fillna("").astype(str),
        start_date=pd.to_datetime(frame["start_date"]),
        end_date=pd.to_datetime(frame["end_date"]),
    )
    low, high = pd.Timestamp(since), pd.Timestamp(until)
    lo = out["start_date"].where(out["start_date"] > low, low)
    hi = out["end_date"].fillna(high).where(out["end_date"].fillna(high) < high, high)
    has_id = out["instrument_id"].notna() & (out["instrument_id"].astype(str) != "")
    alive = has_id & out["start_date"].notna() & (lo <= hi)
    easy = out["asset_type"].astype(str).str.upper().eq(ETF)
    easy |= out["exchange"].astype(str).str.upper().eq(NASDAQ)
    joined = (
        out.assign(_lo=lo, _hi=hi)
        .reset_index()
        .merge(
            members.assign(
                _ms=pd.to_datetime(members["start_date"]),
                _me=pd.to_datetime(members["end_date"]).fillna(pd.Timestamp.max),
            )[["ticker", "_ms", "_me"]],
            on="ticker",
            how="inner",
        )
    )
    overlapping = joined[(joined["_ms"] <= joined["_hi"]) & (joined["_me"] >= joined["_lo"])]
    member = out.index.isin(overlapping["index"])
    kept = out[alive & (easy | member)].drop_duplicates("instrument_id")
    kept = kept.assign(
        start_date=kept["start_date"].dt.date,
        end_date=kept["end_date"].dt.date.where(kept["end_date"].notna(), None),
    )
    cols = ["instrument_id", "ticker", "perma_ticker", "start_date", "end_date", "reused"]
    return kept[cols].sort_values(["ticker", "start_date"]).reset_index(
        drop=True
    ), snap.snapshot_date


def read_listings(reader: StoreReader) -> tuple[pd.DataFrame, date]:
    """The Tiingo rows in scope of the latest ``instruments/listing_history`` snapshot,
    ``end_date`` included, and that snapshot's date (Massive's rows are left out so the winners
    sample, seeded on this frame, stays reproducible). For the winners-sample runner only (see
    the module docstring)."""
    frame, snap = listing_frame(reader)
    return frame[frame["source"].eq(TIINGO)].reset_index(drop=True), snap.snapshot_date


def delisted_by(reader: StoreReader, session: date) -> dict[str, date]:
    """Instrument id -> last trading day, for the listings with a trusted id whose ``end_date``
    is on or before ``session`` (``MissingDataError`` with no snapshot). A listing that ends
    after ``session``, or is open, is absent: at ``session`` its delisting was not known. For
    the outcomes task (a window ending at ``session`` marks a name with no bar at its end
    DELISTED)."""
    frame, _ = listing_frame(reader)
    has_id = frame["instrument_id"].notna() & (frame["instrument_id"].astype(str) != "")
    rows = frame[has_id]
    # An id several listings share (a ticker change) is delisted only once every one has ended.
    ends = pd.to_datetime(rows["end_date"]).groupby(rows["instrument_id"].astype(str))
    stats = ends.agg(["count", "size", "max"])
    gone = stats[(stats["count"] == stats["size"]) & (stats["max"] <= pd.Timestamp(session))]
    return {str(i): last.date() for i, last in gone["max"].items()}
