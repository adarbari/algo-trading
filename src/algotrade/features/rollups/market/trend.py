"""``market_trend@v1``: the trend of the two US index proxies, SPY and QQQ (ADR 0047).

Input: ``bars/1d`` (split-adjusted as of the session, never dividend-adjusted: a price
return, like ``price_stats@v2``) of SPY (columns ``spx_``) and QQQ (``ndx_``), found by ticker
through ``instruments/symbol_ids`` (``tickers``). One ``MKT:US`` row per session.

A column is null (UNKNOWN), never a shorter window, unless the ticker is in the reference and
has a bar on every session of the column's window (sessions from ``core.time.calendar``):

    <p>_close_vs_sma200    close / mean close over 200 sessions - 1
    <p>_sma50_vs_sma200    sma50 / sma200 - 1 (below 0: a "death cross")
    <p>_drawdown_252d      close / highest close of the last 252 sessions - 1
                           (``quant.turning_points.drawdowns`` over that window)
    <p>_realised_vol_20d   sample stdev of the last 20 log returns x sqrt(252)
                           (``quant.realized_vol.close_to_close``)
    <p>_ret_21d, _ret_252d close / close 21 (252) sessions earlier - 1

The windows are part of the definition (named in the columns): changing one is a new version.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.tickers import BARS, SYMBOL_IDS, Matrix, closes, ticker_ids
from algotrade.quant import realized_vol
from algotrade.quant.turning_points import drawdowns

NAME = "market_trend"
VERSION = 1
INDEXES = {"spx": "SPY", "ndx": "QQQ"}  # column prefix -> the ticker that tracks the index
SMA_LONG, SMA_SHORT = 200, 50
DRAWDOWN_WINDOW = 252
VOL_WINDOW = 20
RETURN_WINDOWS = (21, 252)
PERIODS_PER_YEAR = 252
LOOKBACK = max(SMA_LONG, DRAWDOWN_WINDOW, VOL_WINDOW + 1, *(n + 1 for n in RETURN_WINDOWS)) - 1

CLOSE = f"{BARS}.close"
ID = f"{SYMBOL_IDS}.instrument_id"


def _short(prefix: str, n: int) -> str:
    return (
        f"{INDEXES[prefix]} is not in the reference snapshot, or has no bar on a session among "
        f"the last {n} (a short history or a gap)"
    )


def _features(p: str) -> tuple[Feature, ...]:
    t = INDEXES[p]
    return (
        Feature(
            f"{p}_close_vs_sma200", "float32", "decimal",
            f"{t} close / its mean close over the last {SMA_LONG} sessions - 1 (below 0: under "
            "the 200-day average)",
            _short(p, SMA_LONG), valid_range=(-1, None), inputs=(CLOSE, ID),
        ),
        Feature(
            f"{p}_sma50_vs_sma200", "float32", "decimal",
            f"{t} {SMA_SHORT}-session mean close / {SMA_LONG}-session mean close - 1 (below 0: a "
            "death cross)",
            _short(p, SMA_LONG), valid_range=(-1, None), inputs=(CLOSE, ID),
        ),
        Feature(
            f"{p}_drawdown_252d", "float32", "decimal",
            f"{t} close / its highest close over the last {DRAWDOWN_WINDOW} sessions - 1 (0 at a "
            "new high, -0.2 a bear market's threshold)",
            _short(p, DRAWDOWN_WINDOW), valid_range=(-1, 0), inputs=(CLOSE, ID),
        ),
        Feature(
            f"{p}_realised_vol_20d", "float32", "decimal",
            f"{t} close-to-close realised volatility: sample stdev of the last {VOL_WINDOW} log "
            "returns x sqrt(252)",
            _short(p, VOL_WINDOW + 1), valid_range=(0, 5), inputs=(CLOSE, ID),
        ),
        *(
            Feature(
                f"{p}_ret_{n}d", "float32", "decimal",
                f"{t} close / close {n} sessions earlier - 1 (price return, no dividends)",
                _short(p, n + 1), valid_range=(-1, None), inputs=(CLOSE, ID),
            )
            for n in RETURN_WINDOWS
        ),
    )  # fmt: skip


FEATURES = tuple(f for prefix in INDEXES for f in _features(prefix))
COLUMNS = column_types(FEATURES)


def _complete(window: Matrix) -> bool:
    return bool(len(window) and not np.isnan(window).any())


def index_trend(close: Matrix) -> dict[str, float]:
    """Every column (without its prefix) for the LAST session of one ticker's closes."""
    last = close[-1]
    out = dict.fromkeys(
        ("close_vs_sma200", "sma50_vs_sma200", "drawdown_252d", "realised_vol_20d"), np.nan
    )
    if _complete(close[-SMA_LONG:]):
        sma_long = close[-SMA_LONG:].mean()
        out["close_vs_sma200"] = last / sma_long - 1.0
        out["sma50_vs_sma200"] = close[-SMA_SHORT:].mean() / sma_long - 1.0
    if _complete(close[-DRAWDOWN_WINDOW:]):
        out["drawdown_252d"] = float(drawdowns(close[-DRAWDOWN_WINDOW:])[-1])
    vol = close[-VOL_WINDOW - 1 :]
    if _complete(vol):
        out["realised_vol_20d"] = float(
            realized_vol.close_to_close(vol, VOL_WINDOW, PERIODS_PER_YEAR)[-1]
        )
    for n in RETURN_WINDOWS:
        window = close[-n - 1 :]
        out[f"ret_{n}d"] = last / window[0] - 1.0 if _complete(window) else np.nan
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    days = sessions_ending(session, LOOKBACK + 1)
    tickers = list(INDEXES.values())
    matrix = closes(bars, ticker_ids(inputs[SYMBOL_IDS], tickers), tickers, days)
    row: dict[str, object] = {"instrument_id": market_id("US")}
    for j, prefix in enumerate(INDEXES):
        for column, value in index_trend(matrix[:, j]).items():
            row[f"{prefix}_{column}"] = value
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Index trend of SPY and QQQ: distance from the 200-day average, death cross, drawdown "
    "from the 52-week closing high, realised vol and returns",
    (
        Input(BARS, lookback=LOOKBACK, symbols=tuple(INDEXES.values())),
        Input(SYMBOL_IDS, required=False),
    ),
    FEATURES,
    compute,
    entity="market",
)
