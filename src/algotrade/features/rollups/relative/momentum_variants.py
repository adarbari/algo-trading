"""``momentum_variants@v1``: the momentum factor's variants that need more than one stored
number: the 12-1 and 1-month returns net of SPY (residual), the information discreteness of the
12-1 path, and the sector ETF's 12-month return with the 1-month return against it.

Input: ``bars/1d`` split-adjusted as of the session, 252 sessions back; ``instruments/
symbol_ids`` (SPY and the sector ETFs, ADR 0018: never built); ``relative_strength@v1``'s
``sector_etf`` of the session (the sector map lives there, once). Everything reads closes up to
the session only: the 12-1 window ends 21 sessions back, and the betas use the same closes the
returns do, so nothing sees a later bar. The volatility-scaled momentum is an expression
feature (``config/site/features/technical/price.toml``), not computed here.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.tickers import BARS, SYMBOL_IDS, Matrix, ticker_ids
from algotrade.features.rollups.price.episodes import beta_corr
from algotrade.features.rollups.price.price_stats import panel, symbol_column, traded_rows
from algotrade.features.rollups.price.trend_stats import LONG, SKIP
from algotrade.features.rollups.relative.relative_strength import (
    BENCHMARK,
    ETFS,
    relative,
    ret,
)

NAME = "momentum_variants"
VERSION = 1
RELATIVE = "rollups/instrument/relative_strength@v1"
MONTH = 20  # sessions of the 1-month return (price_stats.ret_20d)
LOOKBACK = LONG  # earlier sessions read: the 12-1 window starts 252 sessions back
_GAP = "a session in the window has no bar (a gap), or the history is shorter"
_NO_SPY = f"{BENCHMARK} is not in the symbol map or has no bars, or its own window has a gap"
_BETA = "the instrument has fewer than 200 of the window's returns (or SPY does)"
_MKT = f"{BENCHMARK}'s"

FEATURES = (
    Feature(
        "resid_mom_12_1", "float32", "decimal",
        "The 12-1 momentum net of the market: ln(close 21 sessions back / close 252 sessions "
        f"back) minus beta times {_MKT} same log return, beta the OLS slope of the instrument's "
        f"daily log returns on {_MKT} over that same window (no intercept is removed). 0.15 is "
        "15 points of log return beyond what the market's own move explains. A market-only, "
        "unscaled approximation of Blitz, Huij and Martens' residual momentum (they use 36-month "
        "Fama-French residuals scaled by their stdev)",
        f"a session from 252 to 21 sessions back has no bar for the instrument ({_GAP}), "
        f"{_NO_SPY}, or {_BETA}",
        valid_range=(-5, 5), inputs=(f"{BARS}.close", f"{SYMBOL_IDS}.instrument_id"),
    ),
    Feature(
        "fip_12_1", "float32", "ratio",
        "Information discreteness of the 12-1 path: sign(12-1 return) x (share of down days - "
        "share of up days) over the 12-1 window's daily returns. Below 0 the winners rose on "
        "many small up days (continuous, 'frog in the pan'); above 0 they rose on a few big "
        "jumps (discrete); -0.2 is 20 points more up days than down days in an up move",
        f"a session from 252 to 21 sessions back has no bar ({_GAP})",
        valid_range=(-1, 1), inputs=(f"{BARS}.close",),
    ),
    Feature(
        f"resid_ret_{MONTH}d", "float32", "decimal",
        f"The {MONTH}-session return net of the market (residual 1-month return): the log "
        f"return over {MONTH} sessions minus beta_252d times {_MKT} over the same sessions "
        "(beta from the trailing 252 sessions, the rollup beta_252d). Positive: the name beat "
        "what its market exposure explains; a high value tends to reverse next month",
        f"a session among the last {MONTH + 1} has no bar ({_GAP}), {_NO_SPY}, or {_BETA}",
        valid_range=(-5, 5), inputs=(f"{BARS}.close", f"{SYMBOL_IDS}.instrument_id"),
    ),
    Feature(
        f"sector_ret_{LONG}d", "float32", "decimal",
        f"The {LONG}-session return of the instrument's sector ETF (close / close {LONG} "
        "sessions earlier - 1): how the sector as a whole has done over a year",
        f"relative_strength@v1's sector_etf is null for the session, or the ETF is not in the "
        f"symbol map or has a gap in its {LONG + 1} closes",
        valid_range=(-1, None), inputs=("relative_strength.sector_etf@v1", f"{BARS}.close"),
    ),
    Feature(
        f"rs_sector_{MONTH}d", "float32", "decimal",
        f"The {MONTH}-session return against the sector ETF's: (1 + the instrument's return) / "
        "(1 + the ETF's) - 1. A sector-adjusted 1-month return (the sector is the SEC SIC code's "
        "coarse market sector, the nearest industry proxy stored); 0.05 beat its sector by 5 "
        "points",
        f"sector_etf is null, the ETF has a gap in its last {MONTH + 1} closes, or the "
        f"instrument has ({_GAP})",
        valid_range=(-1, None), inputs=("relative_strength.sector_etf@v1", f"{BARS}.close"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _log_gain(close: Matrix, first: int, last: int) -> Matrix:
    """ln(close[last] / close[first]) per column; NaN unless every close from ``first`` to
    ``last`` exists (negative row numbers count from the session)."""
    window = close[first : last + 1 if last != -1 else None]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(window[-1] / window[0])
    return np.where(~np.isnan(window).any(axis=0) & np.isfinite(out), out, np.nan)


def residual(close: Matrix, market: int | None, first: int, last: int, beta: Matrix) -> Matrix:
    """The log gain between rows ``first`` and ``last`` minus ``beta`` times the market's."""
    if market is None:
        return np.full(close.shape[1], np.nan)
    gain = _log_gain(close, first, last)
    out: Matrix = gain - beta * _log_gain(close[:, [market]], first, last)[0]
    return out


