"""ETF shares outstanding (``holdings/etf_shares``, EB D4): the issuer's daily count per fund.

One row per fund and issuer as-of date, written by the ``etf-holdings`` task from the iShares
file it already reads. A reader on session ``S`` sees only what was knowable then: rows with
``known_from <= S`` (the first session the count could have been known, ADR 0050; the file's
``as_of`` is not it: issuers publish the same evening or next morning). A file read again for
an ``as_of`` leaves a second row with a later ``known_from``; a reader keeps the latest row it
may see (``known_from <= S``), so a restated count is seen from the session it was fetched.
Flows are not stored: the change in shares times the stored close approximates them.
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
