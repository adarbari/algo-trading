"""``trend_stats@v1``: longer returns, the 12-1 momentum, the return z-score and the streaks
(closes, sessions above the 20-session mean, tight-range sessions), from daily bars
(``docs/data/technical.md``).

Input: ``bars/1d`` split-adjusted AS OF the session, the session plus ``LOOKBACK`` (252)
earlier sessions. One row per instrument with a bar on the session.

    ret_120d, ret_252d    close / close n sessions earlier - 1
    mom_12_1              close 21 sessions earlier / close 252 sessions earlier - 1: the
                          12-month return with the last month skipped (Jegadeesh-Titman)
    ret_z_20d             the session's one-session return / the sample stdev of the 20
                          one-session returns before it
    close_streak          signed consecutive sessions with the close above (+) / below (-)
                          the previous close; 0 when unchanged
    sma20_streak          signed consecutive sessions with the close above (+) / below (-)
                          its 20-session mean; 0 when equal
    tight_range_sessions  consecutive sessions on which the 20-session high-low range / close
                          was at most ``tight_range_pct`` (0.15): the length of the base

A streak counts only while every session in it has a bar (and a known mean or range); it is
capped by the sessions read. Parameters: ``TrendStatsParams`` (``config/site/rollups.toml``
``["trend_stats@v1"]``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, panel, traded_rows
from algotrade.quant.rolling import rolling_max, rolling_mean, rolling_min, trailing_run

NAME = "trend_stats"
VERSION = 1
BARS = "bars/1d"
RETURN_WINDOWS = (120, 252)
SKIP, LONG = 21, 252  # the 12-1 momentum: skip the last month, measure the year before it
Z_WINDOW = 20  # one-session returns the return z-score is measured against
MEAN_WINDOW = 20  # sma20_streak's mean, tight_range_sessions' range
LOOKBACK = LONG  # earlier sessions read: a return over 252 sessions needs the close before
ZERO_STD = 1e-9  # a return stdev under this is rounding noise over equal returns: unknown z
CLOSE, HIGH, LOW = (f"{BARS}.{c}" for c in ("close", "high", "low"))


def _gap(n: int) -> str:
    return f"a session among the last {n} has no bar (a gap), or the history is shorter"


FEATURES = (
    *(
        Feature(
            f"ret_{n}d", "float32", "decimal",
            f"Close / close {n} sessions earlier - 1",
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
        f"ret_z_{Z_WINDOW}d", "float32", "ratio",
        "The session's one-session return (close / previous close - 1) / the sample standard "
        f"deviation (ddof 1) of the {Z_WINDOW} one-session returns before it: the day's "
        "surprise in standard deviations, on the same base as volume_z_20d",
        f"{_gap(Z_WINDOW + 2)}; or those {Z_WINDOW} returns were all equal (zero standard "
        "deviation)",
        inputs=(CLOSE,),
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


def signed_run(diff: Matrix, known: np.ndarray) -> Matrix:
    """The signed trailing run of ``diff``'s sign: rows above 0 count up, below 0 down."""
    up = trailing_run(diff > 0, known)
    down = trailing_run(diff < 0, known)
    return np.where(np.isnan(up), np.nan, np.where(up > 0, up, -down))


def streaks(px: Panel, p: TrendStatsParams) -> dict[str, Matrix]:
    close = px.close
    change = np.diff(close, axis=0)
    known = ~np.isnan(change)
    mean = rolling_mean(close, MEAN_WINDOW)
    width = (rolling_max(px.high, MEAN_WINDOW) - rolling_min(px.low, MEAN_WINDOW)) / close
    tight = width <= p.tight_range_pct
    return {
        "close_streak": signed_run(change, known),
        f"sma{MEAN_WINDOW}_streak": signed_run(close - mean, ~np.isnan(mean)),
        "tight_range_sessions": trailing_run(tight, ~np.isnan(width)),
    }


def compute(inputs: Inputs, session: date, p: TrendStatsParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, LOOKBACK + 1))
    values = {**returns(px.close), f"ret_z_{Z_WINDOW}d": return_z(px.close), **streaks(px, p)}
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"{RETURN_WINDOWS[0]} / {RETURN_WINDOWS[1]}-session returns, the 12-1 momentum, the "
    f"return z-score over {Z_WINDOW} sessions and the close, SMA{MEAN_WINDOW} and "
    "tight-range streaks",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
    params=TrendStatsParams(),
)
