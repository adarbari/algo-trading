"""``candle@v1``: the shape of the session's bar (body and wick shares, the body against the
recent average), its relation to the previous bar and the named candles, from daily bars
(``docs/data/technical.md``).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` (20)
earlier sessions. One row per instrument with a bar on the session. Every column is read
from the session's open, high, low and close (and the previous bar where said).

    body_share, upper_wick_share,  |close - open|, the high above the body and the low below
    lower_wick_share               it, each over the range (high - low)
    body_vs_avg_20d                |close - open| / the mean |close - open| of the 20 sessions
                                   before
    bar_relation                   INSIDE, OUTSIDE, UP_GAP, DOWN_GAP or OVERLAP against the
                                   previous bar's high-low range
    prev_bar_relation              the same label for the previous bar against the one before
    candle                         the first matching of BULLISH_ENGULFING, BEARISH_ENGULFING,
                                   HAMMER, SHOOTING_STAR, DOJI, else NONE

Parameters: ``CandleParams`` (``config/site/rollups.toml`` ``["candle@v1"]``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, panel, traded_rows

NAME = "candle"
VERSION = 1
BARS = "bars/1d"
AVG_WINDOW = 20  # sessions before the session whose mean body the engulfing test measures
LOOKBACK = AVG_WINDOW
RELATIONS = ("INSIDE", "OUTSIDE", "UP_GAP", "DOWN_GAP", "OVERLAP")
CANDLES = ("HAMMER", "SHOOTING_STAR", "DOJI", "BULLISH_ENGULFING", "BEARISH_ENGULFING", "NONE")
OPEN, HIGH, LOW, CLOSE = (f"{BARS}.{c}" for c in ("open", "high", "low", "close"))
_NO_RANGE = "the bar has no range (high equals low)"
_NO_PREV = "the previous session has no bar"
_OHLC = (OPEN, HIGH, LOW, CLOSE)

FEATURES = (
    Feature(
        "body_share", "float32", "ratio",
        "The candle body over the session's range: |close - open| / (high - low); 0 is a "
        "doji, 1 a marubozu (no wicks), 0.5 a body half the day's range",
        _NO_RANGE, valid_range=(0, 1), inputs=_OHLC,
    ),
    Feature(
        "upper_wick_share", "float32", "ratio",
        "The upper shadow over the session's range: (high - max(open, close)) / (high - low); "
        "0.6 means the price gave back most of its day's high",
        _NO_RANGE, valid_range=(0, 1), inputs=_OHLC,
    ),
    Feature(
        "lower_wick_share", "float32", "ratio",
        "The lower shadow over the session's range: (min(open, close) - low) / (high - low); "
        "0.6 means the price was bought back from most of its day's low",
        _NO_RANGE, valid_range=(0, 1), inputs=_OHLC,
    ),
    Feature(
        f"body_vs_avg_{AVG_WINDOW}d", "float32", "ratio",
        f"The session's |close - open| over the mean |close - open| of the {AVG_WINDOW} "
        "sessions before it: above 1 a bigger body than usual, 2 twice the usual",
        f"a session among the {AVG_WINDOW} before has no bar (a gap), or the history is "
        "shorter; or those bodies were all zero (a zero mean)",
        valid_range=(0, None), inputs=(OPEN, CLOSE),
    ),
    Feature(
        "bar_relation", "str", "category",
        "The session's high-low range against the previous session's: INSIDE (high at or "
        "below the previous high and low at or above the previous low), OUTSIDE (a higher "
        "high and a lower low), UP_GAP (the low above the previous high), DOWN_GAP (the high "
        "below the previous low), else OVERLAP; tested in that order",
        _NO_PREV, "label", categories=RELATIONS, inputs=(HIGH, LOW),
    ),
    Feature(
        "prev_bar_relation", "str", "category",
        "bar_relation of the previous session (its range against the session before it): "
        "what the day before was, for a pattern that completes today (an inside day "
        "breakout)",
        "the previous session or the one before it has no bar", "label",
        categories=RELATIONS, inputs=(HIGH, LOW),
    ),
    Feature(
        "candle", "str", "category",
        "The named candle of the session, the first match of BULLISH_ENGULFING (an up body "
        "that covers the previous down body, at least engulf_min_body x the 20-session "
        "average body), BEARISH_ENGULFING (the mirror), HAMMER (a lower wick of at least "
        "hammer_wick bodies, the upper wick at most small_body of the range, a body above "
        "doji_body), SHOOTING_STAR (the mirror), DOJI (body at most doji_body of the range), "
        "else NONE",
        f"{_NO_RANGE}, or {_NO_PREV}; an unknown {AVG_WINDOW}-session average body never "
        "matches an engulfing candle (the bar reads on to the other tests, never null for it)",
        "label", categories=CANDLES, inputs=_OHLC,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class CandleParams:
    doji_body: float = 0.1  # a body at most this share of the range is a doji
    hammer_wick: float = 2.0  # the long wick at least this many bodies
    small_body: float = 0.3  # the other wick at most this share of the range
    engulf_min_body: float = 0.5  # the engulfing body at least this x the average body

    def __post_init__(self) -> None:
        for name in ("doji_body", "small_body"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"{name} must be in (0, 1), got {getattr(self, name)}")
        if self.hammer_wick <= 0:
            raise ValueError(f"hammer_wick must be positive, got {self.hammer_wick}")
        if self.engulf_min_body < 0:
            raise ValueError(f"engulf_min_body must not be negative, got {self.engulf_min_body}")


def _labelled(label: npt.NDArray[np.str_], known: npt.NDArray[np.bool_]) -> npt.NDArray[np.object_]:
    """The labels as objects, ``None`` where ``known`` is False."""
    out = label.astype(object)
    out[~known] = None
    return out


def relation(
    high: Matrix, low: Matrix, prev_high: Matrix, prev_low: Matrix
) -> npt.NDArray[np.object_]:
    """INSIDE, OUTSIDE, UP_GAP, DOWN_GAP or OVERLAP per instrument; ``None`` where any of the
    four is unknown."""
    label = np.select(
        [
            (high <= prev_high) & (low >= prev_low),
            (high > prev_high) & (low < prev_low),
            low > prev_high,
            high < prev_low,
        ],
        RELATIONS[:4],
        default=RELATIONS[4],
    )
    return _labelled(label, ~np.isnan(np.stack([high, low, prev_high, prev_low])).any(axis=0))


def shape(px: Panel) -> dict[str, Matrix]:
    """The body and wick shares of the last row (NaN where the bar has no range)."""
    o, h, low, c = px.open[-1], px.high[-1], px.low[-1], px.close[-1]
    span = h - low
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = span > 0
        return {
            "body_share": np.where(ok, np.abs(c - o) / span, np.nan),
            "upper_wick_share": np.where(ok, (h - np.maximum(o, c)) / span, np.nan),
            "lower_wick_share": np.where(ok, (np.minimum(o, c) - low) / span, np.nan),
        }


def body_vs_average(px: Panel) -> Matrix:
    """The last body over the mean body of the ``AVG_WINDOW`` rows before it."""
    bodies = np.abs(px.close - px.open)
    base = bodies[-AVG_WINDOW - 1 : -1]
    mean = base.mean(axis=0)  # NaN with a gap among the rows
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(mean > 0, bodies[-1] / mean, np.nan)


def named_candle(px: Panel, p: CandleParams) -> npt.NDArray[np.object_]:
    """The first matching candle per instrument (see the module docstring); ``None`` when
    the bar has no range or the previous bar is missing."""
    o, h, low, c = px.open[-1], px.high[-1], px.low[-1], px.close[-1]
    po, pc = px.open[-2], px.close[-2]
    ph, pl = px.high[-2], px.low[-2]
    span = h - low
    body = np.abs(c - o)
    upper, lower = h - np.maximum(o, c), np.minimum(o, c) - low
    average = np.abs(px.close - px.open)[-AVG_WINDOW - 1 : -1].mean(axis=0)
    big = body >= p.engulf_min_body * average  # False when the average is unknown
    with np.errstate(invalid="ignore"):
        bull = (c > o) & (pc < po) & (o <= pc) & (c >= po) & big
        bear = (c < o) & (pc > po) & (o >= pc) & (c <= po) & big
        hammer = (lower >= p.hammer_wick * body) & (upper <= p.small_body * span)
        star = (upper >= p.hammer_wick * body) & (lower <= p.small_body * span)
        small = body <= p.doji_body * span
        label = np.select(
            [bull, bear, hammer & ~small, star & ~small, small],
            ["BULLISH_ENGULFING", "BEARISH_ENGULFING", "HAMMER", "SHOOTING_STAR", "DOJI"],
            default="NONE",
        )
        known = (span > 0) & ~np.isnan(np.stack([o, c, po, pc, ph, pl])).any(axis=0)
    return _labelled(label, known)


def compute(inputs: Inputs, session: date, p: CandleParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, LOOKBACK + 1))
    values = {
        **shape(px),
        f"body_vs_avg_{AVG_WINDOW}d": body_vs_average(px),
        "bar_relation": relation(px.high[-1], px.low[-1], px.high[-2], px.low[-2]),
        "prev_bar_relation": relation(px.high[-2], px.low[-2], px.high[-3], px.low[-3]),
        "candle": named_candle(px, p),
    }
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The session's bar shape (body and wick shares, the body against its 20-session average), "
    "its relation to the previous bar (inside, outside, gaps) and the named candles (hammer, "
    "shooting star, doji, bullish and bearish engulfing)",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
    params=CandleParams(),
)
