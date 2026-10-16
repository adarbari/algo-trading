"""Financial statement lines (``instruments/statements``, SEC company facts) for consumers and
the producer.

One row per us-gaap tag, period and filing: a duration (``period_type`` DURATION: an income
statement or cash flow line over a quarter, half year, nine months or year, cash flow lines
cumulative from the fiscal year start) or an instant (INSTANT: a balance sheet line at
``period_end``, ``period_start`` null). ``concept`` is what a rollup reads and ``tag`` the
us-gaap tag that supplied it; every tag of a concept is a row and the rollup chooses (ADR 0067).
``value`` is in ``unit`` (``usd``).

The table is stored in increments, like ``instruments/shares``: each run of the ``shares`` task
adds the facts it found new plus one ``checked`` marker per instrument whose CIK it fetched
(``fetched_on``). A read unions every partition and keeps the latest stored version of each row
(``instrument_id``, ``concept``, ``tag``, ``period_start``, ``period_end``, ``filed``); a null
in a key column (an instant's ``period_start``, a marker's ``tag``) equals another null.

Point in time is the FILING date, not the partition: a fact filed in 2025 that a backfill
stored in 2026 was public in 2025, so ``statement_facts(reader, session)`` returns the facts
filed on or before the session and no other.
"""

from datetime import date, datetime

import pandas as pd

from algotrade.data.shares import ALL_TIME, CHECKED, DATES, KEY, latest_versions
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/statements"
__all__ = [
    "ALL_TIME",
    "CHECKED",
    "DATES",
    "KEY",
    "STAMPS",
    "TABLE",
    "light_statements",
    "statement_facts",
    "stored_statements",
]
STAMPS = ["session_date", "knowledge_ts", "source", "run_id"]


def stored_statements(
    reader: StoreReader,
    as_of: datetime | None = None,
    columns: list[str] | None = None,
    instruments: list[str] | None = None,
) -> pd.DataFrame:
    """Every stored row (facts and markers), the latest version per key; empty when none.
    Date columns are ``date`` objects (``None`` when missing). ``columns``: only these (plus
    the key columns, ``cik`` and the stamps the merge needs); ``instruments``: only these ids
    (the table is large: the producer reads the whole of it by key columns only)."""
    wanted = None if columns is None else list(dict.fromkeys([*KEY, "cik", *columns]))
    frame = reader.table_range(TABLE, *ALL_TIME, as_of, instruments, wanted)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[*KEY, "cik", "value", "fetched_on"])
    return latest_versions(frame)


def light_statements(reader: StoreReader) -> pd.DataFrame:
    """``instrument_id``, ``cik``, ``concept`` and ``fetched_on`` of every stored row and
    nothing else, not deduplicated: what the producer needs to know what is due (a maximum per
    CIK) without reading the table's values."""
    frame = reader.table_range(TABLE, *ALL_TIME, None, None, ["cik", "concept", "fetched_on"])
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["instrument_id", "cik", "concept", "fetched_on"])
    return frame[["instrument_id", "cik", "concept", "fetched_on"]]


def statement_facts(
    reader: StoreReader,
    session: date,
    as_of: datetime | None = None,
    instruments: list[str] | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """The facts (no markers) filed on or before ``session``, sorted by ``filed``, without the
    stamp columns; empty when none. ``instruments`` and ``columns`` narrow the read (the key
    columns and ``cik`` are always returned): a consumer asks for the ids and fields it uses."""
    frame = stored_statements(reader, as_of, columns, instruments)
    frame = frame[frame["concept"] != CHECKED]  # a marker has no filing date
    frame = frame[frame["filed"] <= session]
    frame = frame.drop(columns=[c for c in STAMPS if c in frame.columns])
    return frame.sort_values("filed", kind="stable").reset_index(drop=True)
