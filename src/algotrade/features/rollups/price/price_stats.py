"""``price_stats@v2``: trend, range, realised volatility and dollar volume from daily bars.

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
    high_52w, low_52w   highest high / lowest low over the last ``year_sessions`` sessions, on
                        split-adjusted prices, NOT dividend-adjusted (decided 2026-10-03 after
                        the IBKR comparison: IBKR's 52-week range is dividend-adjusted, so on a
                        payer its values sit below ours by up to the dividends since the bar)
    hv20, hv30          close-to-close realised vol (``quant.realized_vol``): sample stdev
                        of the last 20 / 30 log returns x sqrt(252) (IBKR's own HV uses another
                        estimator and differs)
    hv20_yz             Yang-Zhang realised vol over 20 sessions
    adv_usd_20d         mean of close x volume over 20 sessions (split-invariant)
    history_days        sessions with a bar among the last ``year_sessions``

The windows named in the columns (20, 50, 200, 60, 30) are part of the definition: changing
one is a new version. ``config/site/rollups.toml ["price_stats@v2"]`` sets the 52-week length,
its minimum bars and the annualisation.

v2 (ADR 0023 step 3) stores the same values as v1 as 32-bit floats and drops the columns
computed from other columns: ``pct_from_high_52w`` / ``pct_from_low_52w`` are expression
features (``config/site/features/price.toml``), computed on read.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.quant import realized_vol

type Matrix = npt.NDArray[np.float64]

NAME = "price_stats"
VERSION = 2
BARS = "bars/1d"
SMA_WINDOWS = (20, 50, 200)
RETURN_WINDOWS = (20, 60)
HV_WINDOWS = (20, 30)
YZ_WINDOW = 20
ADV_WINDOW = 20

CLOSE, HIGH, LOW, OPEN, VOLUME = (f"{BARS}.{c}" for c in ("close", "high", "low", "open", "volume"))


# Why close / the 52-week range are null, from price_history@v1 (ADR 0046): no trade on the
# session; a listing too young, or a name trading too rarely, for the window.
_BAR_STATUS = "price_history.bar_status@v1"
_SHORT_RANGE: dict[str, Any] = {
    "null_status": "price_history.range_status@v1",
    "explained_statuses": ("FEW_BARS", "NEW_LISTING"),
}


def _gap(n: int) -> str:
    return f"a session among the last {n} has no bar (a gap), or the history is shorter"


FEATURES = (
    Feature(
        "close", "float32", "usd_per_share",
        "The session's close, split-adjusted as of the session",
        "no bar on the session (no row): price_history bar_status says NO_TRADE when the "
        "instrument has an earlier bar in the last 252 sessions",
        valid_range=(0, None), inputs=(CLOSE,),
        null_status=_BAR_STATUS, explained_statuses=("NO_TRADE",),
    ),
    *(
        Feature(
            f"sma_{n}", "float32", "usd_per_share", f"Mean close over the last {n} sessions",
            _gap(n), valid_range=(0, None), inputs=(CLOSE,),
        )
        for n in SMA_WINDOWS
    ),
    *(
        Feature(
            f"ret_{n}d", "float32", "decimal", f"Close / close {n} sessions earlier - 1",
            _gap(n + 1), valid_range=(-1, None), inputs=(CLOSE,),
        )
        for n in RETURN_WINDOWS
    ),
    Feature(
        "high_52w", "float32", "usd_per_share",
        "Highest daily high over the last 52 weeks (252 sessions), split-adjusted (not "
        "dividend-adjusted)",
        "fewer than min_year_sessions (240) bars among the last year_sessions (252)",
        valid_range=(0, None), inputs=(HIGH,), **_SHORT_RANGE,
    ),
    Feature(
        "low_52w", "float32", "usd_per_share",
        "Lowest daily low over the last 52 weeks (252 sessions), split-adjusted (not "
        "dividend-adjusted)",
        "fewer than min_year_sessions (240) bars among the last year_sessions (252)",
        valid_range=(0, None), inputs=(LOW,), **_SHORT_RANGE,
    ),
    *(
        Feature(
            f"hv{n}", "float32", "decimal",
            f"Close-to-close realised volatility: sample stdev of the last {n} log returns "
            "x sqrt(252)",
            _gap(n + 1), valid_range=(0, 5), inputs=(CLOSE,),
        )
        for n in HV_WINDOWS
    ),
    Feature(
        f"hv{YZ_WINDOW}_yz", "float32", "decimal",
        f"Yang-Zhang realised volatility over {YZ_WINDOW} sessions, annualised (252)",
        _gap(YZ_WINDOW + 1), valid_range=(0, 5), inputs=(OPEN, HIGH, LOW, CLOSE),
    ),
    Feature(
        f"adv_usd_{ADV_WINDOW}d", "float32", "usd",
        f"Mean daily dollar volume (close x volume) over {ADV_WINDOW} sessions",
        _gap(ADV_WINDOW), valid_range=(0, None), inputs=(CLOSE, VOLUME),
    ),
    Feature(
        "history_days", "int", "sessions",
        "Sessions with a bar among the last year_sessions (252), the session included",
        "never", valid_range=(1, None), inputs=(CLOSE,),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


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


def traded_rows(px: Panel, values: Mapping[str, Matrix], columns: Iterable[str]) -> pd.DataFrame:
    """One row per instrument with a bar on the panel's last session: ``instrument_id`` and
    each of ``columns`` from ``values`` (one value per instrument)."""
    traded = ~np.isnan(px.close[-1])
    frame = pd.DataFrame({"instrument_id": px.ids[traded]})
    for column in columns:
        frame[column] = values[column][traded]
    return frame


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
    frame = traded_rows(px, stats(px, p), COLUMNS)
    frame["history_days"] = frame["history_days"].astype(np.int64)
    return frame


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Close, moving averages, returns, 52-week range, realised vol and dollar volume",
    (Input(BARS, lookback=lookback),),
    FEATURES,
    compute,
    PriceStatsParams(),
)
