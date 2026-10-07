"""``gaps@v1``: today's opening gap and the nearest unfilled price gaps on either side of the
close, from daily bars (``docs/data/swing.md``).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` (252)
earlier sessions. One row per instrument with a bar on the session.

A gap on session t compares its bar with the one on the session before it (both must exist):

    up gap      low_t > high_{t-1}: the zone [high_{t-1}, low_t] was never traded. It is
                filled when a later session (through today) has a low <= high_{t-1}
    down gap    high_t < low_{t-1}: the zone [high_t, low_{t-1}] was never traded. It is
                filled when a later session has a high >= low_{t-1}

An unfilled gap lies on the far side of every close since it: an unfilled up gap is below the
close (support), an unfilled down gap above it (resistance). So:

    gap_above       the lower edge of the nearest unfilled DOWN gap above the close: the zone
                    sits wholly above it and ``gap_above`` (high_t) is where price would enter
                    it; nearest is the smallest such edge (a tie: the more recent gap);
                    ``gap_above_date`` is session t
    gap_below       the upper edge of the nearest unfilled UP gap below the close (low_t,
                    where price falling would enter it): the largest such edge;
                    ``gap_below_date`` is session t
    gap_open_pct    today's open / the previous session's close - 1

A gap that price has entered but not crossed (the close is inside the zone) is partly filled
and is neither above nor below the close. The window is the 253 bars read: a gap on the oldest
bar has no previous bar in it. Distances to the zones (``dist_to_gap_above``,
``dist_to_gap_below``) are expression features (``config/site/features/swing.toml``).
"""

from datetime import date
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, panel, traded_rows

NAME = "gaps"
VERSION = 1
BARS = "bars/1d"
LOOKBACK = 252  # earlier sessions read: 253 bars

OPEN, CLOSE, HIGH, LOW = (f"{BARS}.{c}" for c in ("open", "close", "high", "low"))
_NONE = (
    "no unfilled {kind} gap {where} the close among the last {n} sessions (every gap is "
    "filled, the close is inside one, or the bars around it are missing)"
)

FEATURES = (
    Feature(
        "gap_open_pct", "float32", "decimal",
        "Today's open / the previous session's close - 1: the opening gap, up positive",
        "the previous session has no bar", valid_range=(-1, None), inputs=(OPEN, CLOSE),
    ),
    Feature(
        "gap_above", "float32", "usd_per_share",
        "Resistance gap: the lower edge (the high of the gap session, where price rising would "
        "enter the zone) of the nearest unfilled down gap above the close (a down gap: high < "
        "the previous low; filled when a later high reaches that previous low)",
        _NONE.format(kind="down", where="above", n=LOOKBACK), valid_range=(0, None),
        inputs=(HIGH, LOW, CLOSE),
    ),
    Feature(
        "gap_above_date", "date", "date", "The session of that down gap",
        _NONE.format(kind="down", where="above", n=LOOKBACK), inputs=(HIGH, LOW, CLOSE),
    ),
    Feature(
        "gap_below", "float32", "usd_per_share",
        "Support gap: the upper edge (the low of the gap session, where price falling would "
        "enter the zone) of the nearest unfilled up gap below the close (an up gap: low > the "
        "previous high; filled when a later low reaches that previous high)",
        _NONE.format(kind="up", where="below", n=LOOKBACK), valid_range=(0, None),
        inputs=(HIGH, LOW, CLOSE),
    ),
    Feature(
        "gap_below_date", "date", "date", "The session of that up gap",
        _NONE.format(kind="up", where="below", n=LOOKBACK), inputs=(HIGH, LOW, CLOSE),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _later(values: Matrix, high: bool) -> Matrix:
    """Per row, the max (high) or min of ``values`` over the rows AFTER it (NaN: none, or no
    bar: a missing bar never fills a gap)."""
    reduce = np.fmax if high else np.fmin
    running = reduce.accumulate(values[::-1], axis=0)[::-1]
    out = np.full(values.shape, np.nan)
    out[:-1] = running[1:]
    return out


def _nearest(
    edge: Matrix, unfilled: npt.NDArray[np.bool_], close: Matrix, above: bool, days: list[date]
) -> tuple[Matrix, npt.NDArray[np.object_]]:
    """Per column, the edge (and its session) of the unfilled gap wholly above (below) the
    last close that is nearest to it; ties go to the most recent session."""
    with np.errstate(invalid="ignore"):
        usable = unfilled & ((edge > close[-1]) if above else (edge < close[-1]))
    key = np.where(usable, edge if above else -edge, np.inf)[::-1]  # newest first for ties
    pick = len(key) - 1 - np.argmin(key, axis=0)
    has = usable.any(axis=0)
    level = np.where(has, edge[pick, np.arange(edge.shape[1])], np.nan)
    when = np.array(
        [days[r] if ok else None for r, ok in zip(pick, has, strict=True)], dtype=object
    )
    return level, when


def nearest_gaps(
    px_high: Matrix, px_low: Matrix, close: Matrix, days: list[date]
) -> dict[str, npt.NDArray[Any]]:
    """The nearest unfilled down gap above and up gap below the last close."""
    prev_high = np.vstack([np.full((1, px_high.shape[1]), np.nan), px_high[:-1]])
    prev_low = np.vstack([np.full((1, px_low.shape[1]), np.nan), px_low[:-1]])
    with np.errstate(invalid="ignore"):
        down = px_high < prev_low  # zone [high_t, low_{t-1}]
        up = px_low > prev_high  # zone [high_{t-1}, low_t]
        down_open = down & ~(_later(px_high, True) >= prev_low)
        up_open = up & ~(_later(px_low, False) <= prev_high)
    above, above_on = _nearest(px_high, down_open, close, True, days)
    below, below_on = _nearest(px_low, up_open, close, False, days)
    return {
        "gap_above": above,
        "gap_above_date": above_on,
        "gap_below": below,
        "gap_below_date": below_on,
    }


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    days = sessions_ending(session, LOOKBACK + 1)
    px = panel(bars, days)
    values = {
        "gap_open_pct": px.open[-1] / px.close[-2] - 1.0,
        **nearest_gaps(px.high, px.low, px.close, days),
    }
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Today's opening gap and the nearest unfilled down gap above and up gap below the close "
    f"(over the last {LOOKBACK + 1} sessions)",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
