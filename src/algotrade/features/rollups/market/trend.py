"""``market_trend@v2``: the trend of the S&P 500, the Nasdaq-100 and the Nasdaq Composite, one
``MKT:US`` row per session (ADR 0047; ADR 0048 for the index levels).

Each column prefix reads ONE source per session, never a mix inside a window:

    spx_   SPY's bars when its full 253-session window is complete, else the S&P 500 level
           (``IDX:SPX``, FRED SP500, 2016 on)
    ndx_   QQQ's bars only (as v1: each column needs its own window complete)
    comp_  the Nasdaq Composite level only (``IDX:COMP``, FRED NASDAQCOM, 1971 on)

Bars are ``bars/1d`` (split-adjusted as of the session, never dividend-adjusted: a price
return), found by ticker through ``instruments/symbol_ids``, one close per exchange session
(``core.time.calendar``). Index levels are ``macro/series`` read point in time by vintage
(``vintage_date`` on or before the session); both series are ``pit = "lag"`` with a one-day
release lag (``config/site/macro.toml``), so a session knows the level up to the PREVIOUS
session's close, never its own. An index window counts the last N non-null observations known
by the session (a FRED "." holiday is skipped, not counted; not calendar sessions), and the
prefix is null when its newest observation is more than ``MAX_AGE`` sessions old.
``<p>_source`` says which source fed the row (``bars`` | ``index``; null: neither);
``<p>_level`` is the index level itself (the previous close), whatever the source.

A column is null (UNKNOWN), never a shorter window, unless its whole window is known:

    <p>_close_vs_sma200    close / mean close over 200 closes - 1
    <p>_sma50_vs_sma200    sma50 / sma200 - 1 (below 0: a "death cross")
    <p>_drawdown_252d      close / highest close of the last 252 - 1
                           (``quant.turning_points.drawdowns`` over that window)
    <p>_realised_vol_20d   sample stdev of the last 20 log returns x sqrt(252)
                           (``quant.realized_vol.close_to_close``)
    <p>_ret_21d, _ret_252d close / close 21 (252) closes earlier - 1

Licence (ADR 0028, ADR 0048): the index levels are for personal use, so every column that can
come from them or reads them (every ``spx_`` and ``comp_`` column, the source labels included)
is ``personal``; ``ndx_`` is open.

v2 added the index fallback and ``comp_`` (v1 read SPY and QQQ bars only, so its ``spx_``
columns were null until SPY's stored history covered their windows). v1 is superseded and,
like ``market_macro@v2``, not in ``features.registry.SUPERSEDED`` (that map, ``moved_field``
and ``retire-features`` handle instrument groups only). The windows are part of the
definition (named in the columns): changing one is a new version.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import index_id, market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.market.macro import MACRO
from algotrade.features.rollups.market.observations import as_series, last_observations
from algotrade.features.rollups.market.tickers import BARS, SYMBOL_IDS, Matrix, closes, ticker_ids
from algotrade.quant import realized_vol
from algotrade.quant.turning_points import drawdowns

NAME = "market_trend"
VERSION = 2
SMA_LONG, SMA_SHORT = 200, 50
DRAWDOWN_WINDOW = 252
VOL_WINDOW = 20
RETURN_WINDOWS = (21, 252)
PERIODS_PER_YEAR = 252
LOOKBACK = max(SMA_LONG, DRAWDOWN_WINDOW, VOL_WINDOW + 1, *(n + 1 for n in RETURN_WINDOWS)) - 1
WINDOW = LOOKBACK + 1  # closes a full window holds (253)
MAX_AGE = 2  # sessions: an index level whose newest observation is older is stale
# Sessions of index observations read: the window plus room for exchange sessions the index
# has no value on (a "." or a closure the calendar does not know).
INDEX_LOOKBACK = LOOKBACK + 30
SOURCES = ("bars", "index")
TREND = ("close_vs_sma200", "sma50_vs_sma200", "drawdown_252d", "realised_vol_20d",
         *(f"ret_{n}d" for n in RETURN_WINDOWS))  # fmt: skip


@dataclass(frozen=True)
class Prefix:
    """What one column prefix reads: an ETF's bars (``ticker``), an index level (``index``, its
    ``config/site/macro.toml`` key), or both (the bars, else the level)."""

    name: str  # the index, in descriptions
    ticker: str | None = None
    index: str | None = None

    @property
    def index_id(self) -> str | None:
        return index_id(self.index) if self.index else None


PREFIXES = {
    "spx": Prefix("the S&P 500", "SPY", "SPX"),
    "ndx": Prefix("the Nasdaq-100", "QQQ"),
    "comp": Prefix("the Nasdaq Composite", index="COMP"),
}
TICKERS = tuple(p.ticker for p in PREFIXES.values() if p.ticker)
INDEX_IDS = tuple(i for p in PREFIXES.values() if (i := p.index_id))

CLOSE = f"{BARS}.close"
ID = f"{SYMBOL_IDS}.instrument_id"
LAG = "the previous session's close (the level is published a day late: pit lag)"


def _source(p: Prefix) -> str:
    """Where the prefix's closes come from, for its descriptions."""
    if p.ticker and p.index:
        return (f"{p.name}: {p.ticker}'s bars when its {WINDOW}-session window is complete "
                f"(as of the session's close), else the {p.index} level, as of {LAG}")  # fmt: skip
    if p.index:
        return f"{p.name}: the {p.index} level, as of {LAG}"
    return f"{p.name}: {p.ticker}'s bars, as of the session's close"


