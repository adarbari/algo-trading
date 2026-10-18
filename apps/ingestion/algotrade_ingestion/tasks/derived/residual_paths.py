"""The residual-return arithmetic of the ``residual-returns`` task (ADR 0053 amendment, EB H11):
for one window (S..T) and the names the forward outcomes measured, each name's return minus what
its factor loadings explain over the same sessions.

    residual = fwd_return - sum_k beta_k x factor_k return over S..end

``end`` is T, or a delisted name's last bar (the window the forward row measured). The factor
returns are the simple returns over S..end of the ETF proxies of ``factor_betas@v1``: market
SPY, size IWM minus SPY, momentum MTUM minus SPY, value VLUE minus SPY. The sector loading is
left out on purpose: ``factor_betas@v1`` stores the four betas of one four-factor fit and
``beta_sector`` from a different five-factor fit, so adding it would count sector exposure twice
(a ``factor_betas@v2`` storing all five betas of the five-factor fit is needed to add sector).
The betas are those the caller read from the session before S: estimated on the 252 sessions
ending there, so they never see a return of the window (the betas come from log returns, the
window sums simple ones: a first-order match, stated, not hidden).

A name is UNMEASURED with a reason, never a market-only residual and never a zero:
``BAD_BAR`` (carried from the forward row), ``NO_FACTOR_HISTORY`` (a factor ETF has no bar at S:
MTUM and VLUE start in 2013; or the betas say so), ``NO_BETAS`` (no betas row or partition for
the name before S), ``SHORT_HISTORY`` (the betas say the name had too few joint returns) and
``NO_FACTOR_BAR`` (a factor ETF has no bar at the window's end). Pure: no storage, no clock.
"""

from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd

from algotrade.features.rollups.relative.factor_betas import (
    MOMENTUM_ETF,
    SIZE_ETF,
    VALUE_ETF,
)
from algotrade.features.rollups.relative.factor_betas import (
    NO_FACTOR_HISTORY as BETAS_NO_FACTOR_HISTORY,
)
from algotrade.features.rollups.relative.factor_betas import (
    SHORT_HISTORY as BETAS_SHORT_HISTORY,
)
from algotrade.features.rollups.relative.relative_strength import BENCHMARK
from algotrade.storage.tables.schemas import UNMEASURED
from algotrade_ingestion.tasks.derived.outcome_paths import Window, last_bar

NO_FACTOR_HISTORY = "NO_FACTOR_HISTORY"
NO_BETAS = "NO_BETAS"
SHORT_HISTORY = "SHORT_HISTORY"
NO_FACTOR_BAR = "NO_FACTOR_BAR"
FACTORS = ((SIZE_ETF, "beta_size"), (MOMENTUM_ETF, "beta_mom"), (VALUE_ETF, "beta_value"))
COLUMNS = (
    "instrument_id", "fwd_residual_return", "fwd_factor_return", "beta_session",
    "outcome_status", "outcome_reason",
)  # fmt: skip
FACTOR_ETFS = (BENCHMARK, *(t for t, _ in FACTORS))


def _cumulative(closes: pd.DataFrame, etf_id: str | None) -> np.ndarray:
    """The ETF's return from S to each row of the window (NaN without a bar at S or the row)."""
    if etf_id is None or etf_id not in closes.columns:
        return np.full(len(closes), np.nan)
    series = closes[etf_id].to_numpy(dtype=float)
    out: np.ndarray = series / series[0] - 1
    return out


def residual_rows(
    forward: pd.DataFrame,
    closes: pd.DataFrame,
    window: Window,
    etf: Mapping[str, str],
    betas: pd.DataFrame | None,
    beta_session: date | None,
) -> pd.DataFrame:
    """``forward`` (``outcome_paths.window_rows`` of the window: ``instrument_id``, ``fwd_return``,
    ``outcome_status``, ``outcome_reason``) -> one row per name, ``COLUMNS``.

    ``closes``: sessions x instruments over exactly S..T, the names and the ETFs (``wide_closes``);
    ``etf``: ticker -> instrument id of the factor ETFs the session knows;
    ``betas``: ``factor_betas@v1`` rows at ``beta_session`` indexed by instrument id, or None
    when no partition is stored there."""
    ids = forward["instrument_id"].astype(str).to_numpy()
    n = len(ids)
    status = forward["outcome_status"].to_numpy(dtype=object).copy()
    reason = np.full(n, None, dtype=object)
    carried = status == UNMEASURED
    reason[carried] = forward["outcome_reason"].to_numpy(dtype=object)[carried]
    residual, factor = np.full(n, np.nan), np.full(n, np.nan)
    live = np.flatnonzero(~carried)
    if len(live):
        _fill(forward, closes, etf, betas, ids, live, status, reason, residual, factor)
    return pd.DataFrame(
        {
            "instrument_id": ids,
            "fwd_residual_return": residual,
            "fwd_factor_return": factor,
            "beta_session": beta_session,
            "outcome_status": status,
            "outcome_reason": reason,
        },
        columns=list(COLUMNS),
    )


def _fill(
    forward: pd.DataFrame,
    closes: pd.DataFrame,
    etf: Mapping[str, str],
    betas: pd.DataFrame | None,
    ids: np.ndarray,
    live: np.ndarray,
    status: np.ndarray,
    reason: np.ndarray,
    residual: np.ndarray,
    factor: np.ndarray,
) -> None:
    """Fill ``residual`` / ``factor`` of the ``live`` rows, or give each a reason and UNMEASURED."""
    names = ids[live]
    last = last_bar(closes[names].to_numpy(dtype=float))  # each name's measured end row
    cum = {t: _cumulative(closes, etf.get(t)) for t in FACTOR_ETFS}
    pending = np.ones(len(live), dtype=bool)  # still without a reason

    def refuse(mask: np.ndarray, why: str) -> None:
        hit = pending & mask
        reason[live[hit]] = why
        status[live[hit]] = UNMEASURED
        pending[hit] = False

    refuse(
        np.full(len(live), not all(np.isfinite(cum[t][0]) for t in FACTOR_ETFS)), NO_FACTOR_HISTORY
    )
    found = pd.DataFrame(index=pd.Index(names)) if betas is None else betas.reindex(names)
    columns = ("beta_mkt", "beta_size", "beta_mom", "beta_value")
    values = {c: _numbers(found, c) for c in columns}
    state = found["factor_status"].to_numpy(dtype=object) if "factor_status" in found else None
    absent = np.ones(len(live), dtype=bool) if betas is None else ~pd.Index(names).isin(betas.index)
    refuse(absent, NO_BETAS)
    if state is not None:
        refuse(state == BETAS_NO_FACTOR_HISTORY, NO_FACTOR_HISTORY)
        refuse(state == BETAS_SHORT_HISTORY, SHORT_HISTORY)
    refuse(~np.isfinite(np.column_stack([values[c] for c in columns])).all(axis=1), NO_BETAS)
    ends = {t: cum[t][last] for t in FACTOR_ETFS}
    refuse(~np.isfinite(np.column_stack(list(ends.values()))).all(axis=1), NO_FACTOR_BAR)
    spy = ends[BENCHMARK]
    explained = values["beta_mkt"] * spy
    for ticker, column in FACTORS:
        explained = explained + values[column] * (ends[ticker] - spy)
    done = live[pending]
    factor[done] = explained[pending]
    residual[done] = forward["fwd_return"].to_numpy(dtype=float)[done] - explained[pending]


def _numbers(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
