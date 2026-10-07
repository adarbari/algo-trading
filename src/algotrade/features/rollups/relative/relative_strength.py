"""``relative_strength@v1``: an instrument against SPY, against its sector's ETF and against the
universe's stocks, from daily bars (``docs/data/technical.md``).

Inputs: ``bars/1d`` (split-adjusted as of the session, every instrument, the session plus 252
earlier sessions), ``instruments/symbol_ids`` (the ticker -> id lookup that finds SPY and the
sector ETFs: never a population), ``universe`` (the population of the percentiles: the STOCK
members of the snapshot the session sees, as ``market_breadth@v1`` counts them; none before
the first snapshot; ``min_coverage`` of them need a bar on the session, as there) and
``instruments/company`` (the SEC sector of the company snapshot on or before the session).
One row per instrument with a bar on the session.

An n-session return is ``close / close n sessions earlier - 1`` and is known only when every
session of its n + 1 closes has a bar (a gap makes it null, never a shorter window).

    rs_spy_63d, rs_spy_252d  (1 + return) / (1 + SPY's return over the same n sessions) - 1
    rs_line_high_252d        the line close / SPY close is at its highest of the last 252
                             sessions (today included)
    rs_spy_trend_20d         rs_spy_63d today - rs_spy_63d 20 sessions earlier
    ret_5d_pctile,           the share of members with a known n-session return strictly below
    mom_pctile_63d,          the instrument's, among members with a known one (the 63-session
    mom_pctile_252d          return is a quarter, as the relative-strength columns)
    sector_etf               ``SECTOR_ETFS[sector]`` (the sector names are the SEC SIC heuristic's)
    sector_ret_63d           the sector ETF's 63-session return
    rs_sector_63d            (1 + return) / (1 + sector ETF's return) - 1 over 63 sessions
    sector_rank_63d          the sector ETF's rank among the 11 by 63-session return (1 the
                             strongest; ties share the better rank)

Parameters: ``RelativeStrengthParams`` (``config/site/rollups.toml``
``["relative_strength@v1"]``).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.breadth import MEMBER_CLASS
from algotrade.features.rollups.market.tickers import BARS, SYMBOL_IDS, Matrix, ticker_ids
from algotrade.features.rollups.price.price_stats import Panel, panel, traded_rows

NAME = "relative_strength"
VERSION = 1
UNIVERSE = "universe"
COMPANY = "instruments/company"
BENCHMARK = "SPY"
# The SEC SIC heuristic's sector names (libs/sources/.../vendors/sec/sic.py) -> the SPDR sector ETF.
SECTOR_ETFS = {
    "Technology": "XLK",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}
ETFS = tuple(SECTOR_ETFS.values())
WEEK, QUARTER, YEAR = 5, 63, 252  # sessions: the percentile's short window, a quarter, a year
PERCENTILES = {WEEK: f"ret_{WEEK}d_pctile", QUARTER: f"mom_pctile_{QUARTER}d",
               YEAR: f"mom_pctile_{YEAR}d"}  # fmt: skip
TREND = 20  # sessions the relative-strength trend looks back
LOOKBACK = YEAR  # earlier sessions read: a 252-session return needs the close before
CLOSE = f"{BARS}.close"
ID = f"{SYMBOL_IDS}.instrument_id"
MEMBERS = f"{UNIVERSE}.instrument_id"
SECTOR = f"{COMPANY}.sector"
_SPY = f"{BENCHMARK}'s"
_GAP = "a session in the window has no bar (a gap), or the history is shorter"
_NO_SPY = f"{BENCHMARK} is not in the symbol map, or its own window has a gap"


def _pctile_null(n: int) -> str:
    return (
        "no universe snapshot on or before the session, fewer than min_coverage of its members "
        f"have a bar on the session (a partial day), fewer than min_members members have a "
        f"known {n}-session return, or the instrument's own {n}-session return is unknown "
        f"({_GAP})"
    )


FEATURES = (
    *(
        Feature(
            f"rs_spy_{n}d", "float32", "decimal",
            f"Relative strength against {BENCHMARK} over {n} sessions: (1 + the instrument's "
            f"{n}-session return) / (1 + {_SPY}) - 1. Above 0 the instrument beat the market "
            "over the window by that share of its starting value; 0.10 is 10 points ahead",
            f"the instrument's {n}-session return is unknown ({_GAP}), or {_NO_SPY}",
            valid_range=(-1, None), inputs=(CLOSE, ID),
        )
        for n in (QUARTER, YEAR)
    ),
    Feature(
        f"rs_line_high_{YEAR}d", "bool", "flag",
        f"The relative-strength line (close / {_SPY} close) is at its highest of the last "
        f"{YEAR} sessions, today included: the instrument is outperforming at a new high",
        f"a session among the last {YEAR} has no bar for the instrument or {BENCHMARK}, or "
        f"{BENCHMARK} is not in the symbol map",
        inputs=(CLOSE, ID),
    ),
    Feature(
        f"rs_spy_trend_{TREND}d", "float32", "decimal",
        f"rs_spy_{QUARTER}d today minus rs_spy_{QUARTER}d {TREND} sessions earlier: above 0 "
        "relative strength is improving, below 0 deteriorating; 0.03 means 3 points better "
        "than it was a month ago",
        f"rs_spy_{QUARTER}d is unknown today or {TREND} sessions earlier ({_GAP}; "
        f"{BENCHMARK}'s window included)",
        valid_range=(-5, 5), inputs=(CLOSE, ID),
    ),
    Feature(
        f"ret_{WEEK}d_pctile", "float32", "decimal",
        f"The share of universe members (stocks of the snapshot the session sees) whose "
        f"{WEEK}-session return is strictly below the instrument's, among members with a known "
        "one: 0.9 is stronger than 90% of the stocks this week",
        _pctile_null(WEEK), kind="cross_section", valid_range=(0, 1), inputs=(CLOSE, MEMBERS),
    ),
    *(
        Feature(
            f"mom_pctile_{n}d", "float32", "decimal",
            f"The share of universe members (stocks of the snapshot the session sees) whose "
            f"{n}-session return is strictly below the instrument's, among members with a "
            f"known one: 0.9 is a top-decile {n}-session return",
            _pctile_null(n), kind="cross_section", valid_range=(0, 1), inputs=(CLOSE, MEMBERS),
        )
        for n in (QUARTER, YEAR)
    ),
    Feature(
        "sector_etf", "str", "text",
        "The ticker of the sector ETF the instrument's company sector maps to (Technology XLK, "
        "Health Care XLV, Financials XLF, Consumer Discretionary XLY, Consumer Staples XLP, "
        "Energy XLE, Industrials XLI, Materials XLB, Utilities XLU, Real Estate XLRE, "
        "Communication Services XLC); the sector is the SEC SIC code's coarse market sector",
        "the company snapshot on or before the session has no sector for the instrument (no "
        "snapshot yet), the universe lists it as an ETF (a fund has no sector here even when "
        "its SEC filings carry a SIC code), or the sector has no ETF",
        inputs=(SECTOR,),
    ),
    Feature(
        f"sector_ret_{QUARTER}d", "float32", "decimal",
        f"The {QUARTER}-session return of the instrument's sector ETF (close / close "
        f"{QUARTER} sessions earlier - 1)",
        f"sector_etf is null, or the ETF is not in the symbol map or has a gap in its "
        f"{QUARTER + 1} closes",
        valid_range=(-1, None), inputs=(SECTOR, CLOSE, ID),
    ),
    Feature(
        f"rs_sector_{QUARTER}d", "float32", "decimal",
        f"Relative strength against the sector ETF over {QUARTER} sessions: (1 + the "
        f"instrument's return) / (1 + the ETF's) - 1; above 0 the instrument beat its sector",
        f"sector_ret_{QUARTER}d is null, or the instrument's {QUARTER}-session return is "
        f"unknown ({_GAP})",
        valid_range=(-1, None), inputs=(SECTOR, CLOSE, ID),
    ),
    Feature(
        f"sector_rank_{QUARTER}d", "int", "count",
        f"The rank of the instrument's sector ETF among the {len(ETFS)} sector ETFs by "
        f"{QUARTER}-session return: 1 the strongest sector, {len(ETFS)} the weakest; ETFs "
        "with equal returns share the better rank",
        f"sector_ret_{QUARTER}d is null, or fewer than min_sector_etfs of the {len(ETFS)} ETFs "
        f"have a complete {QUARTER}-session window",
        kind="cross_section", valid_range=(1, len(ETFS)), inputs=(SECTOR, CLOSE, ID),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class RelativeStrengthParams:
    min_members: int = 200  # members with a known return a percentile needs
    min_coverage: float = 0.9  # share of members with a bar on the session a percentile needs
    min_sector_etfs: int = 6  # sector ETFs with a known return a sector rank needs

    def __post_init__(self) -> None:
        if not 0 <= self.min_coverage <= 1:
            raise ValueError(f"min_coverage must be in [0, 1], got {self.min_coverage}")
        if self.min_members < 1:
            raise ValueError(f"min_members must be >= 1, got {self.min_members}")
        if not 1 <= self.min_sector_etfs <= len(ETFS):
            raise ValueError(
                f"min_sector_etfs must be in [1, {len(ETFS)}], got {self.min_sector_etfs}"
            )


def ret(close: Matrix, n: int, back: int = 0) -> Matrix:
    """The n-session return ``back`` sessions before the last row, per column: ``close /
    close n sessions earlier - 1``; NaN unless all n + 1 closes exist."""
    end = len(close) - back
    if end - n - 1 < 0:
        return np.full(close.shape[1:], np.nan)
    window = close[end - n - 1 : end]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = window[-1] / window[0] - 1.0
    return np.where(~np.isnan(window).any(axis=0) & np.isfinite(out), out, np.nan)


def relative(ret_a: Matrix, ret_b: Matrix | float) -> Matrix:
    """(1 + a) / (1 + b) - 1; NaN when either is unknown."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (1.0 + ret_a) / (1.0 + ret_b) - 1.0
    return np.where(np.isfinite(out), out, np.nan)


