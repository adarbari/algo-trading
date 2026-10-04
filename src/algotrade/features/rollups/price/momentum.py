"""``momentum@v1``: Wilder ATR and RSI, the 5-session return, relative volume and the 20 / 50
session high-low channel, from daily bars (``docs/data/swing.md``).

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``: prices
divided and volume multiplied by the splits up to the session, never a later one), the
session plus ``WARMUP - 1`` earlier sessions. One row per instrument with a bar on the session.

Windows are exchange sessions (``core.time.calendar``): a window statistic is null (UNKNOWN),
never a shorter window, unless every session of it has a bar.

    atr_14          Wilder average true range: seed with the mean of the first 14 true ranges,
                    then ATR = (13 x ATR + TR) / 14, over the consecutive bars ending on the
                    session (at most WARMUP sessions: a fixed warm-up, so the value depends on
                    the last WARMUP sessions only). TR = max(H - L, |H - C_prev|, |L - C_prev|)
    rsi_14          Wilder RSI over the same run: 100 - 100 / (1 + avg_gain / avg_loss); 100
                    when avg_loss is 0 and avg_gain is not, null when both are 0 (no move)
    ret_5d          close / close 5 sessions earlier - 1
    rel_volume      volume / mean volume of the 20 sessions BEFORE the session
    high_20d/50d    highest high over the last 20 (50) sessions, the session included
    low_20d/50d     lowest low over the last 20 (50) sessions, the session included
    prior_high_20d  highest high over the 20 sessions before the session (for breakout_20d)

The windows named in the columns (14, 5, 20, 50) and the warm-up are part of the definition:
changing one is a new version. Formulas over these columns (``atr_pct``, ``range_20d_pct``,
``trend_state``, ...) are expression features (``config/site/features/swing.toml``).
"""

from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Panel, panel

type Matrix = npt.NDArray[np.float64]

NAME = "momentum"
VERSION = 1
BARS = "bars/1d"
PERIOD = 14  # Wilder ATR and RSI
WARMUP = 150  # sessions the Wilder recursions run over (at most): seed weight (13/14)^136
RETURN_WINDOW = 5
VOLUME_WINDOW = 20
CHANNELS = (20, 50)

CLOSE, HIGH, LOW, VOLUME = (f"{BARS}.{c}" for c in ("close", "high", "low", "volume"))
_RUN = (
    f"fewer than {PERIOD + 1} consecutive bars ending on the session (a gap among the last "
    f"{PERIOD + 1} sessions, or a shorter history)"
)


def _gap(n: int) -> str:
    return f"a session among the last {n} has no bar (a gap), or the history is shorter"


