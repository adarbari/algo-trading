"""``vol_long@v1``: the long realised-volatility windows beside ``vol_stats@v1`` (10 / 60), from
daily bars: the half-year and the year of close-to-close volatility and the year's downside
deviation. A leaf group of its own so that adding a window never bumps ``vol_stats`` (whose
columns screeners, edges and expression features name); the straddle setups of the options
design read ``hv252`` (design F6, ADR 0088).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` (252)
earlier sessions. One row per instrument with a bar on the session.

    hv126, hv252       close-to-close realised vol over 126 / 252 log returns, annualised
    downside_dev_252   the root mean square of the year's negative log returns (a return at or
                       above zero counts as 0), annualised: the volatility of the losses
                       alone, so a name that only jumps up reads low where hv252 reads high

Every window is complete or null: a gap among the closes of the window, or a shorter history,
is null (UNKNOWN), never a shorter window.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, bars_rows
from algotrade.quant import realized_vol

NAME = "vol_long"
VERSION = 1
BARS = "bars/1d"
HV_WINDOWS = (126, 252)
DOWNSIDE_WINDOW = 252
PERIODS_PER_YEAR = 252
LOOKBACK = max((*HV_WINDOWS, DOWNSIDE_WINDOW))  # earlier sessions: n returns need n + 1 closes
CLOSE = f"{BARS}.close"


def _gap(n: int) -> str:
    return f"a session among the last {n} has no bar (a gap), or the history is shorter"


FEATURES = (
    *(
        Feature(
            f"hv{n}", "float32", "decimal",
            f"Close-to-close realised volatility: sample stdev of the last {n} log returns x "
            f"sqrt({PERIODS_PER_YEAR})",
            _gap(n + 1), valid_range=(0, 5), inputs=(CLOSE,),
        )
        for n in HV_WINDOWS
    ),
    Feature(
        f"downside_dev_{DOWNSIDE_WINDOW}", "float32", "decimal",
        f"Downside deviation: the root mean square of the last {DOWNSIDE_WINDOW} negative log "
        f"returns (non-negative returns count as 0) x sqrt({PERIODS_PER_YEAR})",
        _gap(DOWNSIDE_WINDOW + 1), valid_range=(0, 5), inputs=(CLOSE,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def downside_deviation(close: Matrix, window: int) -> Matrix:
    """Per column: sqrt(mean(min(r, 0)^2)) x sqrt(periods) over the last ``window`` log returns
    of ``close`` (NaN: a gap in the window or too few rows)."""
    if len(close) < window + 1:
        return np.full(close.shape[1], np.nan)
    returns = np.diff(np.log(close[-window - 1 :]), axis=0)
    losses = np.minimum(returns, 0.0)
    return np.sqrt((losses**2).mean(axis=0) * PERIODS_PER_YEAR)


def stats(px: Panel) -> dict[str, Matrix]:
    out: dict[str, Matrix] = {}
    for n in HV_WINDOWS:
        out[f"hv{n}"] = realized_vol.close_to_close(px.close[-n - 1 :], n, PERIODS_PER_YEAR)[-1]
    out[f"downside_dev_{DOWNSIDE_WINDOW}"] = downside_deviation(px.close, DOWNSIDE_WINDOW)
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    return bars_rows(inputs, session, LOOKBACK, stats, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Close-to-close realised volatility over {HV_WINDOWS[0]} and {HV_WINDOWS[1]} sessions and "
    f"the {DOWNSIDE_WINDOW}-session downside deviation, beside vol_stats@v1's 10 and 60",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