def percentile(returns: Matrix, members: np.ndarray, minimum: int) -> Matrix:
    """The share of ``members`` (a mask) with a known return strictly below each instrument's,
    among members with a known return; NaN for an instrument without a return, and everywhere
    when fewer than ``minimum`` members have one."""
    pool = np.sort(returns[members & ~np.isnan(returns)])
    if len(pool) < max(minimum, 1):
        return np.full(returns.shape, np.nan)
    below = np.searchsorted(pool, returns, side="left") / len(pool)
    return np.where(np.isnan(returns), np.nan, below)


def _series(close: Matrix, index: dict[str, int], ids: dict[str, str], ticker: str) -> Matrix:
    """One ticker's closes down the session axis (all NaN when it has no id or no bar)."""
    iid = ids.get(ticker)
    if iid is None or iid not in index:
        return np.full(len(close), np.nan)
    return close[:, index[iid]]


def _rs_line_high(close: Matrix, spy: Matrix) -> np.ndarray:
    """``True`` / ``False`` per instrument, ``None`` where the line is unknown on a session."""
    line = close[-YEAR:] / spy[-YEAR:, None]
    known = ~np.isnan(line).any(axis=0) & np.isfinite(line).all(axis=0)
    with np.errstate(invalid="ignore"):
        high = line[-1] >= line.max(axis=0)
    out = np.full(close.shape[1], None, dtype=object)
    out[known] = high[known].tolist()
    return out