def _null(p: Prefix, n: int) -> str:
    bars = (f"{p.ticker} is not in the reference snapshot, or has no bar on a session among "
            f"the last {n} (a short history or a gap)")  # fmt: skip
    index = (f"{p.index} has fewer than {n} observations known by the session, or its newest "
             f"is more than {MAX_AGE} sessions old (stale, or no FRED key)")  # fmt: skip
    if p.ticker and p.index:
        return f"{p.ticker} has no complete {WINDOW}-session window, and {index}"
    return index if p.index else bars


def _features(prefix: str) -> tuple[Feature, ...]:
    p = PREFIXES[prefix]
    src = _source(p)
    licence: Licence = "personal" if p.index else "open"
    inputs = (*((CLOSE, ID) if p.ticker else ()), *((f"series:{p.index}",) if p.index else ()))

    def f(name: str, text: str, n: int, valid_range: tuple[float, float | None]) -> Feature:
        return Feature(f"{prefix}_{name}", "float32", "decimal", f"{text}. {src}", _null(p, n),
                       valid_range=valid_range, inputs=inputs, licence=licence)  # fmt: skip

    trend = (
        f("close_vs_sma200", f"Close / its mean close over the last {SMA_LONG} - 1 (below 0: "
          "under the 200-day average)", SMA_LONG, (-1, None)),
        f("sma50_vs_sma200", f"{SMA_SHORT}-close mean / {SMA_LONG}-close mean - 1 (below 0: a "
          "death cross)", SMA_LONG, (-1, None)),
        f("drawdown_252d", f"Close / its highest close of the last {DRAWDOWN_WINDOW} - 1 (0 at "
          "a new high, -0.2 a bear market's threshold)", DRAWDOWN_WINDOW, (-1, 0)),
        f("realised_vol_20d", f"Close-to-close realised volatility: sample stdev of the last "
          f"{VOL_WINDOW} log returns x sqrt(252)", VOL_WINDOW + 1, (0, 5)),
        *(f(f"ret_{n}d", f"Close / the close {n} earlier - 1 (price return, no dividends)",
            n + 1, (-1, None)) for n in RETURN_WINDOWS),
    )  # fmt: skip
    if not p.index:
        return trend
    sources = SOURCES if p.ticker else ("index",)
    stale = (f"no {p.index} observation known by the session, or the newest is more than "
             f"{MAX_AGE} sessions old")  # fmt: skip
    return (
        *trend,
        Feature(f"{prefix}_source", "str", "category",
                f"Which source fed the {prefix}_ columns this session ({' | '.join(sources)}). "
                f"{src}", f"no source is usable: {_null(p, 1)}", kind="label",
                categories=sources, inputs=inputs, licence=licence),
        Feature(f"{prefix}_level", "float32", "index_points",
                f"{p.name} level ({p.index}), as of {LAG}", stale, valid_range=(0, None),
                inputs=(f"series:{p.index}",), licence="personal"),
    )  # fmt: skip


FEATURES = tuple(f for prefix in PREFIXES for f in _features(prefix))
COLUMNS = column_types(FEATURES)


def _complete(window: Matrix) -> bool:
    return bool(len(window) and not np.isnan(window).any())


def index_trend(close: Matrix) -> dict[str, float]:
    """Every trend column (without its prefix) for the LAST of ``close`` (``WINDOW`` closes,
    one per session or per observation, NaN where unknown)."""
    last = close[-1]
    out = dict.fromkeys(TREND, np.nan)
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


def prefix_row(p: Prefix, bars: Matrix | None, levels: Matrix | None) -> dict[str, object]:
    """One prefix's columns (without the prefix) from its bars (``WINDOW`` sessions' closes)
    and its index levels (``WINDOW`` observations; ``None`` when stale or absent): one source
    for every window, never a mix."""
    if not p.index:  # bars only, each column on its own window (as v1)
        assert bars is not None
        return dict(index_trend(bars))
    if bars is not None and _complete(bars):
        out: dict[str, object] = {**index_trend(bars), "source": "bars"}
    elif levels is not None:
        out = {**index_trend(levels), "source": "index"}
    else:
        out = {**dict.fromkeys(TREND, np.nan), "source": None}
    out["level"] = float(levels[-1]) if levels is not None else np.nan
    return out


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    bars = inputs[BARS]
    if bars is None:
        matrix = np.full((WINDOW, len(TICKERS)), np.nan)
    else:
        ids = ticker_ids(inputs[SYMBOL_IDS], TICKERS)
        matrix = closes(bars, ids, TICKERS, sessions_ending(session, WINDOW))
    series = as_series(inputs[MACRO])
    row: dict[str, object] = {"instrument_id": market_id("US")}
    for prefix, p in PREFIXES.items():
        own = matrix[:, TICKERS.index(p.ticker)] if p.ticker else None
        iid = p.index_id
        levels = last_observations(series.get(iid), session, WINDOW, MAX_AGE) if iid else None
        for column, value in prefix_row(p, own, levels).items():
            row[f"{prefix}_{column}"] = value
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Index trend of the S&P 500 (SPY, else the index level), the Nasdaq-100 (QQQ) and the "
    "Nasdaq Composite (index level): distance from the 200-day average, death cross, drawdown "
    "from the 52-week closing high, realised vol and returns",
    (
        Input(BARS, lookback=LOOKBACK, required=False, symbols=TICKERS),
        Input(SYMBOL_IDS, required=False),
        Input(MACRO, lookback=INDEX_LOOKBACK, required=False, ids=INDEX_IDS),
    ),
    FEATURES,
    compute,
    entity="market",
)
