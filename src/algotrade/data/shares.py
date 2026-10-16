"""Share counts and basic financials (``instruments/shares``, SEC company facts) for
consumers and the producer.

The table holds two kinds of fact, told apart by ``concept``: share counts (``dei``,
``weighted_basic``; the count is in ``shares``) and flows (``revenue``, ``net_income``,
``eps_diluted``; the amount is in ``value``, its ``unit`` is ``usd`` or ``usd_per_share``).

The table is stored in increments: each run of the ``shares`` task adds the facts it found
new plus one ``checked`` marker per instrument whose CIK it fetched (``fetched_on``). A read
unions every partition and keeps the latest stored version of each row
(``instrument_id``, ``concept``, ``tag``, ``period_start``, ``period_end``, ``filed``): two
us-gaap tags of one concept (``Revenues`` and ``SalesRevenueNet``) for the same period and
filing are two rows, and a null in a key column (a marker's ``tag``, a share count's
``period_start``) equals another null.

Point in time is the FILING date, not the partition: a fact filed in 2025 that a backfill
stored in 2026 was public in 2025, so ``share_facts`` returns every fact and consumers keep
those with ``filed`` on or before their session (``features`` does it per session).
"""

from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/shares"
KEY = ["instrument_id", "concept", "tag", "period_start", "period_end", "filed"]
CHECKED = "checked"  # the marker concept: "this CIK was fetched on fetched_on"
DATES = ("period_start", "period_end", "filed", "fetched_on")
ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))


def stored_shares(reader: StoreReader, as_of: datetime | None = None) -> pd.DataFrame:
    """Every stored row (facts and markers), the latest version per key; empty when none.
    Date columns are ``date`` objects (``None`` when missing)."""
    frame = reader.table_range(TABLE, *ALL_TIME, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[*KEY, "cik", "shares", "value", "fetched_on"])
    if "tag" not in frame.columns:  # a partition written before the column: null, not a KeyError
        frame["tag"] = None
    frame["tag"] = frame["tag"].astype(object).where(frame["tag"].notna(), None)
    for column in DATES:
        if column in frame.columns:
            day = pd.to_datetime(frame[column]).dt.date
            frame[column] = day.astype(object).where(frame[column].notna(), None)
    # The latest stored version wins (run_id breaks a tie of stamps); the result is in key
    # order, so it does not depend on the order the partitions or rows came in.
    frame = frame.sort_values(["knowledge_ts", "run_id"], kind="stable")
    frame = frame.drop_duplicates(KEY, keep="last")
    return frame.sort_values(KEY, kind="stable", na_position="first").reset_index(drop=True)


def share_facts(reader: StoreReader, as_of: datetime | None = None) -> pd.DataFrame:
    """The facts (no markers), sorted by ``filed``, without the stamp columns."""
    frame = stored_shares(reader, as_of)
    frame = frame[frame["concept"] != CHECKED]
    stamps = ["session_date", "knowledge_ts", "source", "run_id"]
    frame = frame.drop(columns=[c for c in stamps if c in frame.columns])
    frame = frame.sort_values(["instrument_id", "concept"], kind="stable")
    return frame.sort_values("filed", kind="stable").reset_index(drop=True)