def versus_spy(close: Matrix, spy: Matrix) -> dict[str, np.ndarray]:
    """The relative-strength columns against SPY (``spy``: its closes on the session axis)."""
    spy_col = spy[:, None]
    rs = {n: relative(ret(close, n), ret(spy_col, n)[0]) for n in (QUARTER, YEAR)}
    before = relative(ret(close, QUARTER, TREND), ret(spy_col, QUARTER, TREND)[0])
    return {
        f"rs_spy_{QUARTER}d": rs[QUARTER],
        f"rs_spy_{YEAR}d": rs[YEAR],
        f"rs_line_high_{YEAR}d": _rs_line_high(close, spy),
        f"rs_spy_trend_{TREND}d": rs[QUARTER] - before,
    }


def _sector_columns(
    px: Panel,
    ids: dict[str, str],
    company: pd.DataFrame | None,
    quarter: Matrix,
    funds: set[str],
    p: RelativeStrengthParams,
) -> dict[str, np.ndarray]:
    """sector_etf, the ETF's 63-session return, the relative strength against it and its rank
    among the sector ETFs, per instrument of the panel (none for ``funds``: an ETF or trust
    can carry a SIC code, but a sector ETF is not its benchmark)."""
    n = len(px.ids)
    out: dict[str, np.ndarray] = {
        "sector_etf": np.full(n, None, dtype=object),
        f"sector_ret_{QUARTER}d": np.full(n, np.nan),
        f"rs_sector_{QUARTER}d": np.full(n, np.nan),
        f"sector_rank_{QUARTER}d": np.full(n, np.nan),
    }
    if company is None or "sector" not in company.columns:
        return out
    index = {iid: i for i, iid in enumerate(px.ids)}
    etf_ret = {t: ret(_series(px.close, index, ids, t)[:, None], QUARTER)[0] for t in ETFS}
    known = sorted((v for v in etf_ret.values() if not np.isnan(v)), reverse=True)
    named = zip(company["instrument_id"].astype(str), company["sector"], strict=True)
    sector = {iid: s for iid, s in named if isinstance(s, str)}
    for i, iid in enumerate(px.ids):
        etf = None if iid in funds else SECTOR_ETFS.get(sector.get(iid, ""))
        if etf is None:
            continue
        out["sector_etf"][i] = etf
        value = etf_ret[etf]
        if np.isnan(value):
            continue
        out[f"sector_ret_{QUARTER}d"][i] = value
        out[f"rs_sector_{QUARTER}d"][i] = relative(quarter[i], value)
        if len(known) >= p.min_sector_etfs:
            out[f"sector_rank_{QUARTER}d"][i] = 1 + sum(v > value for v in known)
    return out


