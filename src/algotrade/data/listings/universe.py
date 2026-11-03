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
by design: a data-quality sample, never a feature), by ``delisted_listings`` / ``delisted_by`` for
the delistings and outcomes tasks (a name counts as delisted at T only when ``end_date <= T``, so
no later delisting is known) and by ``listings_over`` for ``bars-history --from-listings`` (which
fetches a listing's bars by its permaTicker and clips them to its own dates: identity, never a
feature), nowhere else
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
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.core.time.calendar import sessions_between
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
    out = kept[COLUMNS].sort_values("start_date", kind="stable")
    # One row per instrument: two listings of one id alive on S would count a name twice (the
    # latest start stays, as in ``SymbolResolver.from_listings``; the merge keeps it from
    # happening, this keeps a read honest).
    twice = out["instrument_id"].duplicated(keep="last")
    out = out[~twice].sort_values(["ticker", "start_date"], kind="stable").reset_index(drop=True)
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


def _one_row_per_listing(kept: pd.DataFrame) -> pd.DataFrame:
    """One row per instrument for ``listings_over`` (datetime ``start_date`` / ``end_date``). The
    listings of one permaTicker under one id (a ticker change: one company, listed in turn) are
    one row spanning them all: the earliest start, the latest end (null if any is open), the
    ticker of the latest start, ``reused`` if any is. Any other id keeps its first row."""
    cols = ["instrument_id", "ticker", "perma_ticker", "start_date", "end_date", "reused"]
    named = kept["perma_ticker"] != ""
    rows = kept[named].sort_values("start_date", kind="stable")
    keys = ["instrument_id", "perma_ticker"]
    groups = rows.groupby(keys, sort=False)
    span = pd.DataFrame(
        {
            "_start": groups["start_date"].min(),
            "_end": groups["end_date"].apply(lambda s: pd.NaT if s.isna().any() else s.max()),
            "_reused": groups["reused"].max(),
        }
    )
    latest = groups.tail(1).set_index(keys).join(span).reset_index()
    latest = latest.assign(
        start_date=latest["_start"], end_date=latest["_end"], reused=latest["_reused"]
    )
    both = pd.concat([latest[cols], kept[~named][cols]], ignore_index=True)
    return both.drop_duplicates("instrument_id")


def listings_over(reader: StoreReader, since: date, until: date) -> tuple[pd.DataFrame, date]:
    """The listings that are in the universe on ANY session of ``since..until`` (exactly: a
    listing's dates clipped to the window, and for a stock that is neither on NASDAQ nor an ETF a
    S&P 500 interval of its ticker overlapping them) and the listing snapshot used. Columns:
    ``instrument_id``, ``ticker``, ``perma_ticker`` (``""`` when unknown), ``start_date``,
    ``end_date`` (null while open) and ``reused`` (another listing of the snapshot has the same
    ticker). The listings of one id and one permaTicker are one row spanning them (a ticker
    change's bars are one series). A listing with no start date is never in a window. For the
    bars backfill only (see the module docstring)."""
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
    kept = _one_row_per_listing(out[alive & (easy | member)])
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


RELIST_GAP_SESSIONS = (
    10  # a next listing of the same id this many sessions later is a ticker change
)


def _gap_ends(rows: pd.DataFrame) -> pd.Series:
    """Per row: the first day a next listing of the id may start for the gap to be a real one (the
    ``RELIST_GAP_SESSIONS``-th session after the row's end), null where the row has no end."""
    ends = rows["last_day"].dropna().drop_duplicates()
    sessions = {
        e: pd.Timestamp(sessions_between(e.date() + timedelta(1), e.date() + timedelta(30))[
            RELIST_GAP_SESSIONS - 1])
        for e in ends
    }  # fmt: skip
    return rows["last_day"].map(sessions)


