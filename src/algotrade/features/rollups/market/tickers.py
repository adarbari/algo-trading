"""Tickers to ids and closes for market-entity groups: the one lookup they share.

A market group names its instruments by ticker (SPY, QQQ, HYG, ...) and finds their ids in
the ``instruments/symbol_ids`` input (the reference snapshot's symbol -> id map, ADR 0018: an
id is never built). The map is a lookup only, never a population. ``closes`` pivots daily bars
(split-adjusted as of the session, never dividend-adjusted: ``bars/1d``) onto the session axis,
one column per ticker in the order asked (NaN: no id, or no bar that session).
"""

from collections.abc import Sequence
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.features.rollups.price.price_stats import panel

SYMBOL_IDS = "instruments/symbol_ids"
BARS = "bars/1d"

type Matrix = npt.NDArray[np.float64]


def ticker_ids(symbol_ids: pd.DataFrame | None, tickers: Sequence[str]) -> dict[str, str]:
    """``{ticker: instrument_id}`` for the tickers the map knows (absent: not listed)."""
    if symbol_ids is None:
        return {}
    known = dict(zip(symbol_ids["symbol"], symbol_ids["instrument_id"], strict=True))
    return {t: str(known[t]) for t in tickers if t in known}


def closes(
    bars: pd.DataFrame, ids: dict[str, str], tickers: Sequence[str], days: list[date]
) -> Matrix:
    """Closes as sessions (``days``) x ``tickers``; a ticker without an id is all NaN."""
    wanted = bars[bars["instrument_id"].isin(list(ids.values()))]
    out = np.full((len(days), len(tickers)), np.nan)
    if wanted.empty:
        return out
    px = panel(wanted, days)
    column = {iid: i for i, iid in enumerate(px.ids)}
    for j, ticker in enumerate(tickers):
        if ticker in ids and ids[ticker] in column:
            out[:, j] = px.close[:, column[ids[ticker]]]
    return out
