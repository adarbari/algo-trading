"""``session_returns@v1``: the last 20 sessions' return split into the overnight part (the
previous close to the open) and the intraday part (the open to the close), the decomposition of
Lou, Polk and Skouras (2019).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``; never total
return: an ex-dividend gap sits in the overnight part), the session plus ``WINDOW`` earlier
sessions. One row per instrument with a bar on the session. Windows are exchange sessions
(``core.time.calendar``): a value is null (UNKNOWN), never a shorter window, unless every one of
the ``WINDOW + 1`` sessions has a close and each of the last ``WINDOW`` an open, all positive.

    overnight_ret_20d  the product over the last 20 sessions of open_t / close_{t-1}, minus 1
    intraday_ret_20d   the product over the last 20 sessions of close_t / open_t, minus 1

The two compound to the 20-session close-to-close return: (1 + overnight) x (1 + intraday) - 1.
The window (20) is part of the definition: changing it is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, panel, traded_rows

NAME = "session_returns"
VERSION = 1
BARS = "bars/1d"
WINDOW = 20

_GAP = (
    f"a session among the last {WINDOW + 1} has no bar (a gap), has a non-positive open or "
    "close, or the history is shorter"
)
FEATURES = (
    Feature(
        f"overnight_ret_{WINDOW}d", "float32", "decimal",
        f"The compounded close-to-open return of the last {WINDOW} sessions (each open over the "
        "previous close, split-adjusted as of the session): 0.04 is a name that gained 4% "
        "overnight in total, whatever it did during the days",
        _GAP, valid_range=(-1, None), inputs=(f"{BARS}.open", f"{BARS}.close"),
    ),
    Feature(
        f"intraday_ret_{WINDOW}d", "float32", "decimal",
        f"The compounded open-to-close return of the last {WINDOW} sessions (each close over the "
        "same day's open, split-adjusted as of the session): the part of the month's move that "
        "happened while the market was open",
        _GAP, valid_range=(-1, None), inputs=(f"{BARS}.open", f"{BARS}.close"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def session_split(opens: Matrix, closes: Matrix) -> tuple[Matrix, Matrix]:
    """The overnight and the intraday compounded return per instrument, from sessions x
    instruments matrices of ``WINDOW + 1`` rows (NaN: no bar): NaN for a gap, a non-positive
    price, or a missing open anywhere in the window."""
    opens = np.where(opens > 0, opens, np.nan)
    closes = np.where(closes > 0, closes, np.nan)
    known = ~np.isnan(closes).any(axis=0) & ~np.isnan(opens[1:]).any(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        overnight = np.prod(opens[1:] / closes[:-1], axis=0) - 1.0
        intraday = np.prod(closes[1:] / opens[1:], axis=0) - 1.0
    return np.where(known, overnight, np.nan), np.where(known, intraday, np.nan)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW + 1))
    overnight, intraday = session_split(px.open, px.close)
    return traded_rows(
        px, {f"overnight_ret_{WINDOW}d": overnight, f"intraday_ret_{WINDOW}d": intraday}, COLUMNS
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"The last {WINDOW} sessions' return split into overnight (close to open) and intraday",
    (Input(BARS, lookback=WINDOW),),
    FEATURES,
    compute,
)
