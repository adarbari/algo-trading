"""``cutler_rsi@v1``: Cutler's RSI over the last 3 sessions, the short oscillator of the weak-close
reversal research (Pagonidis 2013: long when RSI(3) < 10 and IBS <= 0.5, hold while RSI(3) <= 40).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``), the session
plus ``WINDOW`` earlier sessions. One row per instrument with a bar on the session. Only bars on
or before the session are read.

    rsi_3    Cutler's RSI: 100 - 100 / (1 + average gain / average loss) where both averages are
             SIMPLE means of the last 3 close-to-close changes (gains and losses, the other side
             counted as 0). Wilder's ``momentum.rsi_14`` smooths recursively instead; the two
             are different oscillators and the values differ even at equal length. 100 when the
             3 changes had no loss, null when they had neither (a flat close)

The window (3) and the simple average are part of the definition: changing either is a new
version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Panel, panel, traded_rows

NAME = "cutler_rsi"
VERSION = 1
BARS = "bars/1d"
WINDOW = 3  # close-to-close changes averaged, so WINDOW + 1 consecutive closes

FEATURES = (
    Feature(
        f"rsi_{WINDOW}", "float32", "pct_points",
        f"Cutler's RSI ({WINDOW}) of close changes, split-adjusted as of the session: 100 - 100 / "
        f"(1 + average gain / average loss), both the simple mean of the last {WINDOW} changes; "
        "100 when there was no loss",
        f"a session among the last {WINDOW + 1} has no close (a gap), or the history is shorter; "
        "or the close never moved over the window (no gain and no loss: 0/0)",
        valid_range=(0, 100), inputs=(f"{BARS}.close",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def cutler_rsi(px: Panel) -> np.ndarray:
    """Per column of the panel's last ``WINDOW + 1`` rows, Cutler's RSI at the last row; NaN for a
    column with a gap (a non-positive close is not a price) or with no move at all."""
    close = np.where(px.close[-WINDOW - 1 :] > 0, px.close[-WINDOW - 1 :], np.nan)
    change = np.diff(close, axis=0)
    gain = np.clip(change, 0, None).mean(axis=0)  # NaN propagates: a gap is no value
    loss = np.clip(-change, 0, None).mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(loss > 0, 100 - 100 / (1 + gain / loss), np.where(gain > 0, 100.0, np.nan))
    return np.where(np.isnan(change).any(axis=0), np.nan, rsi)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW + 1))
    return traded_rows(px, {f"rsi_{WINDOW}": cutler_rsi(px)}, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Cutler's RSI ({WINDOW}): the simple-average oscillator over the last {WINDOW} sessions",
    (Input(BARS, lookback=WINDOW),),
    FEATURES,
    compute,
)