def discreteness(close: Matrix) -> Matrix:
    """sign(12-1 return) x (share of down days - share of up days) over the 12-1 window's
    daily returns; NaN unless the window is complete."""
    window = close[-LONG - 1 : -SKIP]
    complete = ~np.isnan(window).any(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        daily = window[1:] / window[:-1] - 1.0
        gain = window[-1] / window[0] - 1.0
    down = (daily < 0).mean(axis=0)
    up = (daily > 0).mean(axis=0)
    out = np.sign(gain) * (down - up)
    return np.where(complete & np.isfinite(out), out, np.nan)


def compute(inputs: Inputs, session: date, p: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, LOOKBACK + 1))
    symbols = inputs[SYMBOL_IDS]
    spy = symbol_column(symbols, px.ids, BENCHMARK)
    n = len(px.ids)
    nan = np.full(n, np.nan)
    formation_beta = beta_corr(px.close[:-SKIP], spy)[0] if spy is not None else nan
    month_beta = beta_corr(px.close, spy)[0] if spy is not None else nan
    values: dict[str, np.ndarray] = {
        "resid_mom_12_1": residual(px.close, spy, -LONG - 1, -SKIP - 1, formation_beta),
        "fip_12_1": discreteness(px.close),
        f"resid_ret_{MONTH}d": residual(px.close, spy, -MONTH - 1, -1, month_beta),
        f"sector_ret_{LONG}d": nan.copy(),
        f"rs_sector_{MONTH}d": nan.copy(),
    }
    values |= _sector_columns(px.ids, px.close, symbols, inputs[RELATIVE])
    return traded_rows(px, values, COLUMNS)


def _sector_columns(
    ids: np.ndarray, close: Matrix, symbols: pd.DataFrame | None, rel: pd.DataFrame | None
) -> dict[str, np.ndarray]:
    """The sector ETF's 252-session return and the 20-session return against it, per
    instrument, through ``relative_strength@v1``'s ``sector_etf`` of the session."""
    n = len(ids)
    out = {f"sector_ret_{LONG}d": np.full(n, np.nan), f"rs_sector_{MONTH}d": np.full(n, np.nan)}
    if rel is None or "sector_etf" not in rel.columns:
        return out
    etf_ids = ticker_ids(symbols, ETFS)
    column = {iid: i for i, iid in enumerate(ids)}
    long_ret: dict[str, float] = {}
    month_ret: dict[str, float] = {}
    for ticker, iid in etf_ids.items():
        if iid in column:
            series = close[:, [column[iid]]]
            long_ret[ticker] = float(ret(series, LONG)[0])
            month_ret[ticker] = float(ret(series, MONTH)[0])
    own_month = ret(close, MONTH)
    sector = dict(zip(rel["instrument_id"].astype(str), rel["sector_etf"], strict=True))
    for i, iid in enumerate(ids):
        etf = sector.get(iid)
        if not isinstance(etf, str) or etf not in long_ret:
            continue
        out[f"sector_ret_{LONG}d"][i] = long_ret[etf]
        out[f"rs_sector_{MONTH}d"][i] = relative(own_month[i], month_ret[etf])
    return out


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The momentum factor's variants: the 12-1 and 1-month returns net of SPY (residual), the "
    "information discreteness of the 12-1 path, the sector ETF's 12-month return and the "
    "1-month return against it",
    (
        Input(BARS, lookback=LOOKBACK),
        Input(SYMBOL_IDS, required=False),
        Input(RELATIVE, required=False),
    ),
    FEATURES,
    compute,
    None,
)
