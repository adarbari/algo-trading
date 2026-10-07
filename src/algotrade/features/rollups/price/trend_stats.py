"""``trend_stats@v2``: short and long returns, momentum acceleration, the return z-score,
the 100 / 200-session channels and the prior levels a breakout or breakdown must clear, the
pullback's age, the close's place in the day's range and the streaks, from daily bars
(``docs/data/technical.md``).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` (252)
earlier sessions. One row per instrument with a bar on the session.

    ret_1d/3d/10d/120d/252d  close / close n sessions earlier - 1
    mom_12_1                 close 21 sessions earlier / close 252 sessions earlier - 1
    mom_accel_5d             ret_5d today - ret_5d five sessions earlier (momentum
                             accelerating above 0, deteriorating below)
    ret_z_20d                the session's one-session return / the sample stdev of the 20
                             one-session returns before it
    high_100d, low_100d,     highest high / lowest low over the last n sessions
    high_200d, low_200d
    prior_high_50d,          the extreme over the n sessions BEFORE the session (the level a
    prior_low_20d/50d        breakout or breakdown close must clear; momentum@v1 has
                             prior_high_20d)
    sessions_since_high_20d  sessions since the highest high of the last 20 (0: today)
    close_range_pos          (close - low) / (high - low) of the session's bar
    close_streak             signed consecutive sessions with the close above (+) / below (-)
                             the previous close; 0 when unchanged
    sma20_streak             signed consecutive sessions above (+) / below (-) the 20-mean
    tight_range_sessions     consecutive sessions on which the 20-session range / close was at
                             most ``tight_range_pct`` (0.15): the length of the base

A streak counts only while every session in it has a bar (and a known mean or range); it is
capped by the sessions read. Parameters: ``TrendStatsParams`` (``config/site/rollups.toml``
``["trend_stats@v2"]``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.momentum import channel_features
from algotrade.features.rollups.price.price_stats import Matrix, Panel, panel, traded_rows
from algotrade.quant.rolling import rolling_max, rolling_mean, rolling_min, trailing_run

NAME = "trend_stats"
VERSION = 2
BARS = "bars/1d"
RETURN_WINDOWS = (1, 3, 10, 120, 252)
SKIP, LONG = 21, 252  # the 12-1 momentum: skip the last month, measure the year before it
ACCEL = 5  # momentum acceleration: the 5-session return against the one before it
Z_WINDOW = 20  # one-session returns the return z-score is measured against
CHANNELS = (100, 200)
PRIOR = (("high", 50), ("low", 20), ("low", 50))  # the extremes over the sessions before
MEAN_WINDOW = 20  # sma20_streak's mean, tight_range_sessions' range, the pullback's age
REG_WINDOW = 90  # the regression of log close on time (Clenow's momentum)
PERIODS_PER_YEAR = 252
LOOKBACK = LONG  # earlier sessions read: a return over 252 sessions needs the close before
ZERO_STD = 1e-9  # a return stdev under this is rounding noise over equal returns: unknown z
ZERO_VAR = 1e-16  # a log-close variance under this is rounding noise over equal closes: no fit
CLOSE, HIGH, LOW = (f"{BARS}.{c}" for c in ("close", "high", "low"))


def _gap(n: int) -> str:
    return f"a session among the last {n} has no bar (a gap), or the history is shorter"


FEATURES = (
    *(
        Feature(
            f"ret_{n}d", "float32", "decimal",
            f"Close / close {n} session{'s' if n > 1 else ''} earlier - 1",
            _gap(n + 1), valid_range=(-1, None), inputs=(CLOSE,),
        )
        for n in RETURN_WINDOWS
    ),
    Feature(
        "mom_12_1", "float32", "decimal",
        f"Close {SKIP} sessions earlier / close {LONG} sessions earlier - 1: the 12-month "
        "return with the last month skipped (the Jegadeesh-Titman momentum signal, which "
        "leaves out the short-term reversal month)",
        _gap(LONG + 1), valid_range=(-1, None), inputs=(CLOSE,),
    ),
    Feature(
        f"mom_accel_{ACCEL}d", "float32", "decimal",
        f"The {ACCEL}-session return today minus the {ACCEL}-session return {ACCEL} sessions "
        "earlier: above 0 momentum is accelerating (this week beat last week), below 0 "
        "deteriorating; -0.04 means this week's return was 4 points below last week's",
        _gap(2 * ACCEL + 1), valid_range=(-5, 5), inputs=(CLOSE,),
    ),
    Feature(
        f"ret_z_{Z_WINDOW}d", "float32", "ratio",
        "The session's one-session return (close / previous close - 1) / the sample standard "
        f"deviation (ddof 1) of the {Z_WINDOW} one-session returns before it: the day's "
        "surprise in standard deviations, on the same base as volume_z_20d",
        f"{_gap(Z_WINDOW + 2)}; or those {Z_WINDOW} returns were all equal (zero standard "
        "deviation)",
        inputs=(CLOSE,),
    ),
    *channel_features(CHANNELS, HIGH, LOW),
    *(
        Feature(
            f"prior_{side}_{n}d", "float32", "usd_per_share",
            f"{'Highest daily high' if side == 'high' else 'Lowest daily low'} over the {n} "
            f"sessions before the session (the session excluded): the level a "
            f"{'breakout' if side == 'high' else 'breakdown'} close must clear",
            f"a session among the {n} before the session has no bar (a gap), or the history is "
            "shorter", valid_range=(0, None), inputs=(HIGH if side == "high" else LOW,),
        )
        for side, n in PRIOR
    ),
    Feature(
        f"sessions_since_high_{MEAN_WINDOW}d", "int", "sessions",
        f"Sessions since the highest high of the last {MEAN_WINDOW} sessions (0: today's high "
        "is the highest; 19: the pullback has lasted the whole window): the age of the "
        "current pullback",
        _gap(MEAN_WINDOW), valid_range=(0, MEAN_WINDOW - 1), inputs=(HIGH,),
    ),
    Feature(
        "close_range_pos", "float32", "ratio",
        "Where the close sits in the session's own high-low range: (close - low) / (high - "
        "low), 1 at the high of the day, 0 at the low; above 0.7 the session closed strong",
        "never null for a traded session, except a bar whose high equals its low (no range)",
        valid_range=(0, 1), inputs=(HIGH, LOW, CLOSE),
    ),
    Feature(
        f"trend_r2_{REG_WINDOW}d", "float32", "ratio",
        f"R-squared of the least-squares line through the log close over the last {REG_WINDOW} "
        "sessions: how much of the price path a straight trend explains, 1 a perfectly smooth "
        "trend, 0 no trend at all (Clenow's trend quality)",
        f"{_gap(REG_WINDOW)}; or the close never moved over the window",
        valid_range=(0, 1), inputs=(CLOSE,),
    ),
    Feature(
        f"reg_slope_{REG_WINDOW}d_ann", "float32", "decimal",
        f"The slope of that line, annualised: exp(slope x {PERIODS_PER_YEAR}) - 1, the yearly "
        "return the last {REG_WINDOW} sessions' trend implies (0.40 is a trend pace of 40% a year)",
        _gap(REG_WINDOW), valid_range=(-1, None), inputs=(CLOSE,),
    ),
    Feature(
        "close_streak", "int", "sessions",
        "Signed count of consecutive sessions, ending on the session, with the close above the "
        "previous close (positive) or below it (negative); 0 when the close is unchanged; the "
        "count stops at the first session without a bar before it",
        "no bar on the session before (a gap)", valid_range=(-LOOKBACK, LOOKBACK),
        inputs=(CLOSE,),
    ),
    Feature(
        f"sma{MEAN_WINDOW}_streak", "int", "sessions",
        "Signed count of consecutive sessions, ending on the session, with the close above "
        f"its {MEAN_WINDOW}-session mean (positive) or below it (negative); 0 when equal; the "
        "count stops at the first session whose mean is unknown",
        f"the session's {MEAN_WINDOW}-session mean is unknown ({_gap(MEAN_WINDOW)})",
        valid_range=(-LOOKBACK, LOOKBACK), inputs=(CLOSE,),
    ),
    Feature(
        "tight_range_sessions", "int", "sessions",
        f"Consecutive sessions, ending on the session, on which the {MEAN_WINDOW}-session "
        "high-low range / close was at most tight_range_pct (0.15): the length of the base "
        "(0: the session itself is not tight)",
        f"the session's {MEAN_WINDOW}-session range is unknown ({_gap(MEAN_WINDOW)})",
        valid_range=(0, None), inputs=(HIGH, LOW, CLOSE),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class TrendStatsParams:
    tight_range_pct: float = 0.15  # a 20-session range at most this share of the close is tight

    def __post_init__(self) -> None:
        if not 0 < self.tight_range_pct < 1:
            raise ValueError(f"tight_range_pct must be in (0, 1), got {self.tight_range_pct}")


def _if_complete(value: Matrix, window: Matrix) -> Matrix:
    return np.where(~np.isnan(window).any(axis=0), value, np.nan)


def returns(close: Matrix) -> dict[str, Matrix]:
    out = {
        f"ret_{n}d": _if_complete(close[-1] / close[-n - 1] - 1.0, close[-n - 1 :])
        for n in RETURN_WINDOWS
    }
    out["mom_12_1"] = _if_complete(close[-SKIP - 1] / close[-LONG - 1] - 1.0, close[-LONG - 1 :])
    this = close[-1] / close[-ACCEL - 1] - 1.0
    last = close[-ACCEL - 1] / close[-2 * ACCEL - 1] - 1.0
    out[f"mom_accel_{ACCEL}d"] = _if_complete(this - last, close[-2 * ACCEL - 1 :])
    return out


def return_z(close: Matrix) -> Matrix:
    """The last one-session return in units of the sample stdev of the ``Z_WINDOW`` before."""
    if len(close) < Z_WINDOW + 2:
        return np.full(close.shape[1], np.nan)
    daily = close[1:] / close[:-1] - 1.0
    base = daily[-Z_WINDOW - 1 : -1]
    std = base.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(std > ZERO_STD, daily[-1] / std, np.nan)
    return _if_complete(z, close[-Z_WINDOW - 2 :])


def levels(px: Panel) -> dict[str, Matrix]:
    """The channels, the prior extremes, the pullback's age and the close's range position."""
    out: dict[str, Matrix] = {}
    for n in CHANNELS:
        out[f"high_{n}d"] = px.high[-n:].max(axis=0)
        out[f"low_{n}d"] = px.low[-n:].min(axis=0)
    for side, n in PRIOR:
        prices = (px.high if side == "high" else px.low)[-n - 1 : -1]
        out[f"prior_{side}_{n}d"] = prices.max(axis=0) if side == "high" else prices.min(axis=0)
    recent = px.high[-MEAN_WINDOW:]
    age = np.argmax(recent[::-1] == recent.max(axis=0), axis=0)  # the latest of equal highs
    out[f"sessions_since_high_{MEAN_WINDOW}d"] = _if_complete(age.astype(float), recent)
    span = px.high[-1] - px.low[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        out["close_range_pos"] = np.where(span > 0, (px.close[-1] - px.low[-1]) / span, np.nan)
    return out


def regression(close: Matrix) -> tuple[Matrix, Matrix]:
    """For the last row: ``(r2, annualised slope)`` of the least-squares line through the log
    close over the last ``REG_WINDOW`` rows (NaN on a gap; r2 NaN when the close never moved)."""
    y = np.log(close[-REG_WINDOW:])
    x = np.arange(REG_WINDOW, dtype=float)
    x = x - x.mean()
    y_mean = y.mean(axis=0)
    cov = (x[:, None] * (y - y_mean)).sum(axis=0)
    var_x = (x**2).sum()
    var_y = ((y - y_mean) ** 2).sum(axis=0)
    slope = cov / var_x
    with np.errstate(divide="ignore", invalid="ignore"):
        r2 = np.where(var_y > ZERO_VAR, cov**2 / (var_x * var_y), np.nan)
    complete = ~np.isnan(y).any(axis=0)
    return np.where(complete, r2, np.nan), np.where(
        complete, np.expm1(slope * PERIODS_PER_YEAR), np.nan
    )


def signed_run(diff: Matrix, known: np.ndarray) -> Matrix:
    """The signed trailing run of ``diff``'s sign: rows above 0 count up, below 0 down."""
    up = trailing_run(diff > 0, known)
    down = trailing_run(diff < 0, known)
    return np.where(np.isnan(up), np.nan, np.where(up > 0, up, -down))


