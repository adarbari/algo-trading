"""``anomaly_stats@v1``: the lottery-demand and illiquidity measures of the return anomalies the
decoy battery ranks by (ADR 0053 amendment 2026-10-18), from daily bars.

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` earlier
sessions. One row per instrument with a bar on the session.

    max_ret_21d   the largest daily return of the last 21 sessions (MAX, Bali, Cakici and
                  Whitelaw 2011): the lottery-like stocks have the biggest one-day jumps
    amihud_63d    the mean over the last 63 sessions of |daily return| / dollar volume in
                  millions (Amihud 2002): the price move per dollar traded, high when illiquid

Both are null on any gap in their window (a missing bar, a shorter history); Amihud also on a
session with no volume, whose ratio does not exist.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, bars_rows

NAME = "anomaly_stats"
VERSION = 1
BARS = "bars/1d"
MAX_WINDOW = 21  # sessions of the MAX return
AMIHUD_WINDOW = 63  # sessions of the Amihud mean (a quarter)
MILLION = 1e6  # dollar volume is in millions in Amihud's ratio
LOOKBACK = AMIHUD_WINDOW  # earlier sessions read: 63 returns need 64 closes
CLOSE, VOLUME = f"{BARS}.close", f"{BARS}.volume"
_GAP = "a session in the window has no bar (a gap), or the history is shorter"

FEATURES = (
    Feature(
        f"max_ret_{MAX_WINDOW}d", "float32", "decimal",
        f"The largest daily return (close / previous close - 1) of the last {MAX_WINDOW} "
        "sessions, the MAX measure of lottery-like demand: 0.25 is a one-day jump of 25% inside "
        "the month; high-MAX stocks have tended to earn less afterwards (Bali, Cakici and "
        "Whitelaw 2011)",
        f"a session among the last {MAX_WINDOW + 1} closes has no bar ({_GAP})",
        valid_range=(-1, None), inputs=(CLOSE,),
    ),
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


def max_return(px: Panel) -> Matrix:
    """The largest of the last ``MAX_WINDOW`` daily returns; NaN on a gap."""
    close = px.close[-MAX_WINDOW - 1 :]
    with np.errstate(divide="ignore", invalid="ignore"):
        daily = close[1:] / close[:-1] - 1.0
    return np.where(np.isfinite(daily).all(axis=0), daily.max(axis=0), np.nan)


def amihud(px: Panel) -> Matrix:
    """The mean of |return| / dollar volume in millions over the last ``AMIHUD_WINDOW``
    sessions; NaN on a gap or a session without volume."""
    close = px.close[-AMIHUD_WINDOW - 1 :]
    dollars = close[1:] * px.volume[-AMIHUD_WINDOW:] / MILLION
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.abs(close[1:] / close[:-1] - 1.0) / dollars
    return np.where(np.isfinite(ratio).all(axis=0), ratio.mean(axis=0), np.nan)


def stats(px: Panel) -> dict[str, Matrix]:
    return {f"max_ret_{MAX_WINDOW}d": max_return(px), f"amihud_{AMIHUD_WINDOW}d": amihud(px)}


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    return bars_rows(inputs, session, LOOKBACK, stats, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"MAX (the largest daily return of {MAX_WINDOW} sessions) and Amihud illiquidity (mean "
    f"|return| per dollar traded over {AMIHUD_WINDOW} sessions): the ranks of the lottery and "
    "illiquidity decoys",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
