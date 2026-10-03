"""``price_stats@v1``: trend, range, realised volatility and dollar volume from daily bars.

Input: ``bars/1d`` split-adjusted AS OF the session (``data.prices.session_bars``; never total
return), the session plus enough earlier sessions for the longest window. One row per
instrument with a bar on the session.

Windows are exchange sessions (``core.time.calendar``), not "the instrument's last n bars":
a session without a bar is a gap. A statistic is null (UNKNOWN), never zero or a shorter
window, unless every session of its window has a bar; the 52-week high / low need at least
``min_year_sessions`` bars among the last ``year_sessions`` sessions.

    close               the session's close
    sma_20/50/200       mean close over the last 20 / 50 / 200 sessions
    ret_20d/60d         close / close 20 (60) sessions earlier - 1
    high_52w, low_52w   highest high / lowest low over the last ``year_sessions`` sessions
    pct_from_high_52w   close / high_52w - 1 (<= 0);  pct_from_low_52w: close / low_52w - 1
    hv20, hv30          close-to-close realised vol (``quant.realized_vol``), annualised
    hv20_yz             Yang-Zhang realised vol over 20 sessions
    adv_usd_20d         mean of close x volume over 20 sessions (split-invariant)
    history_days        sessions with a bar among the last ``year_sessions``

The windows named in the columns (20, 50, 200, 60, 30) are the v1 definition: changing one
is a new version. ``config/site/rollups.toml ["price_stats@v1"]`` sets the 52-week length,
its minimum bars and the annualisation.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import Input, Inputs, Rollup
from algotrade.quant import realized_vol

type Matrix = npt.NDArray[np.float64]

NAME = "price_stats"
VERSION = 1
BARS = "bars/1d"
SMA_WINDOWS = (20, 50, 200)
RETURN_WINDOWS = (20, 60)
HV_WINDOWS = (20, 30)
YZ_WINDOW = 20
ADV_WINDOW = 20

COLUMNS: dict[str, str] = {
    "close": "float",
    **{f"sma_{n}": "float" for n in SMA_WINDOWS},
    **{f"ret_{n}d": "float" for n in RETURN_WINDOWS},
    "high_52w": "float",
    "low_52w": "float",
    "pct_from_high_52w": "float",
    "pct_from_low_52w": "float",
    **{f"hv{n}": "float" for n in HV_WINDOWS},
    f"hv{YZ_WINDOW}_yz": "float",
    f"adv_usd_{ADV_WINDOW}d": "float",
    "history_days": "int",
}


@dataclass(frozen=True)
class PriceStatsParams:
    year_sessions: int = 252  # the 52-week window, in sessions
    min_year_sessions: int = 240  # bars needed in that window for high_52w / low_52w
    periods_per_year: int = 252  # realised-vol annualisation

    def __post_init__(self) -> None:
        if self.year_sessions < 2:
            raise ValueError(f"year_sessions must be >= 2, got {self.year_sessions}")
        if not 1 <= self.min_year_sessions <= self.year_sessions:
            raise ValueError("min_year_sessions must be between 1 and year_sessions")
        if self.periods_per_year < 1:
            raise ValueError("periods_per_year must be >= 1")


def lookback(p: PriceStatsParams) -> int:
    """Earlier sessions needed: the longest window (a return needs one close before it)."""
    longest = max(p.year_sessions, *SMA_WINDOWS, *(n + 1 for n in RETURN_WINDOWS))
    return max(longest, *(n + 1 for n in (*HV_WINDOWS, YZ_WINDOW))) - 1


@dataclass(frozen=True)
class Panel:
    """Bars as sessions x instruments matrices (NaN: no bar that session)."""

    ids: npt.NDArray[np.str_]
    open: Matrix
    high: Matrix
    low: Matrix
    close: Matrix
    volume: Matrix


def panel(bars: pd.DataFrame, days: list[date]) -> Panel:
    """Pivot a bars frame onto the session axis ``days`` (bars outside it are ignored)."""
    codes, ids = pd.factorize(bars["instrument_id"].astype(str), sort=True)
    day_codes, seen = pd.factorize(bars["session_date"])  # few distinct sessions: map those
    rows = pd.Index(days).get_indexer(pd.Index(seen))[day_codes]
    keep = rows >= 0
    shape = (len(days), len(ids))

    def matrix(column: str) -> Matrix:
        out = np.full(shape, np.nan)
        out[rows[keep], codes[keep]] = bars[column].to_numpy(dtype=np.float64)[keep]
        return out

    return Panel(
        np.asarray(ids, dtype=str), *(matrix(c) for c in ("open", "high", "low", "close", "volume"))
    )


def _complete(window: Matrix) -> npt.NDArray[np.bool_]:
    return ~np.isnan(window).any(axis=0)


def _mean(window: Matrix) -> Matrix:
    """Column means; NaN for a column with a gap (``np.mean`` propagates NaN)."""
    return window.mean(axis=0)


def stats(px: Panel, p: PriceStatsParams) -> dict[str, Matrix]:
    """Every column for the LAST session of the panel, one value per instrument."""
    close, high, low = px.close, px.high, px.low
    last = close[-1]
    out: dict[str, Matrix] = {"close": last}
    for n in SMA_WINDOWS:
        out[f"sma_{n}"] = _mean(close[-n:])
    for n in RETURN_WINDOWS:
        ret = last / close[-n - 1] - 1.0
        out[f"ret_{n}d"] = np.where(_complete(close[-n - 1 :]), ret, np.nan)
    year = slice(-p.year_sessions, None)
    bars_in_year = (~np.isnan(close[year])).sum(axis=0)
    enough = bars_in_year >= p.min_year_sessions
    out["high_52w"] = np.where(enough, np.fmax.reduce(high[year], axis=0), np.nan)
    out["low_52w"] = np.where(enough, np.fmin.reduce(low[year], axis=0), np.nan)
    out["pct_from_high_52w"] = last / out["high_52w"] - 1.0
    out["pct_from_low_52w"] = last / out["low_52w"] - 1.0
    for n in HV_WINDOWS:
        out[f"hv{n}"] = realized_vol.close_to_close(close[-n - 1 :], n, p.periods_per_year)[-1]
    w = slice(-YZ_WINDOW - 1, None)
    out[f"hv{YZ_WINDOW}_yz"] = realized_vol.yang_zhang(
        px.open[w], high[w], low[w], close[w], YZ_WINDOW, p.periods_per_year
    )[-1]
    out[f"adv_usd_{ADV_WINDOW}d"] = _mean(close[-ADV_WINDOW:] * px.volume[-ADV_WINDOW:])
    out["history_days"] = bars_in_year.astype(np.float64)
    return out


def compute(inputs: Inputs, session: date, p: PriceStatsParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, lookback(p) + 1))
    traded = ~np.isnan(px.close[-1])
    values = stats(px, p)
    frame = pd.DataFrame({"instrument_id": px.ids[traded]})
    for column in COLUMNS:
        frame[column] = values[column][traded]
    frame["history_days"] = frame["history_days"].astype(np.int64)
    return frame


ROLLUP = Rollup(
    NAME,
    VERSION,
    "Close, moving averages, returns, 52-week range, realised vol and dollar volume",
    (Input(BARS, lookback=lookback),),
    COLUMNS,
    compute,
    PriceStatsParams(),
)
