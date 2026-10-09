"""Read one user's paper trades (``results/edge_paper``) for the signal sessions in a window.

The table is partitioned by signal session and its runs merge per (user, edge, signal session,
name): a night that settles a trade rewrites its row, the latest known row wins, and ``as_of``
(row by row) gives the book as an earlier night saw it. A trade whose signal session is after
``until`` is not read."""

from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import EDGE_PAPER

LOOKBACK_DAYS = (
    400  # the window a paper record is read over: a window of 252 sessions closes inside it
)
PAPER_COLUMNS = (
    "user_id", "edge_id", "signal_session", "instrument_id", "config_hash", "outcome_hash",
    "screener", "status", "reason", "buy_session", "sell_session", "horizon_sessions", "rank",
    "delisted", "excess_return", "knowledge_ts",
)  # fmt: skip


def read_paper(
    reader: StoreReader,
    user_id: str,
    since: date,
    until: date,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """``user_id``'s paper trades with a signal session in ``since..until``, as ``PAPER_COLUMNS``
    sorted by (signal session, edge, rank, name); empty when none is stored."""
    frame = reader.table_range(EDGE_PAPER.name, since, until, as_of)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(PAPER_COLUMNS))
    mine = frame[frame["user_id"] == user_id]
    out = mine.reindex(columns=list(PAPER_COLUMNS))
    for column in ("signal_session", "buy_session", "sell_session"):
        out[column] = pd.to_datetime(out[column]).dt.date
    return out.sort_values(
        ["signal_session", "edge_id", "rank", "instrument_id"], kind="stable"
    ).reset_index(drop=True)
