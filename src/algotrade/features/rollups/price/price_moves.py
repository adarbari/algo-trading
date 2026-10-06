"""``price_moves@v1``: the largest one-day close-to-close move over the last 20 sessions.

The VRP scanner's "recent > 10% one-day move" risk flag (``docs/screeners/vrp-scanner.md``):
a large gap makes HV30 unstable. A small group of its own (rather than a new ``price_stats``
version) because it needs bar history, which an expression feature cannot read.

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``; never total
return), the session plus ``WINDOW`` earlier sessions. One row per instrument with a bar on
the session. Windows are exchange sessions (``core.time.calendar``): the value is null
(UNKNOWN), never a shorter window, unless every one of the ``WINDOW + 1`` sessions has a close.

    one_day_move   max over the last 20 sessions of |close_t / close_{t-1} - 1|

The window (20) is part of the definition: changing it is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import panel, traded_rows

NAME = "price_moves"
VERSION = 1
BARS = "bars/1d"
WINDOW = 20

FEATURES = (
    Feature(
        "one_day_move", "float32", "decimal",
        f"Largest absolute one-day close-to-close return over the last {WINDOW} sessions "
        "(split-adjusted as of the session): 0.12 is a 12% move up or down",
        f"a session among the last {WINDOW + 1} has no close (a gap), or the history is "
        "shorter",
        valid_range=(0, None), inputs=(f"{BARS}.close",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def largest_move(closes: np.ndarray) -> np.ndarray:
    """Per column of a sessions x instruments close matrix (``WINDOW + 1`` rows, NaN: no bar):
    the largest absolute one-day return, NaN for a column with a gap."""
    closes = np.where(closes > 0, closes, np.nan)  # a non-positive close is not a price
    with np.errstate(invalid="ignore", divide="ignore"):
        moves = np.abs(closes[1:] / closes[:-1] - 1.0)
    complete = ~np.isnan(closes).any(axis=0)
    return np.where(complete, np.nan_to_num(moves).max(axis=0, initial=0.0), np.nan)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW + 1))  # price_stats' session axis
    return traded_rows(px, {"one_day_move": largest_move(px.close)}, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"The largest one-day close-to-close move over the last {WINDOW} sessions",
    (Input(BARS, lookback=WINDOW),),
    FEATURES,
    compute,
)
