"""Share counts and basic financials (``instruments/shares``, SEC company facts) for
consumers and the producer.

The table holds two kinds of fact, told apart by ``concept``: share counts (``dei``,
``weighted_basic``, ``ifrs_weighted``; the count is in ``shares``, its ``unit`` is ``shares``, or
``units`` for a trust that tags those) and flows (``revenue``, ``net_income``, ``eps_diluted``;
the amount is in ``value``, its ``unit`` is ``usd`` or ``usd_per_share``).

The table is stored in increments: each run of the ``shares`` task adds the facts it found
new plus one ``checked`` marker per instrument whose CIK it fetched (``fetched_on``). A read
unions every partition and keeps the latest stored version of each row
(``instrument_id``, ``concept``, ``tag``, ``period_start``, ``period_end``, ``filed``): two
us-gaap tags of one concept (``Revenues`` and ``SalesRevenueNet``) for the same period and
filing are two rows, and a null in a key column (a marker's ``tag``, a share count's
``period_start``) equals another null.

Point in time is the FILING, not the partition: a fact filed in 2025 that a backfill stored in
2026 was public in 2025, so ``share_facts`` returns every fact and ``known_from`` says from
which session each counts (``features`` keeps, per session, the facts known from it or before).
``known_from`` is the first session whose CLOSE is strictly after the instant SEC accepted the
filing (``accepted_ts``; 16:00 New York, 13:00 on an early close): a filing accepted at or
after the close, a 10-Q at 16:30 say, is not public at that session's close and counts from the
next. ``filed`` is a date and says
nothing about the hour (SEC dates a filing accepted until 17:30 that day), so a fact without
``accepted_ts`` counts from the session after ``filed``, never from ``filed`` itself.
"""

from datetime import date, datetime

import pandas as pd

from algotrade.core.time.calendar import EXCHANGE_TZ, close_time, is_session, next_session
from algotrade.storage.tables.readers import StoreReader

TABLE = "instruments/shares"
KEY = ["instrument_id", "concept", "tag", "period_start", "period_end", "filed"]
CHECKED = "checked"  # the marker concept: "this CIK was fetched on fetched_on"
DATES = ("period_start", "period_end", "filed", "fetched_on")
ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
NEVER = date(2200, 1, 1)  # ``known_from`` of a fact with no date (inside datetime64[ns])


def stored_shares(reader: StoreReader, as_of: datetime | None = None) -> pd.DataFrame:
    """Every stored row (facts and markers), the latest version per key; empty when none.
    Date columns are ``date`` objects (``None`` when missing)."""
    frame = reader.table_range(TABLE, *ALL_TIME, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=[*KEY, "cik", "shares", "value", "fetched_on"])
    return latest_versions(frame)


def latest_versions(frame: pd.DataFrame) -> pd.DataFrame:
    """The latest stored version of each ``KEY`` row of a union of partitions (shares and
    statements alike), in key order. Date columns become ``date`` objects (``None`` when
    missing) and a null ``tag`` (a marker, a partition written before the column) is ``None``,
    so a null in a key column equals another null."""
    if "tag" not in frame.columns:
        frame["tag"] = None
    if "accepted_ts" not in frame.columns:  # partitions older than the column: not known
        frame["accepted_ts"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
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


def known_from(facts: pd.DataFrame) -> pd.Series:
    """The session each fact of ``facts`` (``filed`` and, when present, ``accepted_ts``) counts
    from (module doc): the first session whose close is strictly after the acceptance instant, else
    the first session after ``filed``. A fact with neither is never known (``NEVER``)."""
    if "accepted_ts" in facts.columns:
        accepted = pd.to_datetime(facts["accepted_ts"], utc=True)
    else:
        accepted = pd.Series(pd.NaT, index=facts.index, dtype="datetime64[ns, UTC]")
    local = accepted.dt.tz_convert(EXCHANGE_TZ).dt.date
    filed = pd.to_datetime(facts["filed"]).dt.date
    days = set(local.dropna()) | set(filed.dropna())
    after = {d: next_session(d) for d in days}
    close = {d: close_time(d) for d in set(local.dropna()) if is_session(d)}
    closes = pd.to_datetime(local.map(close), utc=True)  # NaT: accepted on a non-session day
    on_time = accepted.notna() & (accepted < closes)
    by_acceptance = local.where(on_time, local.map(after))
    out = by_acceptance.where(accepted.notna(), filed.map(after))
    return out.astype(object).where(out.notna(), NEVER)
