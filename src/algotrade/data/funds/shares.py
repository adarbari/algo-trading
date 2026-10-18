"""ETF shares outstanding (``holdings/etf_shares``, EB D4): the issuer's daily count per fund.

One row per fund and issuer as-of date, written by the ``etf-holdings`` task from the iShares
file it already reads. A reader on session ``S`` sees only what was knowable then: rows with
``known_from <= S`` (the first session the count could have been known, ADR 0050; the file's
``as_of`` is not it: issuers publish the same evening or next morning). A file read again for
an ``as_of`` leaves a second row with a later ``known_from``; a reader keeps the latest row it
may see (``known_from <= S``), so a restated count is seen from the session it was fetched.
Flows are not stored: the change in shares times the stored close approximates them.

``share_versions`` is the feature input's read (``data/feature_inputs.py``): every stored row of
every fund with ``known_from <= through``, restated versions side by side, so the input can hand a
session the rows it knew and a compute keep the latest version of each (fund, ``as_of``).
"""

from collections.abc import Collection
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

TABLE = "holdings/etf_shares"
COLUMNS = ("instrument_id", "as_of", "shares_outstanding", "known_from", "source")


def etf_shares(
    reader: StoreReader,
    instrument_ids: Collection[str],
    since: date,
    on: date,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The shares outstanding of ``instrument_ids`` known on session ``on`` for issuer dates from
    ``since`` (``COLUMNS``, by fund then ``as_of``); an empty frame when none are stored."""
    empty = pd.DataFrame({c: [] for c in COLUMNS})
    if not instrument_ids:
        return empty
    frame = reader.table_range(TABLE, since, on, as_of, sorted(instrument_ids))
    if frame is None or frame.empty:
        return empty
    frame = frame.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"]).dt.date
    frame["known_from"] = pd.to_datetime(frame["known_from"]).dt.date
    frame = frame[(frame["known_from"] <= on) & (frame["as_of"] >= since)]
    latest = frame.sort_values(["known_from", "knowledge_ts", "run_id"], kind="stable")
    latest = latest.drop_duplicates(["instrument_id", "as_of"], keep="last")
    out = latest.reindex(columns=list(COLUMNS))
    return out.sort_values(["instrument_id", "as_of"], kind="stable").reset_index(drop=True)


def share_versions(reader: StoreReader, through: date) -> pd.DataFrame:
    """Every stored row (every version) of every fund known on or before ``through``
    (``COLUMNS`` plus ``knowledge_ts``), sorted by ``known_from`` then fund and ``as_of``; empty
    when none is stored. A version restated later sits beside the one it replaces: the reader of
    a session keeps the latest with ``known_from <= session``."""
    keep = [*COLUMNS, "knowledge_ts"]
    frame = reader.table_range(TABLE, date(1900, 1, 1), date(9999, 12, 31))
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in keep})
    frame = frame.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"]).dt.date
    frame["known_from"] = pd.to_datetime(frame["known_from"]).dt.date
    frame = frame[frame["known_from"] <= through]
    out = frame.reindex(columns=keep)
    return out.sort_values(["known_from", "instrument_id", "as_of"], kind="stable").reset_index(
        drop=True
    )