def _start_after_end(rows: pd.DataFrame) -> pd.Series:
    """Per row: the first start among the id's listings strictly after the row's end (null when
    none, or the row is open): the relisting a stretch-ending row is compared with, never a
    listing nested inside the stretch."""
    starts = {i: g.sort_values().to_numpy() for i, g in rows.groupby("instrument_id")["first_day"]}
    out: list[Any] = []
    for iid, end in zip(rows["instrument_id"], rows["last_day"], strict=True):
        later = starts[iid]
        k = later.searchsorted(end.to_datetime64(), side="right") if pd.notna(end) else len(later)
        out.append(pd.Timestamp(later[k]) if k < len(later) else pd.NaT)
    return pd.Series(pd.DatetimeIndex(out), index=rows.index)


def delisted_listings(reader: StoreReader, session: date) -> tuple[pd.DataFrame, date]:
    """One row per delisting of an instrument id (with a trusted id) known on ``session``
    (``MissingDataError`` with no snapshot), and the listing snapshot read: ``instrument_id``,
    ``last_day`` (the vendor's last trading day of that stretch), ``exchange`` and
    ``security_type`` of the listing that ended (its final venue and type), ``cik`` (the latest
    non-null one of the id's listings up to it), ``final`` (the id's last listing: every listing
    of the id has ended), sorted by id and day.

    An id's ended listing is a delisting when it is the last (``final``: every listing of the id
    has ended on or before ``session``) or when the id's next listing starts more than
    ``RELIST_GAP_SESSIONS`` sessions after it (a delisted name that relisted: a real gap, not a
    ticker change). A listing that ends after ``session``, or is open, is not a delisting yet; a
    listing that starts after ``session`` is not yet known."""
    frame, snap = listing_frame(reader)
    has_id = frame["instrument_id"].notna() & (frame["instrument_id"].astype(str) != "")
    started = pd.to_datetime(frame["start_date"]) <= pd.Timestamp(session)
    rows = frame[has_id & started].assign(
        instrument_id=lambda f: f["instrument_id"].astype(str),
        last_day=lambda f: pd.to_datetime(f["end_date"]),
        first_day=lambda f: pd.to_datetime(f["start_date"]),
    )
    rows = rows.sort_values(["instrument_id", "first_day", "last_day"], kind="stable")
    rows = rows.reset_index(drop=True)
    by_id = rows.groupby("instrument_id")
    rows["cik"] = by_id["cik"].ffill()
    rows["cik"] = rows.groupby("instrument_id")["cik"].bfill()
    # An open listing reaches forever; a listing nested in an earlier one's span (A 2000-2010, B
    # 2001-2005) never ends the id's stretch: only a row whose end is the running maximum does.
    reach = rows["last_day"].fillna(pd.Timestamp.max).groupby(rows["instrument_id"]).cummax()
    ended = rows["last_day"] <= pd.Timestamp(session)
    stretch_end = ended & (rows["last_day"] == reach)
    open_ids = rows.loc[rows["last_day"].isna(), "instrument_id"].unique()
    ended_on = rows["last_day"].fillna(pd.Timestamp.min)
    latest = ended_on.groupby(rows["instrument_id"]).idxmax()  # the listing that ended last
    final = rows.index.isin(latest[~latest.index.isin(open_ids)]) & ended
    after = _start_after_end(rows)  # the next listing starting after a stretch's end
    real_gap = stretch_end & (after > _gap_ends(rows))
    rows = rows.assign(final=final)[final | real_gap]
    out = rows[["instrument_id", "last_day", "exchange", "security_type", "cik", "final"]]
    out = out.assign(last_day=[d.date() for d in out["last_day"]])
    return out.sort_values(["instrument_id", "last_day"], kind="stable").reset_index(drop=True), (
        snap.snapshot_date
    )


def delisted_by(reader: StoreReader, session: date) -> dict[str, date]:
    """Instrument id -> last trading day, for the ids whose every listing has ended on or before
    ``session`` (the ``final`` rows of ``delisted_listings``; an id that relisted and is open
    again is absent). For the outcomes task (a window ending at ``session`` marks a name with no
    bar at its end DELISTED)."""
    gone, _ = delisted_listings(reader, session)
    final = gone[gone["final"]]
    return dict(zip(final["instrument_id"], final["last_day"], strict=True))
