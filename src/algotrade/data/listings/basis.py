"""``universe_basis_counts``: the counts behind a run's ``universe_basis`` stamp (ADR 0087 decision
6): how complete the survivorship-free universe was over the window ``[start, end]``. The data
layer only counts; ``services/evaluation`` turns the counts into ``survivors`` | ``free`` against
the thresholds of ``config/site/verdict.toml [universe_basis]``.

What is counted, from the same latest listing snapshot ``universe_asof`` reads and the
``events/delisting`` snapshot written on or before ``as_of`` (``read_delistings``; none stored:
every delisting is unknown):

- ``listings`` / ``no_id``: the in-scope listings alive on some session of the window that
  ADR 0013's rule admits (an ETF, a NASDAQ name, or a stock whose ticker was an S&P 500 member on
  an overlapping interval) and, of those, the ones with no trusted id (not in the universe: the
  survivor tilt the merge could not close). A listing with no start date is never in a window.
- ``stocks`` / ``null_type``: the stock listings among the ones with an id, and those with no
  ``security_type`` (counted as common stocks by the proxy, ADR 0087 decision 3).
- ``merged``: the snapshot is the merged one (it carries ``id_source``).
- ``delisted`` / ``with_bars`` / ``unknown``: the delistings (``delisted_listings``) whose last
  trading day is in the window, those with an ``events/delisting`` row for that day (``with_bars``;
  ``last_close`` is non-null by the table's schema and a name with no bar to its last session has
  no row, so "has bars to its last bar" means "has an event row": a missing row fails closed), and
  those whose delisting return
  has an unknown basis (``ZERO_UNKNOWN``, or no row: a missing event is unknown, never 0).
- ``by_reason`` / ``by_basis``: the matched rows by ``reason`` and ``terminal_basis``, sorted.

Reads ``end_date`` (a vendor's last trading day): identity only, never a feature (the scan in
``tests/architecture/data/test_listing_end_date_readers.py`` allows this folder)."""

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.delistings import ZERO_UNKNOWN, read_delistings
from algotrade.data.listings.membership import SP500
from algotrade.data.listings.membership import TABLE as MEMBERSHIP
from algotrade.data.listings.universe import (
    ETF,
    NASDAQ,
    STOCK,
    delisted_listings,
    listing_frame,
)
from algotrade.data.reference import REFERENCE_HINT, read_snapshot
from algotrade.storage.tables.readers import StoreReader


@dataclass(frozen=True)
class BasisCounts:
    """What ``universe_basis_counts`` found for one window (see the module docstring)."""

    listing_snapshot: date
    delisting_snapshot: date | None  # None: no ``events/delisting`` snapshot stored by ``as_of``
    merged: bool
    listings: int
    no_id: int
    stocks: int
    null_type: int
    delisted: int
    with_bars: int
    unknown: int
    by_reason: dict[str, int] = field(default_factory=dict)
    by_basis: dict[str, int] = field(default_factory=dict)


def _has_id(frame: pd.DataFrame) -> pd.Series:
    return frame["instrument_id"].notna() & (frame["instrument_id"].astype(str) != "")


def _qualifying(frame: pd.DataFrame, members: pd.DataFrame, low: date, high: date) -> pd.DataFrame:
    """The listings alive on some session of ``low..high`` that ADR 0013's rule admits."""
    lo, hi = pd.Timestamp(low), pd.Timestamp(high)
    start, end = pd.to_datetime(frame["start_date"]), pd.to_datetime(frame["end_date"])
    alive = start.notna() & (start <= hi) & (end.isna() | (end >= lo))
    easy = frame["asset_type"].astype(str).str.upper().eq(ETF)
    easy |= frame["exchange"].astype(str).str.upper().eq(NASDAQ)
    span = frame.assign(
        _lo=start.where(start > lo, lo), _hi=end.fillna(hi).where(end.fillna(hi) < hi, hi)
    )[alive & ~easy]
    joined = span.reset_index().merge(
        members.assign(
            _ms=pd.to_datetime(members["start_date"]),
            _me=pd.to_datetime(members["end_date"]).fillna(pd.Timestamp.max),
        )[["ticker", "_ms", "_me"]],
        on="ticker",
        how="inner",
    )
    hit = joined[(joined["_ms"] <= joined["_hi"]) & (joined["_me"] >= joined["_lo"])]
    return frame[alive & (easy | frame.index.isin(hit["index"]))]


def _delisting_counts(
    reader: StoreReader, start: date, end: date, as_of: datetime
) -> tuple[date | None, int, int, int, dict[str, int], dict[str, int]]:
    """``(snapshot, delisted, with_bars, unknown, by_reason, by_basis)`` of the delistings with a
    last trading day in ``start..end`` (known on ``end``, the stamp's window)."""
    gone, _ = delisted_listings(reader, end)
    gone = gone[(gone["last_day"] >= start) & (gone["last_day"] <= end)]
    try:
        events, snap = read_delistings(reader, as_of.date(), as_of)
    except MissingDataError:
        return None, len(gone), 0, len(gone), {}, {}
    key = events.assign(
        _day=pd.to_datetime(events["last_session"]).dt.date,
        _id=events["instrument_id"].astype(str),
    )
    mine = key.merge(
        gone[["instrument_id", "last_day"]].rename(columns={"instrument_id": "_id"}),
        left_on=["_id", "_day"],
        right_on=["_id", "last_day"],
        how="inner",
    ).drop_duplicates(["_id", "_day"])
    bars = mine["last_close"].notna()
    unknown = len(gone) - int((mine["terminal_basis"].ne(ZERO_UNKNOWN) & bars).sum())
    by_reason = {str(k): int(v) for k, v in sorted(mine["reason"].value_counts().items())}
    by_basis = {str(k): int(v) for k, v in sorted(mine["terminal_basis"].value_counts().items())}
    return snap, len(gone), int(bars.sum()), unknown, by_reason, by_basis


def universe_basis_counts(
    reader: StoreReader, start: date, end: date, as_of: datetime
) -> BasisCounts:
    """The counts of the module docstring for the window ``start..end`` (``MissingDataError`` with
    no listing history or membership snapshot); the delisting events are those stored by
    ``as_of``."""
    frame, snap = listing_frame(reader)
    members, _ = read_snapshot(reader, MEMBERSHIP, None, REFERENCE_HINT)
    members = members[members["index_name"] == SP500]
    kept = _qualifying(frame, members, start, end)
    named = kept[_has_id(kept)]
    stock = named[named["asset_type"].astype(str).eq(STOCK)]
    found = _delisting_counts(reader, start, end, as_of)
    merged = bool(frame["id_source"].notna().any())
    return BasisCounts(
        snap.snapshot_date,
        found[0],
        merged,
        len(kept),
        len(kept) - len(named),
        len(stock),
        int(stock["security_type"].isna().sum()),
        found[1],
        found[2],
        found[3],
        found[4],
        found[5],
    )
