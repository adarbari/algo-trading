"""``factor_betas@v1``: an instrument's loadings on free ETF factor proxies over the 252
sessions ending at the session, and the volatility its factors leave unexplained (IVOL).

Input: ``bars/1d`` split-adjusted as of the session, 253 closes; ``instruments/symbol_ids``
(the factor ETFs by ticker, ADR 0018: never built); ``relative_strength@v1``'s ``sector_etf`` of
the session (the sector map lives there, once). Everything reads closes up to the session only,
so the betas are known at the session (the decoy battery of ADR 0053 amendment 2026-10-18 and
the later residual returns read them as such).

The factors are daily log returns of ETFs, no estimation from our survivorship-prone universe:

    market   SPY                          size     IWM - SPY (small minus the market)
    momentum MTUM - SPY                   value    VLUE - SPY
    sector   the instrument's sector SPDR - SPY

Each instrument is regressed (OLS with an intercept) on market, size, momentum and value over the
sessions where its return and those factors exist; it needs ``MIN_OBS`` of them. The four betas
and ``ivol_252d`` (the standard deviation of the residuals, n - 5 degrees of freedom, annualised
by sqrt(252)) come from that fit, so they exist for every name and every history the four ETFs
cover. ``beta_sector`` comes from the four-factor fit and only where the session has a sector
ETF for the name (``relative_strength@v1`` ``sector_etf``, null before the first company
snapshot): else null with status NO_SECTOR, the other columns still set. A window the four
ETFs do not cover (MTUM and VLUE start in 2013) or a short history is UNKNOWN throughout with
its ``factor_status``: never a market-only regression presented as the factor one.
"""

from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market.tickers import BARS, SYMBOL_IDS, Matrix, ticker_ids
from algotrade.features.rollups.price.price_stats import panel, traded_rows
from algotrade.features.rollups.relative.relative_strength import BENCHMARK, ETFS

NAME = "factor_betas"
VERSION = 1
RELATIVE = "rollups/instrument/relative_strength@v1"
WINDOW = 252  # sessions of returns: 253 closes
MIN_OBS = 200  # joint observations an instrument (and each factor ETF) needs
ANNUAL = 252  # sessions a year: the IVOL annualisation
SIZE_ETF, MOMENTUM_ETF, VALUE_ETF = "IWM", "MTUM", "VLUE"
FACTOR_ETFS = (BENCHMARK, SIZE_ETF, MOMENTUM_ETF, VALUE_ETF)
OK, NO_FACTOR_HISTORY, NO_SECTOR, SHORT_HISTORY = (
    "OK", "NO_FACTOR_HISTORY", "NO_SECTOR", "SHORT_HISTORY",
)  # fmt: skip
STATUSES = (OK, NO_FACTOR_HISTORY, NO_SECTOR, SHORT_HISTORY)
BETAS = ("beta_mkt", "beta_size", "beta_mom", "beta_value", "beta_sector")  # the slopes, in order
_UNKNOWN = (
    f"a factor ETF ({', '.join(FACTOR_ETFS)}) has fewer than {MIN_OBS} of the window's "
    "returns (NO_FACTOR_HISTORY: the store, or the ETF's own history, does not cover the "
    f"window), or the instrument has fewer than {MIN_OBS} sessions with a return and every "
    "factor (SHORT_HISTORY)"
)
_SECTOR_UNKNOWN = (
    f"{_UNKNOWN}, or the instrument has no sector ETF at the session (NO_SECTOR: "
    "relative_strength@v1's sector_etf is null, as before the first company snapshot), or its "
    "ETF has too few returns"
)
_INPUTS = (f"{BARS}.close", f"{SYMBOL_IDS}.instrument_id", "relative_strength.sector_etf@v1")


def _beta(name: str, meaning: str) -> Feature:
    return Feature(
        name, "float32", "ratio",
        f"{meaning}: the OLS slope of the instrument's daily log returns on that factor, with "
        f"the other factors in the same regression, over the last {WINDOW} sessions. 1 moves "
        "one for one with the factor",
        _SECTOR_UNKNOWN if name == "beta_sector" else _UNKNOWN,
        valid_range=(-10, 10), inputs=_INPUTS,
    )  # fmt: skip


