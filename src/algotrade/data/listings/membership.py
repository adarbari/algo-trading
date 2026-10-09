"""``instruments/index_membership`` reads: which tickers were in an index on a session (edges
ED6b-3, ADR 0013's S&P 500 rule over history).

The table is a full copy per pull session of the fja05680/sp500 intervals, stamped with the
pull time, so like the listing history it is read as an identity: the **latest snapshot**
whatever the session, and the snapshot is named (``Members.snapshot``, ADR 0036's rule for
snapshot tables). A ticker is a member on S when ``start_date <= S <= end_date`` (a null
``end_date`` is open) for some interval. ``end_date`` is the date the ticker left the index:
used as a feature or label it leaks the future, so only the window test reads it and it is
not returned.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.data.reference import REFERENCE_HINT, read_snapshot
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/index_membership"
SP500 = "SP500"


@dataclass(frozen=True)
class Members:
    """The tickers of ``index_name`` on ``session``, from the membership ``snapshot`` used."""

    index_name: str
    session: date
    snapshot: date
    tickers: frozenset[str]


def members_on(intervals: pd.DataFrame, session: date) -> frozenset[str]:
    """The rule on a frame of ``ticker`` / ``start_date`` / ``end_date`` rows."""
    day = pd.Timestamp(session)
    start = pd.to_datetime(intervals["start_date"])
    end = pd.to_datetime(intervals["end_date"])
    inside = intervals[(start <= day) & (end.isna() | (end >= day))]
    return frozenset(str(t) for t in inside["ticker"])


def index_members(reader: StoreReader, session: date, index_name: str = SP500) -> Members:
    """The tickers of ``index_name`` on ``session`` (``MissingDataError`` with no snapshot)."""
    frame, snap = read_snapshot(reader, TABLE, None, REFERENCE_HINT)
    mine = frame[frame["index_name"] == index_name]
    return Members(index_name, session, snap.snapshot_date, members_on(mine, session))
