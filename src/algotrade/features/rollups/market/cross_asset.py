"""``market_cross_asset@v1``: stress across an ETF basket and the leadership ratios (ADR 0047).

Input: ``bars/1d`` (split-adjusted as of the session, never dividend-adjusted: price returns)
of ETFs found by ticker through ``instruments/symbol_ids`` (``tickers``). One ``MKT:US`` row
per session.

The basket is ``BASKET`` in that fixed order (columns of the returns panel; never the order of
the ids, so a run is bit-reproducible). A ticker that is not in the reference, or misses a bar
on one of the last 61 sessions, is skipped; ``basket_size`` says how many remain (turbulence
and absorption are null below ``MIN_BASKET``). Returns are daily log returns.

    turbulence_60d          Kritzman-Li turbulence (``quant.covariance.turbulence``): the
                            squared Mahalanobis distance of the session's returns from the
                            mean and covariance of the 60 sessions before it
    absorption_ratio_500d   share of the variance of the last 500 sessions' returns absorbed by
                            the first fifth of the eigenvectors, exponential weights with a
                            250-session half-life (Kritzman, Li, Page and Rigobon 2011)
    absorption_shift        (mean absorption ratio over 15 sessions - mean over 252) / stdev
                            over 252 (the same paper's standardised shift)
    <a>_vs_<b>              (close_a / close_b) / (the same ratio 63 sessions earlier) - 1:
                            ``a``'s relative return over ``b`` (RSP and CPER are optional: null
                            when the reference does not list them)

A window that misses a bar of a basket ticker gives null, never a shorter window or a smaller
basket for that measure.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.tickers import BARS, SYMBOL_IDS, Matrix, closes, ticker_ids
from algotrade.quant.covariance import absorption_ratio, absorption_shift, turbulence

NAME = "market_cross_asset"
VERSION = 1
BASKET = (
    "SPY", "QQQ", "IWM", "TLT", "IEF", "HYG", "LQD", "GLD", "USO",
    "XLY", "XLP", "XLU", "XLK", "XLF",
)  # fmt: skip
RATIOS = (
    ("RSP", "SPY"), ("IWM", "SPY"), ("XLY", "XLP"), ("HYG", "LQD"), ("HYG", "IEF"),
    ("CPER", "GLD"), ("XLU", "SPY"),
)  # fmt: skip
TICKERS = tuple(dict.fromkeys((*BASKET, *(t for pair in RATIOS for t in pair))))
MIN_BASKET = 5
TURBULENCE_WINDOW = 60
AR_WINDOW, AR_HALF_LIFE = 500, 250.0
SHIFT_SHORT, SHIFT_LONG = 15, 252
RATIO_WINDOW = 63
# Returns: the absorption shift needs SHIFT_LONG ratios, each over AR_WINDOW returns.
LOOKBACK = max(AR_WINDOW + SHIFT_LONG - 1, TURBULENCE_WINDOW + 1, RATIO_WINDOW)

CLOSE = f"{BARS}.close"
ID = f"{SYMBOL_IDS}.instrument_id"
_SHORT_BASKET = f"fewer than {MIN_BASKET} basket tickers with a bar on each of the last 61 sessions"


def ratio_column(a: str, b: str) -> str:
    return f"{a.lower()}_vs_{b.lower()}"


FEATURES = (
    Feature(
        "basket_size", "int", "count",
        f"Basket ETFs ({', '.join(BASKET)}) in the reference with a bar on each of the last "
        f"{TURBULENCE_WINDOW + 1} sessions: the columns of turbulence and absorption",
        "never", valid_range=(0, len(BASKET)), inputs=(CLOSE, ID),
    ),
    Feature(
        "turbulence_60d", "float32", "ratio",
        "Kritzman-Li turbulence: squared Mahalanobis distance of the session's basket log "
        f"returns from the mean and covariance of the {TURBULENCE_WINDOW} sessions before it "
        "(about basket_size on an ordinary day)",
        f"{_SHORT_BASKET}, or a direction the window never moved in",
        valid_range=(0, None), inputs=(CLOSE, ID),
    ),
    Feature(
        f"absorption_ratio_{AR_WINDOW}d", "float32", "decimal",
        f"Share of the variance of the last {AR_WINDOW} sessions' basket log returns absorbed "
        f"by the first fifth of the eigenvectors (exponential weights, half-life "
        f"{AR_HALF_LIFE:.0f} sessions)",
        f"{_SHORT_BASKET}, or a basket ETF misses a bar among the last {AR_WINDOW + 1} sessions",
        valid_range=(0, 1), inputs=(CLOSE, ID),
    ),
    Feature(
        "absorption_shift", "float32", "ratio",
        f"Standardised shift of the absorption ratio: (its mean over {SHIFT_SHORT} sessions - "
        f"its mean over {SHIFT_LONG}) / its stdev over {SHIFT_LONG}",
        f"{_SHORT_BASKET}, or a basket ETF misses a bar among the last "
        f"{LOOKBACK + 1} sessions, or the ratio did not move over {SHIFT_LONG} sessions",
        valid_range=(None, None), inputs=(CLOSE, ID),
    ),
    *(
        Feature(
            ratio_column(a, b), "float32", "decimal",
            f"{a} / {b} relative return over {RATIO_WINDOW} sessions: (close {a} / close {b}) / "
            f"the same ratio {RATIO_WINDOW} sessions earlier - 1",
            f"{a} or {b} is not in the reference, or has no bar on the session or "
            f"{RATIO_WINDOW} sessions earlier",
            valid_range=(-1, None), inputs=(CLOSE, ID),
        )
        for a, b in RATIOS
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def stress(close: Matrix) -> dict[str, float]:
    """Basket size, turbulence, absorption ratio and shift for the LAST session; ``close`` is
    sessions x ``BASKET`` (NaN: no bar)."""
    recent = close[-(TURBULENCE_WINDOW + 1) :]
    keep = ~np.isnan(recent).any(axis=0)
    out = {"basket_size": float(keep.sum())}
    nan = dict.fromkeys(("turbulence_60d", f"absorption_ratio_{AR_WINDOW}d", "absorption_shift"))
    if keep.sum() < MIN_BASKET:
        return {**out, **dict.fromkeys(nan, np.nan)}
    returns = np.diff(np.log(close[:, keep]), axis=0)
    ar = absorption_ratio(returns, AR_WINDOW, half_life=AR_HALF_LIFE)
    return {
        **out,
        "turbulence_60d": float(
            turbulence(returns[-(TURBULENCE_WINDOW + 1) :], TURBULENCE_WINDOW)[-1]
        ),
        f"absorption_ratio_{AR_WINDOW}d": float(ar[-1]),
        "absorption_shift": float(absorption_shift(ar, SHIFT_SHORT, SHIFT_LONG)[-1]),
    }


def relative(close: Matrix, a: int, b: int) -> float:
    """``a``'s return over ``b``'s across the last ``RATIO_WINDOW`` sessions (NaN: no bar)."""
    now, then = close[-1], close[-RATIO_WINDOW - 1]
    return float((now[a] / now[b]) / (then[a] / then[b]) - 1.0)


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    days = sessions_ending(session, LOOKBACK + 1)
    matrix = closes(bars, ticker_ids(inputs[SYMBOL_IDS], TICKERS), TICKERS, days)
    column = {t: i for i, t in enumerate(TICKERS)}
    row: dict[str, object] = {"instrument_id": market_id("US")}
    row.update(stress(matrix[:, : len(BASKET)]))
    for a, b in RATIOS:
        row[ratio_column(a, b)] = relative(matrix, column[a], column[b])
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Cross-asset stress over an ETF basket (turbulence, absorption ratio and its shift) and "
    "the leadership ratios' 63-session relative returns",
    (Input(BARS, lookback=LOOKBACK), Input(SYMBOL_IDS, required=False)),
    FEATURES,
    compute,
    entity="market",
)