FEATURES = (
    Feature(
        f"atr_{PERIOD}", "float32", "usd_per_share",
        f"Wilder average true range ({PERIOD}): seeded with the mean of the first {PERIOD} "
        f"true ranges, then (13 x ATR + TR) / {PERIOD}, over the consecutive bars ending on "
        f"the session (at most the last {WARMUP} sessions); TR = max(high - low, |high - "
        "previous close|, |low - previous close|)",
        _RUN, valid_range=(0, None), inputs=(HIGH, LOW, CLOSE),
    ),
    Feature(
        f"rsi_{PERIOD}", "float32", "pct_points",
        f"Wilder RSI ({PERIOD}) of close changes over the same run as atr_{PERIOD}: 100 - 100 "
        "/ (1 + average gain / average loss); 100 when there was no loss",
        f"{_RUN}; or the close never moved over the run (no gain and no loss: 0/0)",
        valid_range=(0, 100), inputs=(CLOSE,),
    ),
    Feature(
        f"ret_{RETURN_WINDOW}d", "float32", "decimal",
        f"Close / close {RETURN_WINDOW} sessions earlier - 1",
        _gap(RETURN_WINDOW + 1), valid_range=(-1, None), inputs=(CLOSE,),
    ),
    Feature(
        "rel_volume", "float32", "ratio",
        f"The session's volume / the mean volume of the {VOLUME_WINDOW} sessions before it "
        "(the session excluded): 1.8 is 80% above normal; 0 on a day without trades",
        f"{_gap(VOLUME_WINDOW + 1)}; or those {VOLUME_WINDOW} sessions had no volume at all",
        valid_range=(0, None), inputs=(VOLUME,),
    ),
    *(
        f
        for n in CHANNELS
        for f in (
            Feature(
                f"high_{n}d", "float32", "usd_per_share",
                f"Highest daily high over the last {n} sessions, the session included",
                _gap(n), valid_range=(0, None), inputs=(HIGH,),
            ),
            Feature(
                f"low_{n}d", "float32", "usd_per_share",
                f"Lowest daily low over the last {n} sessions, the session included",
                _gap(n), valid_range=(0, None), inputs=(LOW,),
            ),
        )
    ),
    Feature(
        f"prior_high_{CHANNELS[0]}d", "float32", "usd_per_share",
        f"Highest daily high over the {CHANNELS[0]} sessions before the session (the session "
        "excluded): the level a breakout close must clear",
        f"a session among the {CHANNELS[0]} before the session has no bar (a gap), or the "
        "history is shorter", valid_range=(0, None), inputs=(HIGH,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def wilder(values: Matrix, first: npt.NDArray[np.int64], period: int) -> Matrix:
    """Per column of a sessions x instruments matrix, Wilder's average at the LAST row of the
    values from row ``first`` on (earlier rows are ignored): the mean of the first ``period``
    values, then ``(avg x (period - 1) + x) / period`` for each later one. NaN for a column
    with fewer than ``period`` values."""
    total = np.zeros(values.shape[1])
    avg = np.full(values.shape[1], np.nan)
    for i, row in enumerate(values):
        k = i - first + 1  # values seen so far, row i included
        total = np.where((k >= 1) & (k <= period), total + row, total)
        avg = np.where(k == period, total / period, avg)
        avg = np.where(k > period, (avg * (period - 1) + row) / period, avg)
    return np.where(len(values) - first >= period, avg, np.nan)


def run_start(close: Matrix) -> npt.NDArray[np.int64]:
    """Per column, the first row of the consecutive bars ending on the last row."""
    rows = np.arange(len(close))[:, None]
    return (np.where(np.isnan(close), rows, -1).max(axis=0) + 1).astype(np.int64)


def wilder_atr_rsi(px: Panel) -> tuple[Matrix, Matrix]:
    """``(atr, rsi)`` for the last row, over each column's consecutive run of bars."""
    close, high, low = px.close, px.high, px.low
    prev = np.vstack([np.full((1, close.shape[1]), np.nan), close[:-1]])
    true_range = np.fmax(high - low, np.fmax(np.abs(high - prev), np.abs(low - prev)))
    change = close - prev
    first = run_start(close) + 1  # a true range or change needs the previous close
    atr = wilder(true_range, first, PERIOD)
    gain = wilder(np.clip(change, 0, None), first, PERIOD)
    loss = wilder(np.clip(-change, 0, None), first, PERIOD)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(loss > 0, 100 - 100 / (1 + gain / loss), np.where(gain > 0, 100.0, np.nan))
    return atr, rsi


def _if_complete(value: Matrix, window: Matrix) -> Matrix:
    """``value`` for columns where every row of ``window`` has a bar, else NaN."""
    return np.where(~np.isnan(window).any(axis=0), value, np.nan)


def channels(px: Panel) -> dict[str, Matrix]:
    """The return, relative volume and high-low channels for the last row (NaN on a gap:
    ``max``, ``min`` and ``mean`` propagate NaN)."""
    close, high, low, volume = px.close, px.high, px.low, px.volume
    n = RETURN_WINDOW
    out = {f"ret_{n}d": _if_complete(close[-1] / close[-n - 1] - 1.0, close[-n - 1 :])}
    normal = volume[-VOLUME_WINDOW - 1 : -1].mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["rel_volume"] = np.where(normal > 0, volume[-1] / normal, np.nan)
    for w in CHANNELS:
        out[f"high_{w}d"] = high[-w:].max(axis=0)
        out[f"low_{w}d"] = low[-w:].min(axis=0)
    out[f"prior_high_{CHANNELS[0]}d"] = high[-CHANNELS[0] - 1 : -1].max(axis=0)
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WARMUP))
    traded = ~np.isnan(px.close[-1])
    atr, rsi = wilder_atr_rsi(px)
    values = {f"atr_{PERIOD}": atr, f"rsi_{PERIOD}": rsi, **channels(px)}
    frame = pd.DataFrame({"instrument_id": px.ids[traded]})
    for column in COLUMNS:
        frame[column] = values[column][traded]
    return frame


GROUP = FeatureGroup(
    NAME,
    VERSION,
    f"Wilder ATR and RSI ({PERIOD}), {RETURN_WINDOW}-session return, relative volume and the "
    "20 / 50-session high-low channel",
    (Input(BARS, lookback=WARMUP - 1),),
    FEATURES,
    compute,
)
