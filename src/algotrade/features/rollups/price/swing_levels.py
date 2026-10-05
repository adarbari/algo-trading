"""``swing_levels@v1``: the most recent confirmed swing high above the close (resistance) and
swing low below it (support), from daily bars (``docs/data/swing.md``).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``), the
session plus ``WINDOW - 1`` earlier sessions. One row per instrument with a bar on the session.

A bar t is a **swing high** when its high is strictly above each of the ``PIVOT_WIDTH`` (5)
highs before it and at least each of the 5 highs after it (a flat top counts once, at its
first bar); a **swing low** mirrors it with lows. All 11 sessions must have a bar. A pivot at t
is confirmed only once bar t + 5 exists, so on session d only pivots up to d - 5 count (bars
after d are never read). The bars read are the last ``WINDOW`` (252) sessions, d - 251 to d,
and a pivot needs its 5 bars each side inside them, so a pivot can be dated d - 246 to d - 5.

    swing_high       the high of the most recent confirmed swing high strictly above the
                     session's close; swing_high_date its session
    swing_low        the low of the most recent confirmed swing low strictly below the close;
                     swing_low_date its session

So ``swing_high > close > swing_low`` whenever they are known. Distances (``dist_to_*``) are
expression features (``config/site/features/swing.toml``). The pivot width and the window are
part of the definition: changing one is a new version.
"""

from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import panel

type Matrix = npt.NDArray[np.float64]

NAME = "swing_levels"
VERSION = 1
BARS = "bars/1d"
PIVOT_WIDTH = 5  # bars on each side of a pivot
WINDOW = 252  # sessions of bars read, the session included
FIRST_PIVOT = WINDOW - 1 - PIVOT_WIDTH  # the oldest pivot, d - 246: its 5 bars before are read

CLOSE, HIGH, LOW = (f"{BARS}.{c}" for c in ("close", "high", "low"))
_PIVOT = (
    f"a bar whose high is strictly above the {PIVOT_WIDTH} highs before it and at least the "
    f"{PIVOT_WIDTH} after it, confirmed {PIVOT_WIDTH} sessions later"
)


def _none(side: str, where: str) -> str:
    return (
        f"no confirmed swing {side} {where} the close dated {PIVOT_WIDTH} to {FIRST_PIVOT} "
        f"sessions before the session (e.g. the close is at a {WINDOW}-session "
        f"{'high' if side == 'high' else 'low'}), or fewer than {2 * PIVOT_WIDTH + 1} bars in a row"
    )


FEATURES = (
    Feature(
        "swing_high", "float32", "usd_per_share",
        f"Resistance: the high of the most recent swing high above the close ({_PIVOT})",
        _none("high", "above"), valid_range=(0, None), inputs=(HIGH, CLOSE),
    ),
    Feature(
        "swing_high_date", "date", "date", "The session of that swing high",
        _none("high", "above"), inputs=(HIGH, CLOSE),
    ),
    Feature(
        "swing_low", "float32", "usd_per_share",
        "Support: the low of the most recent swing low below the close (a bar whose low is "
        f"strictly below the {PIVOT_WIDTH} lows before it and at most the {PIVOT_WIDTH} after "
        f"it, confirmed {PIVOT_WIDTH} sessions later)",
        _none("low", "below"), valid_range=(0, None), inputs=(LOW, CLOSE),
    ),
    Feature(
        "swing_low_date", "date", "date", "The session of that swing low",
        _none("low", "below"), inputs=(LOW, CLOSE),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def pivots(prices: Matrix, high: bool, width: int = PIVOT_WIDTH) -> npt.NDArray[np.bool_]:
    """Rows ``width .. n - 1 - width`` of a sessions x instruments matrix: whether each bar is
    a confirmed pivot (strictly beyond the ``width`` bars before, at least as far as the
    ``width`` after; a missing bar, NaN, compares False so it is never a pivot)."""
    n = len(prices)
    sign = 1.0 if high else -1.0
    centre = sign * prices[width : n - width]
    found = np.ones(centre.shape, dtype=bool)
    for j in range(1, width + 1):
        found &= centre > sign * prices[width - j : n - width - j]
        found &= centre >= sign * prices[width + j : n - width + j]
    return found


def latest_level(
    prices: Matrix, close: Matrix, high: bool, days: list[date]
) -> tuple[Matrix, list[date | None]]:
    """Per column, the most recent confirmed pivot strictly beyond the last close (above it
    for highs, below it for lows): its price (NaN: none) and session."""
    centre = prices[PIVOT_WIDTH : len(prices) - PIVOT_WIDTH]
    beyond = centre > close if high else centre < close
    hits = pivots(prices, high) & beyond
    last = len(hits) - 1 - np.argmax(hits[::-1], axis=0)
    has = hits.any(axis=0)
    level = np.where(has, centre[last, np.arange(centre.shape[1])], np.nan)
    when = [days[i + PIVOT_WIDTH] if ok else None for i, ok in zip(last, has, strict=True)]
    return level, when


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    days = sessions_ending(session, WINDOW)
    px = panel(bars, days)
    traded = ~np.isnan(px.close[-1])
    close = px.close[-1]
    swing_high, high_on = latest_level(px.high, close, True, days)
    swing_low, low_on = latest_level(px.low, close, False, days)
    return pd.DataFrame(
        {
            "instrument_id": px.ids[traded],
            "swing_high": swing_high[traded],
            "swing_high_date": [d for d, t in zip(high_on, traded, strict=True) if t],
            "swing_low": swing_low[traded],
            "swing_low_date": [d for d, t in zip(low_on, traded, strict=True) if t],
        }
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Resistance and support: the most recent confirmed swing high above and swing low below "
    f"the close ({PIVOT_WIDTH} bars each side, pivots {PIVOT_WIDTH} to {FIRST_PIVOT} sessions "
    "back)",
    (Input(BARS, lookback=WINDOW - 1),),
    FEATURES,
    compute,
)
