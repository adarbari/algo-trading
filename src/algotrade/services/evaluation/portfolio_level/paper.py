"""The paper record's book (ADR 0053 amendment 2026-10-10, ADR 0088 G15): one edge's own paper
trades as ``OpenTrade`` rows, read only for its record owner, as known at ``as_of`` (a settlement
written later is not leaked into an earlier night). Never another edge's rows, another owner's or
any other store. A paper row stores no collateral, so ``capital`` is None and ``open_collateral``
reads UNKNOWN on this path until the table stores it."""

from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.paper.reading import LOOKBACK_DAYS, read_paper
from algotrade.services.evaluation.portfolio_level.book import OpenTrade

OPEN, SKIPPED = "open", "skipped"  # a paper row's status (forward/settle.py owns the others)


def paper_book(
    reader: StoreReader,
    edge_id: str,
    owner: str,
    session: date,
    as_of: datetime | None = None,
) -> list[OpenTrade]:
    """``edge_id``'s paper trades (record owner ``owner``) signalled up to ``session``, as the
    table stood at ``as_of``, over the paper record's whole lookback (``LOOKBACK_DAYS``: a window
    of 252 sessions closes inside it), so a trade still open from an early signal is never left
    out. ``sell_session`` is the PLANNED sell: a row still ``open`` is due then (``planned_exit``,
    its exit not known: past it unsettled, the book unknown); a ``won`` / ``lost`` row exited at
    it (a trade the contract closes earlier is held to its planned sell: a book too full, never
    too empty); a ``skipped`` row never entered and is left out."""
    frame = read_paper(
        reader, {edge_id: owner}, session - timedelta(days=LOOKBACK_DAYS), session, as_of
    )
    trades: list[OpenTrade] = []
    for row in frame.to_dict("records"):
        buy, sell = row["buy_session"], row["sell_session"]
        if row["status"] == SKIPPED or pd.isna(buy) or pd.isna(sell):
            continue
        settled = row["status"] != OPEN
        trades.append(
            OpenTrade(
                str(row["instrument_id"]),
                buy,
                sell if settled else None,
                sell,
                None,
                str(row["licence"]),
            )
        )
    return trades
