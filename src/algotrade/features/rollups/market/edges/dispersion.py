"""The realised side of dispersion (design D6): the mean realised volatility of the universe's
stocks over the last ``CLOSES`` closes, the denominator of ``realised_corr_ratio_21`` (the
index's realised volatility over the same closes divided by it: near 1 when the names move
together, low when they move apart).

The members are the S&P 500 stocks of the snapshots the session sees: the universe snapshot's
stocks (``asset_class`` ``STOCK``, as ``market_breadth`` counts them) whose reference row says
``in_sp500``, never an older or later list. A member counts only with a bar on every one of the
``CLOSES`` sessions; with fewer than ``min_members`` such members the mean is NaN (UNKNOWN), never
a mean of a thin sample. Before the first reference or universe snapshot there is no list and the
mean is NaN: the stored index-membership intervals (``instruments/index_membership``, from 1996)
would reach further back but need a ticker-to-id resolution per session, a later slice.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.price.price_stats import panel
from algotrade.quant import realized_vol

CLOSES = 21  # closes of the window: 20 log returns, the hv20 convention of market_trend
PERIODS_PER_YEAR = 252
MEMBER_CLASS = "STOCK"


def mean_member_vol(
    universe: pd.DataFrame | None,
    reference: pd.DataFrame | None,
    bars: pd.DataFrame | None,
    session: date,
    min_members: int,
) -> float:
    """The mean annualised realised volatility of the members with a complete window of
    ``CLOSES`` closes ending on ``session`` (NaN: no universe, reference or bars, or fewer than
    ``min_members`` complete members)."""
    if universe is None or reference is None or bars is None or bars.empty:
        return np.nan
    if "in_sp500" not in reference.columns:
        return np.nan
    index = reference.loc[reference["in_sp500"].fillna(False).astype(bool), "instrument_id"]
    stocks = universe.loc[universe["asset_class"] == MEMBER_CLASS, "instrument_id"]
    members = stocks[stocks.isin(index)].unique()
    mine = bars[bars["instrument_id"].isin(members)]
    if mine.empty:
        return np.nan
    px = panel(mine, sessions_ending(session, CLOSES))
    complete = ~np.isnan(px.close).any(axis=0) & (px.close > 0).all(axis=0)
    if int(complete.sum()) < min_members:
        return np.nan
    vol = realized_vol.close_to_close(px.close[:, complete], CLOSES - 1, PERIODS_PER_YEAR)[-1]
    return float(np.mean(vol))
