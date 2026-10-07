"""``bands@v2``: the EMA stack with its slopes, the stored inputs of Bollinger Bands and
Keltner Channels, the bandwidth percentile (the squeeze) and the band walk, from daily bars
(``docs/data/technical.md``).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``), the
session plus ``LOOKBACK`` (399) earlier sessions. One row per instrument with a bar on the
session.

    ema_10/20/50/200      EMA of the close (alpha 2 / (n + 1)) over the consecutive run of
                          bars ending on the session (at most 400), seeded with the mean of
                          the run's first n closes
    ema20_slope_5d        ema_20 / ema_20 five sessions earlier - 1 (ema50_slope_10d and
                          sma200_slope_20d likewise, over the SMA for the 200)
    close_std_20          sample standard deviation (ddof 1) of the last 20 closes
    bb_width_pctile_252d  share of the 252 sessions before the session whose Bollinger
                          bandwidth (4 x std / SMA) was strictly below the session's
    band_walk             signed consecutive sessions with the close above the upper band
                          (positive) or below the lower (negative); 0 inside

The bands themselves, %B, the Keltner channel (EMA +- 2 ATR), the squeeze, the price z-score,
the EMA distances and alignment are expression features (``config/site/features/bands.toml``)
over these columns, ``price_stats@v2`` and ``momentum@v1``. The windows and the multiplier are
part of the definition: changing one is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Matrix, Panel, bars_rows
from algotrade.quant.rolling import (
    exponential_path,
    rolling_mean,
    rolling_var,
    trailing_percentile,
    trailing_run,
)

NAME = "bands"
VERSION = 2
BARS = "bars/1d"
WINDOW = 20  # closes in a band
MULTIPLIER = 2.0  # standard deviations each side (Bollinger's default)
EMA_WINDOWS = (10, 20, 50, 200)
SMA_EXTRA = (
    150  # the 30-week average (Minervini's template, Weinstein's stages): not in price_stats
)
SLOPES = (("ema", 20, 5), ("ema", 50, 10), ("sma", 200, 20))  # (average, window, horizon)
PCTILE_WINDOW = 252  # sessions before the session the bandwidth is ranked against
MIN_PCTILE = 240  # ... of which this many need a bandwidth
LOOKBACK = 399  # earlier sessions read: the EMA run (400 rows), 252 bandwidths of 20 closes
CLOSE = f"{BARS}.close"
_GAP = f"a session among the last {WINDOW} has no bar (a gap), or the history is shorter"


def _run(n: int) -> str:
    return (
        f"fewer than {n} consecutive bars ending on the session (a gap among the last {n} "
        "sessions, or a shorter history)"
    )


def _slope(kind: str, n: int, h: int) -> Feature:
    what = f"ema_{n}" if kind == "ema" else f"sma_{n}"
    return Feature(
        f"{kind}{n}_slope_{h}d", "float32", "decimal",
        f"{what} / {what} {h} sessions earlier - 1: the average's slope over {h} sessions, "
        "positive when it is rising (0.02 is 2% higher than it was)",
        _run(n + h) if kind == "ema" else f"a session among the last {n + h} has no bar (a "
        "gap), or the history is shorter",
        valid_range=(-1, None), inputs=(CLOSE,),
    )  # fmt: skip


FEATURES = (
    *(
        Feature(
            f"ema_{n}", "float32", "usd_per_share",
            f"Exponential moving average of the close, alpha 2 / {n + 1}, over the consecutive "
            f"bars ending on the session (at most the last {LOOKBACK + 1} sessions), seeded with "
            f"the mean of the run's first {n} closes"
            + (": the Keltner channel's midline" if n == WINDOW else ""),
            _run(n), valid_range=(0, None), inputs=(CLOSE,),
        )
        for n in EMA_WINDOWS
    ),
    Feature(
        f"sma_{SMA_EXTRA}", "float32", "usd_per_share",
        f"Mean close over the last {SMA_EXTRA} sessions (the 30-week average of Minervini's "
        "trend template and Weinstein's stage analysis; price_stats has the 20 / 50 / 200)",
        f"a session among the last {SMA_EXTRA} has no bar (a gap), or the history is shorter",
        valid_range=(0, None), inputs=(CLOSE,),
    ),
    *(_slope(kind, n, h) for kind, n, h in SLOPES),
    Feature(
        f"close_std_{WINDOW}", "float32", "usd_per_share",
        f"Sample standard deviation (ddof 1) of the last {WINDOW} closes, the session "
        f"included: the half-width of a one-sigma Bollinger band around sma_{WINDOW}",
        _GAP, valid_range=(0, None), inputs=(CLOSE,),
    ),
    Feature(
        f"bb_width_pctile_{PCTILE_WINDOW}d", "float32", "decimal",
        f"Share of the {PCTILE_WINDOW} sessions before the session whose Bollinger bandwidth "
        f"(2 x {MULTIPLIER:.0f} x close_std_{WINDOW} / sma_{WINDOW}) was strictly below the "
        "session's: 0.05 is a squeeze (narrower than 95% of the year), 0.95 an expansion",
        f"the session's bandwidth is unknown ({_GAP}), or fewer than {MIN_PCTILE} of the "
        f"{PCTILE_WINDOW} sessions before it have one",
        valid_range=(0, 1), inputs=(CLOSE,),
    ),
    Feature(
        "band_walk", "int", "sessions",
        "Signed count of consecutive sessions, ending on the session, with the close above "
        f"the upper Bollinger band (sma_{WINDOW} + {MULTIPLIER:.0f} x close_std_{WINDOW}; "
        "positive) or below the lower band (negative); 0 when the close is inside the bands; "
        "the count stops at the first session whose bands are unknown",
        f"the session's bands are unknown ({_GAP})", valid_range=(-LOOKBACK, LOOKBACK),
        inputs=(CLOSE,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def band_edges(close: Matrix) -> tuple[Matrix, Matrix, Matrix, Matrix]:
    """Per row (sessions x instruments): ``(sma, std, upper, lower)`` of the window ending at
    it; NaN until the window is full or when it has a gap."""
    sma = rolling_mean(close, WINDOW)
    std = np.sqrt(rolling_var(close, WINDOW))
    return sma, std, sma + MULTIPLIER * std, sma - MULTIPLIER * std


def width_percentile(sma: Matrix, std: Matrix) -> Matrix:
    """For the last row: the share of the ``PCTILE_WINDOW`` rows before it with a known
    bandwidth strictly below the last row's; NaN below ``MIN_PCTILE`` known rows."""
    with np.errstate(divide="ignore", invalid="ignore"):
        width = np.where(sma > 0, 2 * MULTIPLIER * std / sma, np.nan)
    return trailing_percentile(width, PCTILE_WINDOW, MIN_PCTILE)


