"""``illiquidity@v1``: the Amihud illiquidity the decoy battery ranks by (ADR 0053 amendment
2026-10-18), from daily bars. MAX is ``max_return@v1``.

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` earlier
sessions. One row per instrument with a bar on the session.

    amihud_63d    the mean over the last 63 sessions of |daily return| / dollar volume in
                  millions (Amihud 2002): the price move per dollar traded, high when illiquid

It is null on any gap in its window (a missing bar, a shorter history) and on a session with no
volume, whose ratio does not exist.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, bars_rows

NAME = "illiquidity"
VERSION = 1
BARS = "bars/1d"
AMIHUD_WINDOW = 63  # sessions of the Amihud mean (a quarter)
MILLION = 1e6  # dollar volume is in millions in Amihud's ratio
LOOKBACK = AMIHUD_WINDOW  # earlier sessions read: 63 returns need 64 closes
CLOSE, VOLUME = f"{BARS}.close", f"{BARS}.volume"
_GAP = "a session in the window has no bar (a gap), or the history is shorter"

FEATURES = (
    Feature(
        f"amihud_{AMIHUD_WINDOW}d", "float32", "ratio",
        f"Amihud illiquidity: the mean over the last {AMIHUD_WINDOW} sessions of |daily return| "
        "divided by the session's dollar volume (close x volume) in millions: 0.05 is a 5% move "
        "per $1M traded on average. High is illiquid, and illiquid stocks have earned a premium "
        "(Amihud 2002)",
        f"a session among the last {AMIHUD_WINDOW + 1} closes has no bar ({_GAP}), or one of "
        f"the {AMIHUD_WINDOW} sessions traded no volume",
        valid_range=(0, None), inputs=(CLOSE, VOLUME),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def amihud(px: Panel) -> Matrix:
    """The mean of |return| / dollar volume in millions over the last ``AMIHUD_WINDOW``
    sessions; NaN on a gap or a session without volume."""
    close = px.close[-AMIHUD_WINDOW - 1 :]
    dollars = close[1:] * px.volume[-AMIHUD_WINDOW:] / MILLION
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.abs(close[1:] / close[:-1] - 1.0) / dollars
    return np.where(np.isfinite(ratio).all(axis=0), ratio.mean(axis=0), np.nan)


def stats(px: Panel) -> dict[str, Matrix]:
    return {f"amihud_{AMIHUD_WINDOW}d": amihud(px)}


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    return bars_rows(inputs, session, LOOKBACK, stats, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Amihud illiquidity (mean |return| per dollar traded over {AMIHUD_WINDOW} sessions): the "
    "rank of the illiquidity decoy",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