def compute(inputs: Inputs, session: date, p: RelativeStrengthParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, LOOKBACK + 1))
    ids = ticker_ids(inputs[SYMBOL_IDS], (BENCHMARK, *ETFS))
    index = {iid: i for i, iid in enumerate(px.ids)}
    values = versus_spy(px.close, _series(px.close, index, ids, BENCHMARK))
    universe = inputs[UNIVERSE]
    stocks: set[str] = set()
    funds: set[str] = set()  # listed in the universe as something else (an ETF): no sector
    if universe is not None:
        is_stock = universe["asset_class"] == MEMBER_CLASS
        stocks = set(universe.loc[is_stock, "instrument_id"].astype(str))
        funds = set(universe.loc[~is_stock, "instrument_id"].astype(str)) - stocks
    members = np.isin(px.ids, list(stocks))
    covered = int((members & ~np.isnan(px.close[-1])).sum())
    # a partial day (few members with a bar) would rank against a skewed pool: no percentile
    full = bool(stocks) and covered / len(stocks) >= p.min_coverage
    for n, column in PERCENTILES.items():
        values[column] = (
            percentile(ret(px.close, n), members, p.min_members)
            if full
            else np.full(len(px.ids), np.nan)
        )
    values |= _sector_columns(px, ids, inputs[COMPANY], ret(px.close, QUARTER), funds, p)
    return traded_rows(px, values, COLUMNS)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Relative strength against SPY (63 and 252 sessions, the line's 252-session high, its "
    "20-session trend), percentile ranks of the 5, 63 and 252-session returns among the "
    "universe's stocks, and the sector: its ETF, the ETF's return, relative strength against "
    "it and the sector's rank among the eleven",
    (
        Input(BARS, lookback=LOOKBACK),
        Input(SYMBOL_IDS, required=False),
        Input(UNIVERSE, required=False),
        Input(COMPANY, required=False),
    ),
    FEATURES,
    compute,
    RelativeStrengthParams(),
)