def streaks(px: Panel, p: TrendStatsParams) -> dict[str, Matrix]:
    close = px.close
    change = np.diff(close, axis=0)
    mean = rolling_mean(close, MEAN_WINDOW)
    width = (rolling_max(px.high, MEAN_WINDOW) - rolling_min(px.low, MEAN_WINDOW)) / close
    return {
        "close_streak": signed_run(change, ~np.isnan(change)),
        f"sma{MEAN_WINDOW}_streak": signed_run(close - mean, ~np.isnan(mean)),
        "tight_range_sessions": trailing_run(width <= p.tight_range_pct, ~np.isnan(width)),
    }


def compute(inputs: Inputs, session: date, p: TrendStatsParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, LOOKBACK + 1))
    r2, slope = regression(px.close)
    values = {
        **returns(px.close),
        f"ret_z_{Z_WINDOW}d": return_z(px.close),
        **levels(px),
        f"trend_r2_{REG_WINDOW}d": r2,
        f"reg_slope_{REG_WINDOW}d_ann": slope,
        **streaks(px, p),
    }
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Short and long returns, the 12-1 momentum and its acceleration, the return z-score, the "
    "100 / 200-session channels, the prior 20 / 50-session extremes, the pullback's age, the "
    f"close's place in the day's range, the {REG_WINDOW}-session regression trend quality and "
    "pace, and the close, SMA20 and tight-range streaks",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
    params=TrendStatsParams(),
)
