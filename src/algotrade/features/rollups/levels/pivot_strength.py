"""``pivot_strength@v1``: how often the swing levels were tested, how old they are and
whether the pivots step up or down (``docs/data/swing.md``).

Inputs: ``bars/1d`` split-adjusted AS OF the session (the last ``WINDOW`` (252) sessions, as
``swing_levels@v1`` reads them) and the session's stored rows of ``swing_levels@v1`` (the
levels and their dates) and ``momentum@v1`` (``atr_14``, the tolerance's unit). One row per
instrument with a ``swing_levels@v1`` row.

    resistance_touches  distinct touches of ``swing_high`` over the 252 sessions read, the
                        pivot bar included. A bar touches when its high is within
                        ``touch_atr x atr_14`` of the level (|high - level| <= tolerance) and
                        its close is at or below it; a run of consecutive touching bars counts
                        once (a missing bar ends a run)
    support_touches     the mirror: lows within the tolerance of ``swing_low``, close at or
                        above it
    resistance_age      exchange sessions from ``swing_high_date`` to the session
    support_age         the same for ``swing_low_date``
    pivot_structure     HH_HL when the last two confirmed swing highs and the last two
                        confirmed swing lows both step up (the later above the earlier),
                        LH_LL when both step down, else MIXED; all pivots of the window
                        count (``swing_levels.pivots``), not only those beyond the close

Prices are compared as stored (``float32``, like the levels read from ``swing_levels@v1``),
so the pivot bar always touches its own level, however small the tolerance. Parameters:
``PivotStrengthParams`` (``config/site/rollups.toml ["pivot_strength@v1"]``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.levels.swing_levels import (
    FIRST_PIVOT,
    PIVOT_WIDTH,
    WINDOW,
    pivots,
)
from algotrade.features.rollups.price.price_stats import Matrix, panel

NAME = "pivot_strength"
VERSION = 1
BARS = "bars/1d"
LEVELS = "rollups/instrument/swing_levels@v1"
MOMENTUM = "rollups/instrument/momentum@v1"
STRUCTURES = ("HH_HL", "LH_LL", "MIXED")

CLOSE, HIGH, LOW = (f"{BARS}.{c}" for c in ("close", "high", "low"))
_NO_RESISTANCE = "swing_high is null (no swing_levels row or no swing high above the close)"
_NO_SUPPORT = "swing_low is null (no swing_levels row or no swing low below the close)"
_NO_ATR = "atr_14 is null (fewer than 15 consecutive bars)"
_TOUCH = (
    "a bar touches when its {side} is within touch_atr (0.5) x atr_14 of the level and its "
    "close is {close} it; consecutive touching bars count once"
)


@dataclass(frozen=True)
class PivotStrengthParams:
    touch_atr: float = 0.5  # how near a high / low must come to touch the level, in ATRs

    def __post_init__(self) -> None:
        if not self.touch_atr > 0:
            raise ValueError(f"touch_atr must be > 0, got {self.touch_atr}")


FEATURES = (
    Feature(
        "resistance_touches", "int", "count",
        f"Distinct touches of swing_high over the {WINDOW} sessions read, the pivot bar "
        f"included: {_TOUCH.format(side='high', close='at or below')}",
        f"{_NO_RESISTANCE}, or {_NO_ATR}", valid_range=(1, WINDOW),
        inputs=(HIGH, CLOSE, "swing_levels.swing_high@v1", "momentum.atr_14@v1"),
    ),
    Feature(
        "support_touches", "int", "count",
        f"Distinct touches of swing_low over the {WINDOW} sessions read, the pivot bar "
        f"included: {_TOUCH.format(side='low', close='at or above')}",
        f"{_NO_SUPPORT}, or {_NO_ATR}", valid_range=(1, WINDOW),
        inputs=(LOW, CLOSE, "swing_levels.swing_low@v1", "momentum.atr_14@v1"),
    ),
    Feature(
        "resistance_age", "int", "sessions",
        "Exchange sessions from the swing high's date to the session (at least "
        f"{PIVOT_WIDTH}: a pivot is confirmed {PIVOT_WIDTH} sessions later)",
        _NO_RESISTANCE, valid_range=(PIVOT_WIDTH, FIRST_PIVOT),
        inputs=("swing_levels.swing_high_date@v1",),
    ),
    Feature(
        "support_age", "int", "sessions",
        "Exchange sessions from the swing low's date to the session (at least "
        f"{PIVOT_WIDTH}: a pivot is confirmed {PIVOT_WIDTH} sessions later)",
        _NO_SUPPORT, valid_range=(PIVOT_WIDTH, FIRST_PIVOT),
        inputs=("swing_levels.swing_low_date@v1",),
    ),
    Feature(
        "pivot_structure", "str", "category",
        "HH_HL when the last two confirmed swing highs and the last two confirmed swing lows "
        "of the window both step up (the later above the earlier), LH_LL when both step "
        "down, else MIXED (an equal pair is MIXED); every confirmed pivot counts, not only "
        "those beyond the close",
        f"fewer than two confirmed swing highs or two swing lows in the {WINDOW} sessions "
        "read (or a missing bar around them)",
        "label", categories=STRUCTURES, inputs=(HIGH, LOW),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def touches(
    price: Matrix, close: Matrix, level: Matrix, tol: Matrix, high: bool
) -> npt.NDArray[np.int64]:
    """Per column of a bars x instruments matrix, the distinct touches of its ``level``: a
    bar touches when its ``price`` (high or low) is within ``tol`` of the level and its close
    is on the near side of it (at or below for a high, at or above for a low). Prices compare
    as ``float32`` (how the levels are stored); a NaN (missing bar, no level) never touches."""
    p, c, lv = price.astype(np.float32), close.astype(np.float32), level.astype(np.float32)
    with np.errstate(invalid="ignore"):
        near = np.abs(p.astype(np.float64) - lv) <= tol
        touch = near & ((c <= lv) if high else (c >= lv))
    starts = touch.copy()
    starts[1:] &= ~touch[:-1]  # a run counts once, at its first bar
    return starts.sum(axis=0)


def _last_two(
    found: npt.NDArray[np.bool_],
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], npt.NDArray[np.bool_]]:
    """Per column of a bars x instruments flag matrix, the rows of the last and the one
    before it (garbage where there are fewer than two) and whether there are two."""
    rows = np.arange(found.shape[1])
    last = len(found) - 1 - np.argmax(found[::-1], axis=0)
    rest = found.copy()
    rest[last, rows] = False
    before = len(found) - 1 - np.argmax(rest[::-1], axis=0)
    return last, before, found.sum(axis=0) >= 2


def structure(high: Matrix, low: Matrix) -> npt.NDArray[np.object_]:
    """Per column, HH_HL / LH_LL / MIXED from the last two swing highs and swing lows
    (``None`` when fewer than two of either)."""
    ids = np.arange(high.shape[1])
    shift = PIVOT_WIDTH  # pivots() rows start at bar PIVOT_WIDTH
    h_new, h_old, has_h = _last_two(pivots(high, True))
    l_new, l_old, has_l = _last_two(pivots(low, False))
    up_h = high[h_new + shift, ids] > high[h_old + shift, ids]
    down_h = high[h_new + shift, ids] < high[h_old + shift, ids]
    up_l = low[l_new + shift, ids] > low[l_old + shift, ids]
    down_l = low[l_new + shift, ids] < low[l_old + shift, ids]
    label = np.where(up_h & up_l, "HH_HL", np.where(down_h & down_l, "LH_LL", "MIXED"))
    out = np.full(high.shape[1], None, dtype=object)
    out[has_h & has_l] = label[has_h & has_l]
    return out


def _ages(dates: pd.Series, days: list[date]) -> Matrix:
    """Sessions from each date to the last of ``days`` (NaN: no date, or not among them)."""
    on = pd.Index(pd.to_datetime(dates, utc=True).dt.date)
    row = pd.Index(days).get_indexer(on)
    return np.where(row >= 0, len(days) - 1 - row, np.nan)


def _stored(frame: pd.DataFrame | None, session: date, columns: list[str]) -> pd.DataFrame:
    assert frame is not None  # required input
    today = frame[frame["session_date"] == session]
    return today.set_index(today["instrument_id"].astype(str))[columns]


def compute(inputs: Inputs, session: date, p: PivotStrengthParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    days = sessions_ending(session, WINDOW)
    px = panel(bars, days)
    rows = _stored(
        inputs[LEVELS], session, ["swing_high", "swing_high_date", "swing_low", "swing_low_date"]
    )
    atr = _stored(inputs[MOMENTUM], session, ["atr_14"])["atr_14"].reindex(rows.index)
    col = pd.Index(px.ids).get_indexer(rows.index)  # -1: no bar among the bars read
    at = np.where(col >= 0, col, 0)
    has_bar = col >= 0
    tol = p.touch_atr * atr.to_numpy(dtype=np.float64)
    out = pd.DataFrame({"instrument_id": rows.index.to_numpy()})
    for side, high in (("resistance", True), ("support", False)):
        level = rows["swing_high" if high else "swing_low"].to_numpy(dtype=np.float64)
        n = touches((px.high if high else px.low)[:, at], px.close[:, at], level, tol, high)
        known = has_bar & ~np.isnan(level) & ~np.isnan(tol)
        out[f"{side}_touches"] = np.where(known, n, np.nan)
        age = _ages(rows["swing_high_date" if high else "swing_low_date"], days)
        out[f"{side}_age"] = np.where(np.isnan(level), np.nan, age)
    shape = structure(px.high, px.low)[at]
    shape[~has_bar] = None
    out["pivot_structure"] = shape
    return out[["instrument_id", *COLUMNS]]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How often the swing high and low were tested (touches within 0.5 ATR), their age in "
    "sessions and whether the pivots step up (HH_HL), down (LH_LL) or mix",
    (Input(BARS, lookback=WINDOW - 1), Input(LEVELS), Input(MOMENTUM)),
    FEATURES,
    compute,
    PivotStrengthParams(),
)