def band_walk(close: Matrix, upper: Matrix, lower: Matrix) -> Matrix:
    """For the last row: the signed trailing run of closes outside the bands."""
    known = ~np.isnan(upper) & ~np.isnan(close)
    up = trailing_run(close > upper, known)
    down = trailing_run(close < lower, known)
    return np.where(np.isnan(up), np.nan, np.where(up > 0, up, -down))


def slope(path: Matrix, horizon: int) -> Matrix:
    """For the last row: ``path[-1] / path[-1 - horizon] - 1`` (NaN when either is)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(path[-1] / path[-1 - horizon] - 1.0)


def stats(px: Panel) -> dict[str, Matrix]:
    sma, std, upper, lower = band_edges(px.close)
    emas = {n: exponential_path(px.close, n) for n in EMA_WINDOWS}
    out: dict[str, Matrix] = {f"ema_{n}": path[-1] for n, path in emas.items()}
    out[f"sma_{SMA_EXTRA}"] = rolling_mean(px.close, SMA_EXTRA)[-1]
    for kind, n, h in SLOPES:
        path = emas[n] if kind == "ema" else rolling_mean(px.close, n)
        out[f"{kind}{n}_slope_{h}d"] = slope(path, h)
    out[f"close_std_{WINDOW}"] = std[-1]
    out[f"bb_width_pctile_{PCTILE_WINDOW}d"] = width_percentile(sma, std)
    out["band_walk"] = band_walk(px.close, upper, lower)
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    return bars_rows(inputs, session, LOOKBACK, stats, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"The EMA stack ({', '.join(str(n) for n in EMA_WINDOWS)}) with slopes, the "
    f"{SMA_EXTRA}-session SMA, the {WINDOW}-close "
    f"standard deviation, the bandwidth percentile over {PCTILE_WINDOW} sessions (the squeeze) "
    "and the band walk",
    (Input(BARS, lookback=LOOKBACK),),
    FEATURES,
    compute,
)
