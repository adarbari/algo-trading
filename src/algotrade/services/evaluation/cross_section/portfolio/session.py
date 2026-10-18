"""One session of a portfolio_return outcome (ADR 0073): the value is the book's return over the
window minus the blended benchmark's over the same window, and a hit is a positive value after
the document's cost.

The book's weights are formed at D (``weights.py``); the window's returns are the stored
``fwd_return`` of each held name at S (one outcome partition: the same close-to-close window for
the book and the benchmark). The benchmark's constituents are universe instruments, so their rows
are in the grain beside every other name's: ``BENCHMARKS`` stays the set the grain stores and a
blend is computed here, from the constituents' own rows (a mix of SPY alone is SPY). ``CASH`` earns
the T-bill yield read at D over the window, ``yield * horizon / 252``.

A value that cannot be formed is *no value with a reason*, never a zero: a held name, or a
constituent of the benchmark, with no usable row at S (``no_pick_return``,
``no_benchmark_row:<ticker>``), a book with cash and no curve at D (``no_cash_yield``). The session
is then left out of the measures. The cost the stored value is net of is one full round trip (the
convention of every leg: ``reporting/turnover.py`` replaces it by the weight change)."""

import math
from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import pandas as pd

from algotrade.config.edges.portfolio import CASH
from algotrade.services.evaluation.cross_section.measures import SessionStat, decile_means
from algotrade.services.evaluation.cross_section.portfolio.weights import Weights

TRADING_DAYS = 252
FIELDS = ("fwd_return", "fwd_excess_return")  # the stored outcome fields a book reads (a window's
# return for the book and the blend; the excess return for the screen's deciles)
MIN_DECILE_NAMES = 20  # ranked names under which the decile figures are not applicable
NO_PICK_RETURN = "no_pick_return"  # a held name has no usable return at S
NO_BENCHMARK_ROW = "no_benchmark_row"  # a constituent of the benchmark has none ("...:<ticker>")
NO_CASH_YIELD = "no_cash_yield"  # a book holding cash, and no Treasury curve stored at D
UNMEASURED = "UNMEASURED"  # the stored ``outcome_status`` of a window over a flagged bar


def window_returns(rows: pd.DataFrame) -> dict[str, float]:
    """The usable ``fwd_return`` by instrument id of one entry session's rows: finite and not an
    UNMEASURED window (a name with no usable return is absent, never 0)."""
    values = pd.to_numeric(rows["fwd_return"], errors="coerce").to_numpy(dtype=np.float64)
    usable = np.isfinite(values) & (rows["outcome_status"] != UNMEASURED).to_numpy()
    ids = rows["instrument_id"].astype(str).to_numpy()
    return {i: float(v) for i, v, ok in zip(ids, values, usable, strict=True) if ok}


def cash_return(yield_at_d: float | None, horizon: int) -> float | None:
    """What a unit of cash earns over ``horizon`` sessions at the bill yield read at D (a decimal
    per year); None when no yield is known."""
    if yield_at_d is None or not math.isfinite(yield_at_d):
        return None
    return yield_at_d * horizon / TRADING_DAYS


def session_value(
    weights: Weights,
    blend: Sequence[tuple[str, float]],
    blend_ids: Mapping[str, str | None],
    returns: Mapping[str, float],
    cash: float | None,
) -> tuple[float | None, str]:
    """``(gross value, reason)``: the book's return minus the blend's, or None and why not.
    ``blend``: the benchmark's ``(ticker, weight)`` pairs; ``blend_ids``: each ticker's id at S
    (None: not a known instrument); ``returns``: ``window_returns``; ``cash``: ``cash_return``."""
    book = 0.0
    for name, weight in weights:
        if name == CASH:
            if cash is None:
                return None, NO_CASH_YIELD
            book += weight * cash
        elif name in returns:
            book += weight * returns[name]
        else:
            return None, NO_PICK_RETURN
    bench = 0.0
    for ticker, weight in blend:
        found = blend_ids.get(ticker)
        if found is None or found not in returns:
            return None, f"{NO_BENCHMARK_ROW}:{ticker}"
        bench += weight * returns[found]
    return book - bench, ""


def ranking_deciles(
    rows: pd.DataFrame,
    scores: Mapping[str, float],
    cost_bps: float | None,
    min_names: int = MIN_DECILE_NAMES,
) -> tuple[float, ...]:
    """The mean of each tenth of the ranked names' net excess returns, best-ranked first: the
    screen's ranking of the eligible names (``rows``: their outcome rows at S) over the window.
    Empty under ``min_names`` ranked names: a tenth of a small universe is a name or two, so the
    decile figures are not applicable there (served as N/A, never a noisy number)."""
    excess = pd.to_numeric(rows["fwd_excess_return"], errors="coerce").to_numpy(dtype=np.float64)
    ok = np.isfinite(excess) & (rows["outcome_status"] != UNMEASURED).to_numpy()
    by_id = {
        str(i): float(v) - (cost_bps or 0.0) / 1e4
        for i, v, good in zip(rows["instrument_id"], excess, ok, strict=True)
        if good
    }
    ranked = sorted((i for i in by_id if i in scores), key=lambda i: (-scores[i], i))
    return decile_means([by_id[i] for i in ranked]) if len(ranked) >= min_names else ()


def portfolio_stat(
    day: date,
    regime: str,
    value: float | None,
    reason: str,
    weights: Weights,
    cost_bps: float | None,
    deciles: tuple[float, ...] = (),
    ranked: int = 0,
) -> SessionStat:
    """The session's statistic: one value (the session's, net of one round trip of the document's
    cost; the picks of a book are one position) and a hit when it is positive. A session with no
    value is not measured (``excluded_coverage``) and says why (``portfolio_reason``). ``deciles``:
    the decile means of the screen's ranking (``ranking_deciles``; empty: not applicable),
    ``ranked`` the names they are over."""
    if value is None:
        return SessionStat(session=day, regime=regime, excluded_coverage=1, portfolio_reason=reason)
    net = value - (cost_bps or 0.0) / 1e4
    return SessionStat(
        session=day,
        regime=regime,
        pick_values=(net,),
        pick_hits=int(net > 0),
        weights=weights,
        deciles=deciles,
        top_decile=deciles[0] if deciles else None,
        spread=deciles[0] - deciles[-1] if deciles else None,
        ranked=ranked if deciles else 0,
    )
