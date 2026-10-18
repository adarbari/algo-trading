"""``signed_volume@v1``: on-balance volume's 20-session change as a share of the volume traded,
the OBV trend of Granville (1963).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``; never total
return), the session plus ``WINDOW`` earlier sessions. One row per instrument with a bar on the
session. Windows are exchange sessions (``core.time.calendar``): the value is null (UNKNOWN),
never a shorter window, unless every one of the ``WINDOW + 1`` sessions has a bar.

    obv_trend_20d  sum over the last 20 sessions of sign(close_t - close_{t-1}) x volume_t, divided
                   by the total volume of those sessions: the 20-session change of on-balance
                   volume per share traded (a flat close adds 0 to the top, its volume to the
                   bottom); between -1 and 1, scale-free so names compare

The window (20) is part of the definition: changing it is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, panel, traded_rows

NAME = "signed_volume"
VERSION = 1
BARS = "bars/1d"
WINDOW = 20

FEATURES = (
    Feature(
        f"obv_trend_{WINDOW}d", "float32", "decimal",
        f"The {WINDOW}-session change of on-balance volume / the volume traded in those sessions "
        "(each session's volume counts positive on a close above the previous close, negative "
        "below, zero when unchanged): 0.3 is net buying on a third of the volume, -0.3 net "
        "selling",
        f"a session among the last {WINDOW + 1} has no bar (a gap), or the history is shorter, "
        f"or the last {WINDOW} sessions had no volume at all",
        valid_range=(-1, 1), inputs=(f"{BARS}.close", f"{BARS}.volume"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def obv_trend(closes: Matrix, volumes: Matrix) -> Matrix:
    """Per instrument, from a sessions x instruments close matrix (``WINDOW + 1`` rows, NaN: no
    bar) and its volume matrix: the signed volume of the last ``WINDOW`` sessions over their total
    volume, NaN for a gap or no volume."""
    complete = ~np.isnan(closes).any(axis=0) & ~np.isnan(volumes[1:]).any(axis=0)
    window = np.nan_to_num(volumes[1:])
    signed = np.sign(closes[1:] - closes[:-1]) * window
    total = window.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(complete & (total > 0), signed.sum(axis=0) / total, np.nan)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW + 1))
    return traded_rows(px, {f"obv_trend_{WINDOW}d": obv_trend(px.close, px.volume)}, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"The {WINDOW}-session on-balance volume change as a share of the volume traded",
    (Input(BARS, lookback=WINDOW),),
    FEATURES,
    compute,
)
