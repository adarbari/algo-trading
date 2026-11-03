"""The paper record's book (ADR 0053 amendment 2026-10-10, ADR 0088 G15): one edge's own paper
trades as ``OpenTrade`` rows, read only for its record owner, as known at ``as_of`` (a settlement
written later is not leaked into an earlier night). Never another edge's rows, another owner's or
any other store. A paper row stores no collateral, so ``capital`` is None and ``open_collateral``
reads UNKNOWN on this path until the table stores it. ``paper_row`` is the level's row over that
book, the one both tonight's picks and the paper record's own gate read (E9)."""

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.paper.reading import LOOKBACK_DAYS, read_paper
from algotrade.services.evaluation.portfolio_level.book import (
    OpenTrade,
    PortfolioRow,
    portfolio_row,
)

SKIPPED = "skipped"  # a paper row's status (forward/settle.py owns the others)


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
    out. Every row that entered exits at its ``sell_session``, the PLANNED sell, whatever its
    status:
    the paper record holds each trade to it (a trade the contract closes earlier too), so a
    settlement lag never makes the book UNKNOWN (a book too full, never too empty); a ``skipped``
    row never entered and is left out."""
    frame = read_paper(
        reader, {edge_id: owner}, session - timedelta(days=LOOKBACK_DAYS), session, as_of
    )
    trades: list[OpenTrade] = []
    for row in frame.to_dict("records"):
        buy, sell = row["buy_session"], row["sell_session"]
        if row["status"] == SKIPPED or pd.isna(buy) or pd.isna(sell):
            continue
        trades.append(
            OpenTrade(
                str(row["instrument_id"]),
                buy,
                sell,
                sell,
                None,
                str(row["licence"]),
            )
        )
    return trades


def paper_row(
    reader: StoreReader,
    edge_id: str,
    owner: str,
    session: date,
    as_of: datetime | None,
    sectors: Callable[[frozenset[str], date], Mapping[str, str | None]],
    *,
    option: bool = False,
) -> PortfolioRow:
    """The portfolio level's row at ``session`` over ``edge_id``'s paper book as known at ``as_of``
    (``paper_book``); ``sectors`` reads the held names' sectors at ``session`` (only when one is
    held). An empty book is a known state: a record holds nothing until it buys."""
    trades = paper_book(reader, edge_id, owner, session, as_of)
    held = frozenset(t.instrument_id for t in trades)
    return portfolio_row(trades, session, sectors(held, session) if held else {}, option=option)
