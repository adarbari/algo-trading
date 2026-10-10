"""Read paper trades (``results/edge_paper``) for the signal sessions in a window.

Paper trades follow the edge's owner (ADR 0053 amendment 2026-10-10): ``user_id`` is the RECORD
owner, ``site`` for a site edge, else the user whose edge it is. ``read_paper`` reads the record
of the edges a reader sees, each under its record owner, so a follower's old rows of a site edge
(written when followers traded) are left out of the shared record; ``read_stored`` is every row
one record owner wrote, which is what that owner's own nightly settles.

The table is partitioned by signal session and its runs merge per (user, edge, signal session,
name): a night that settles a trade rewrites its row, the latest known row wins, and ``as_of``
(row by row) gives the book as an earlier night saw it. A trade whose signal session is after
``until`` is not read."""

from collections.abc import Mapping
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import EDGE_PAPER

# The window a paper record is read over: a window of 252 sessions closes inside it.
LOOKBACK_DAYS = 400


def job_name(user_id: str) -> str:
    """The run-record ``job`` of one record owner's nightly (``edge-paper:<owner>``): its stats
    say, per recording edge, what the night did (signalled, no picks, not due, skipped and why)."""
    return f"edge-paper:{user_id}"


PAPER_COLUMNS = (
    "user_id", "edge_id", "signal_session", "instrument_id", "config_hash", "outcome_hash",
    "screener", "status", "reason", "buy_session", "sell_session", "horizon_sessions", "rank",
    "delisted", "excess_return", "knowledge_ts",
)  # fmt: skip


def read_stored(
    reader: StoreReader,
    user_id: str,
    since: date,
    until: date,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Every row ``user_id`` wrote with a signal session in ``since..until``, as ``PAPER_COLUMNS``
    sorted by (signal session, edge, rank, name); empty when none is stored."""
    frame = reader.table_range(EDGE_PAPER.name, since, until, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(PAPER_COLUMNS))
    return _shaped(frame[frame["user_id"] == user_id])


def read_paper(
    reader: StoreReader,
    owners: Mapping[str, str],
    since: date,
    until: date,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The paper trades of the edges in ``owners`` (edge id -> its record owner) with a signal
    session in ``since..until``: only the rows written by that edge's record owner, as
    ``PAPER_COLUMNS`` sorted as ``read_stored``; empty when none is stored."""
    frame = reader.table_range(EDGE_PAPER.name, since, until, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(PAPER_COLUMNS))
    owner = frame["edge_id"].map(owners)
    return _shaped(frame[owner.notna() & (frame["user_id"] == owner)])


def _shaped(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.reindex(columns=list(PAPER_COLUMNS))
    for column in ("signal_session", "buy_session", "sell_session"):
        out[column] = pd.to_datetime(out[column]).dt.date
    return out.sort_values(
        ["signal_session", "edge_id", "rank", "instrument_id"], kind="stable"
    ).reset_index(drop=True)
