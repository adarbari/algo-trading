"""The forward-outcome arithmetic of the ``outcomes`` task (ADR 0053 decision 3): for one window
(start session S, end session T, horizon h) and the names eligible at S, each name's return and
path fields from daily bars split-adjusted as of T (``data.prices.SessionBars.window``).

A name is eligible when it was in the universe at S and has a bar at S. Its row is
- COMPLETE when it has a bar at T: ``fwd_return`` = close(T) / close(S) - 1;
- DELISTED when it has no bar at T and the reference records it delisted after S (the weekly
  reference build stamps ``delisted_on`` when it notices, after the last bar; the task passes
  only the stamps within the ``RECHECK`` sessions after T, the listing history's last trading
  days on or before T): measured to its
  last bar in the window (a name whose last bar is S: a zero return, no volatility); the
  delisting return itself (a cash-out, a final print) is not measured;
- otherwise absent, with a reason (a gap at T, or a name not yet recorded as delisted: the
  task recomputes recent windows each night, so a later reference build turns it into a row).

The path fields run over the bars after S up to the measured end: ``fwd_max_return`` from the
highs (favourable excursion), ``fwd_max_drawdown`` from the lows (adverse excursion, a positive
fraction, 0 when no low is below close(S)), ``fwd_realised_vol`` the annualised standard
deviation of the daily log close returns (null under two returns). ``fwd_excess_return`` is
``fwd_return`` minus the benchmark's over the same sessions (null without its bars). Pure: no
storage, no clock.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

TRADING_DAYS = 252  # annualises the realised volatility
NO_END_BAR = "no bar at the window end (a gap, or left the universe without a delisting date)"
_COLUMNS = (
    "instrument_id", "fwd_return", "fwd_excess_return", "fwd_max_return", "fwd_max_drawdown",
    "fwd_realised_vol", "outcome_status",
)  # fmt: skip


@dataclass(frozen=True)
class Window:
    """``sessions`` are the exchange sessions S..T (h + 1 of them)."""

    sessions: tuple[date, ...]

    @property
    def start(self) -> date:
        return self.sessions[0]

    @property
    def end(self) -> date:
        return self.sessions[-1]

    @property
    def horizon(self) -> int:
        return len(self.sessions) - 1


def window_rows(
    bars: pd.DataFrame,
    window: Window,
    eligible: Collection[str],
    benchmark: str | None,
    delisted: Mapping[str, date],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """``bars`` (``instrument_id``, ``session_date``, ``high``, ``low``, ``close``; S..T, adjusted
    as of T) -> (one row per measured name, ``_COLUMNS``; reason per eligible name without one).
    ``eligible``: the universe at S (names without a bar at S are dropped, not reasons);
    ``benchmark``: its instrument id, or None; ``delisted``: id -> delisting date, as the
    latest reference snapshot records it."""
    close, high, low = (_wide(bars, window, field) for field in ("close", "high", "low"))
    ids = np.array(
        [i for i in close.columns if i in eligible and pd.notna(close.at[window.start, i])]
    )
    if not len(ids):
        return pd.DataFrame(columns=list(_COLUMNS)), {}
    c = close[ids].to_numpy(dtype=float)
    complete = ~np.isnan(c[-1])
    gone = np.array([_gone(delisted.get(i), window) for i in ids])
    kept = complete | gone
    reasons = {str(i): NO_END_BAR for i in ids[~kept]}
    ids, c, complete = ids[kept], c[:, kept], complete[kept]
    last = _last_bar(c)
    start = c[0]
    fwd = c[last, np.arange(len(ids))] / start - 1
    rows = pd.DataFrame(
        {
            "instrument_id": ids,
            "fwd_return": fwd,
            "fwd_excess_return": fwd - _benchmark_return(close, benchmark, last),
            "fwd_max_return": _excursion(high[ids], last, start, np.fmax) / start - 1,
            "fwd_max_drawdown": np.maximum(
                0.0, 1 - _excursion(low[ids], last, start, np.fmin) / start
            ),
            "fwd_realised_vol": _realised_vol(c, last),
            "outcome_status": np.where(complete, "COMPLETE", "DELISTED"),
        }
    )
    return rows, reasons


def _wide(bars: pd.DataFrame, window: Window, field: str) -> pd.DataFrame:
    """``field`` as sessions x instruments over exactly S..T (a session with no bars: NaN)."""
    frame = bars.assign(instrument_id=bars["instrument_id"].astype(str))
    wide = frame.pivot(index="session_date", columns="instrument_id", values=field)
    return wide.reindex(list(window.sessions))


def _gone(delisted_on: date | None, window: Window) -> bool:
    return delisted_on is not None and pd.notna(delisted_on) and delisted_on > window.start


def _last_bar(c: np.ndarray) -> np.ndarray:
    """Per column, the row of its last bar (row 0, S, always has one)."""
    present = ~np.isnan(c)
    return len(c) - 1 - np.argmax(present[::-1], axis=0)


def _through(values: np.ndarray, last: np.ndarray) -> np.ndarray:
    """``values`` after S up to each column's ``last`` row; NaN elsewhere."""
    rows = np.arange(len(values))[:, None]
    return np.where((rows >= 1) & (rows <= last[None, :]), values, np.nan)


def _excursion(
    values: pd.DataFrame, last: np.ndarray, start: np.ndarray, pick: np.ufunc
) -> np.ndarray:
    """The extreme (``np.fmax`` / ``np.fmin``) of ``values`` after S; close(S) when none."""
    out = pick.reduce(_through(values.to_numpy(dtype=float), last), axis=0)  # NaN ignored
    return np.where(np.isnan(out), start, out)


def _realised_vol(c: np.ndarray, last: np.ndarray) -> np.ndarray:
    """Annualised stdev of the log returns between consecutive bars from S to ``last``."""
    logs = pd.DataFrame(np.log(np.where(np.arange(len(c))[:, None] <= last[None, :], c, np.nan)))
    returns = logs - logs.ffill().shift(1)
    vol: np.ndarray = (returns.std(ddof=1) * np.sqrt(TRADING_DAYS)).to_numpy(dtype=float)
    return vol


def _benchmark_return(close: pd.DataFrame, benchmark: str | None, last: np.ndarray) -> np.ndarray:
    """The benchmark's return from S to each name's measured end (NaN without both bars)."""
    if benchmark is None or benchmark not in close.columns:
        return np.full(len(last), np.nan)
    b = close[benchmark].to_numpy(dtype=float)
    out: np.ndarray = b[last] / b[0] - 1
    return out
