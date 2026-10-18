"""``max_return@v1``: the largest one-day return of the last 21 sessions, the lottery-attention
measure MAX (Bali, Cakici and Whitelaw 2011).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``; never total
return), the session plus ``WINDOW`` earlier sessions. One row per instrument with a bar on the
session. Windows are exchange sessions (``core.time.calendar``): the value is null (UNKNOWN),
never a shorter window, unless every one of the ``WINDOW + 1`` sessions has a close.

    max_ret_21d  max over the last 21 sessions of close_t / close_{t-1} - 1 (signed: the best
                 day, not the largest absolute move; ``price_moves.one_day_move`` is that)

The window (21) is part of the definition: changing it is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import panel, traded_rows

NAME = "max_return"
VERSION = 1
BARS = "bars/1d"
WINDOW = 21

FEATURES = (
    Feature(
        "max_ret_21d", "float32", "decimal",
        f"The best one-day close-to-close return of the last {WINDOW} sessions "
        "(split-adjusted as of the session): 0.12 is a day that gained 12%; negative when "
        "every day lost",
        f"a session among the last {WINDOW + 1} has no close (a gap), or the history is shorter",
        valid_range=(-1, None), inputs=(f"{BARS}.close",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def best_day(closes: np.ndarray) -> np.ndarray:
    """Per column of a sessions x instruments close matrix (``WINDOW + 1`` rows, NaN: no bar):
    the largest one-day return, NaN for a column with a gap or a non-positive close."""
    closes = np.where(closes > 0, closes, np.nan)  # a non-positive close is not a price
    with np.errstate(invalid="ignore", divide="ignore"):
        moves = closes[1:] / closes[:-1] - 1.0
    complete = ~np.isnan(closes).any(axis=0)
    return np.where(complete, np.nanmax(np.where(np.isnan(moves), -np.inf, moves), axis=0), np.nan)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW + 1))
    return traded_rows(px, {"max_ret_21d": best_day(px.close)}, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"The best one-day close-to-close return of the last {WINDOW} sessions (MAX)",
    (Input(BARS, lookback=WINDOW),),
    FEATURES,
    compute,
)