FEATURES = (
    _beta("beta_mkt", f"Market beta (the {BENCHMARK} loading)"),
    _beta("beta_size", f"Size loading ({SIZE_ETF} minus {BENCHMARK}; above 0 leans small)"),
    _beta("beta_mom", f"Momentum loading ({MOMENTUM_ETF} minus {BENCHMARK})"),
    _beta("beta_value", f"Value loading ({VALUE_ETF} minus {BENCHMARK})"),
    _beta("beta_sector", f"Sector loading (its sector SPDR minus {BENCHMARK})"),
    Feature(
        f"ivol_{WINDOW}d", "float32", "decimal",
        "Idiosyncratic volatility: the standard deviation of the daily log returns left after "
        f"market, size, momentum and value, over the last {WINDOW} sessions, annualised "
        f"(x sqrt({ANNUAL})). 0.4 "
        "is 40% a year of move the market, size, momentum and value do not explain "
        "(Ang, Hodrick, Xing and Zhang 2006 use the Fama-French three factors)",
        _UNKNOWN, valid_range=(0, 20), inputs=_INPUTS,
    ),
    Feature(
        "factor_obs", "int", "count",
        f"Sessions of the {WINDOW}-session window with a return for the instrument and every "
        "factor: the observations the regression used",
        "never", valid_range=(0, WINDOW), inputs=_INPUTS,
    ),
    Feature(
        "factor_status", "str", "category",
        f"OK: every column is set; NO_SECTOR: all but beta_sector (no sector ETF at the session); "
        f"NO_FACTOR_HISTORY: a factor ETF lacks {MIN_OBS} returns in the window; SHORT_HISTORY: "
        f"fewer than {MIN_OBS} joint observations",
        "never", "label", categories=STATUSES, inputs=_INPUTS,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)
IVOL = f"ivol_{WINDOW}d"


def _log_returns(close: Matrix) -> Matrix:
    with np.errstate(divide="ignore", invalid="ignore"):
        levels = np.where(close > 0, np.log(close), np.nan)
    return levels[1:] - levels[:-1]


def _etf_returns(
    ids: np.ndarray, returns: Matrix, symbols: pd.DataFrame | None, tickers: tuple[str, ...]
) -> dict[str, np.ndarray]:
    """The daily log returns of each ticker the symbol map and the panel both have."""
    column = {iid: i for i, iid in enumerate(ids)}
    return {
        t: returns[:, column[iid]]
        for t, iid in ticker_ids(symbols, tickers).items()
        if iid in column
    }


def regress(y: Matrix, x: Matrix) -> tuple[Matrix, Matrix, npt.NDArray[np.int_]]:
    """OLS with an intercept of each column of ``y`` (sessions x instruments) on ``x`` (sessions
    x factors): ``(slopes (factors x instruments), residual standard deviation, observations)``.
    A session counts for an instrument only when its return and every factor are finite; an
    instrument with fewer than ``MIN_OBS`` of them is NaN. Instruments with the same sessions
    are fitted together."""
    n_factors, n_ids = x.shape[1], y.shape[1]
    slopes = np.full((n_factors, n_ids), np.nan)
    sd = np.full(n_ids, np.nan)
    usable = np.isfinite(x).all(axis=1)
    mask = np.isfinite(y) & usable[:, None]
    obs = mask.sum(axis=0)
    fitted = obs >= MIN_OBS
    for pattern in {m.tobytes(): m for m in mask[:, fitted].T}.values():  # one per distinct mask
        columns = np.flatnonzero(fitted & (mask == pattern[:, None]).all(axis=0))
        design = np.column_stack([np.ones(int(pattern.sum())), x[pattern]])
        target = y[np.ix_(pattern, columns)]
        coef = np.linalg.lstsq(design, target, rcond=None)[0]
        resid = target - design @ coef
        dof = design.shape[0] - design.shape[1]
        slopes[:, columns] = coef[1:]
        sd[columns] = np.sqrt((resid**2).sum(axis=0) / dof) * np.sqrt(ANNUAL)
    return slopes, sd, obs


def compute(inputs: Inputs, session: date, p: None) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    px = panel(bars, sessions_ending(session, WINDOW + 1))
    returns = _log_returns(px.close)
    symbols = inputs[SYMBOL_IDS]
    etf = _etf_returns(px.ids, returns, symbols, (*FACTOR_ETFS, *ETFS))
    n = len(px.ids)
    sectors = _sector_etfs(px.ids, inputs[RELATIVE])
    values: dict[str, np.ndarray] = {c: np.full(n, np.nan) for c in (*BETAS, IVOL)}
    obs = np.zeros(n, dtype=np.int64)
    status = np.full(n, NO_FACTOR_HISTORY, dtype=object)
    if all(_covered(etf, t) for t in FACTOR_ETFS):
        spy = etf[BENCHMARK]
        base = np.column_stack(
            [spy, etf[SIZE_ETF] - spy, etf[MOMENTUM_ETF] - spy, etf[VALUE_ETF] - spy]
        )
        slopes, sd, found = regress(returns, base)  # every name: market, size, momentum, value
        for k, column in enumerate(BETAS[:4]):
            values[column] = slopes[k]
        values[IVOL], obs = sd, found
        status[:] = np.where(np.isfinite(sd), NO_SECTOR, SHORT_HISTORY)
        for sector in sorted({s for s in sectors if s and _covered(etf, s)}):
            members = np.flatnonzero((sectors == sector) & np.isfinite(sd))
            if not len(members):
                continue
            five = regress(returns[:, members], np.column_stack([base, etf[sector] - spy]))
            values["beta_sector"][members] = five[0][4]
            status[members] = np.where(np.isfinite(five[0][4]), OK, NO_SECTOR)
    values["factor_obs"] = obs
    values["factor_status"] = status
    return traded_rows(px, values, COLUMNS)


def _covered(etf: dict[str, np.ndarray], ticker: str) -> bool:
    """The ETF has a return series with ``MIN_OBS`` finite returns in the window."""
    return ticker in etf and int(np.isfinite(etf[ticker]).sum()) >= MIN_OBS


def _sector_etfs(ids: np.ndarray, rel: pd.DataFrame | None) -> np.ndarray:
    """The sector ETF ticker of each instrument through ``relative_strength@v1`` ('' for none)."""
    out = np.full(len(ids), "", dtype=object)
    if rel is None or "sector_etf" not in rel.columns:
        return out
    sector = dict(zip(rel["instrument_id"].astype(str), rel["sector_etf"], strict=True))
    for i, iid in enumerate(ids):
        etf = sector.get(iid)
        out[i] = etf if isinstance(etf, str) else ""
    return out


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Loadings on four ETF factor proxies (market, size, momentum, value) and a sector one over "
    "252 sessions and the idiosyncratic volatility the four leave: the decoys' beta and IVOL, "
    "point in time",
    (
        Input(BARS, lookback=WINDOW),
        Input(SYMBOL_IDS, required=False),
        Input(RELATIVE),
    ),
    FEATURES,
    compute,
    None,
)
