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

from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/statements"
KEY = ["instrument_id", "concept", "tag", "period_start", "period_end", "filed"]
CHECKED = "checked"  # the marker concept: "this CIK was fetched on fetched_on"
DATES = ("period_start", "period_end", "filed", "fetched_on")
ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
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


def statement_facts(
    reader: StoreReader, session: date, as_of: datetime | None = None
) -> pd.DataFrame:
    """The facts (no markers) filed on or before ``session``, sorted by ``filed``, without the
    stamp columns; empty when none."""
    frame = stored_statements(reader, as_of)
    frame = frame[frame["concept"] != CHECKED]  # a marker has no filing date
    frame = frame[frame["filed"] <= session]
    frame = frame.drop(columns=[c for c in STAMPS if c in frame.columns])
    return frame.sort_values("filed", kind="stable").reset_index(drop=True)
