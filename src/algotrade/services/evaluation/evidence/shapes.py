"""The mapping of each outcome shape to the trade contract (ADR 0088, design 2.5a): pure over
frames, called right after ``hit.apply_outcome`` (which it never edits, so ``value``, ``hit`` and
``excluded`` are the harness's own) by each consumer, and by the time-series valuation.

- ``excess_return`` (shares): capital basis ``notional``, price source ``bars``; the return on
  capital is the name's raw ``fwd_return`` less the document's ``cost_bps`` (a short pick: minus
  it, less the borrow); ``max_adverse`` is the window's dip for a long and null for a short.
- ``option_pnl``: the template's collateral rule; ``capital`` the stored collateral per unit; the
  return on capital is the mid P&L over it before cost, and net of the half-spreads and
  ``cost_bps`` of the entry spot at the document's level; the stored exit session, exit kind,
  ``max_adverse``, price source and licence. No collateral stored (a ``regt`` template) or not
  positive: no return on capital, the row still counts for value and hit.
- ``expires_otm`` and ``hit_target``: a hit rate with no money: basis ``none``, no return on
  capital. ``option_model_pnl``: notional, price source ``model``. ``pair_spread``: its two legs
  as one row (the spread is the return on capital).
- ``series_trades``: the windows of a time-series edge; ``book_trades``: a ``portfolio_return``
  book's per-session series, for the evidence only (never ledger rows).

A figure not known is null, never 0."""

from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.services.evaluation.cross_section.hit import borrow_cost, chain_rows
from algotrade.services.evaluation.evidence.contract import (
    BARS,
    BOOK_ID,
    COLUMN_NAMES,
    DELISTED,
    FIGURES,
    HORIZON,
    MODEL,
    capital_basis_of,
    empty_trades,
)

OPEN = "open"
BOOK = "book"
MEASURED = "measured"  # the status of a series row of a measured session


def _column(frame: pd.DataFrame, name: str) -> np.ndarray:
    """``frame[name]`` as floats, NaN where the value or the column is absent."""
    if name not in frame.columns:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)


def _strings(frame: pd.DataFrame, name: str, default: str) -> np.ndarray:
    if name not in frame.columns:
        return np.full(len(frame), default, dtype=object)
    return frame[name].fillna(default).astype(str).to_numpy(dtype=object)


def _dates(values: Any) -> list[date | None]:
    return [None if pd.isna(v) else pd.Timestamp(v).date() for v in values]


def _finite(values: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """``values`` where ``keep`` and finite, NaN elsewhere (a figure is never 0 by default)."""
    with np.errstate(invalid="ignore"):
        return np.where(keep & np.isfinite(values), values, np.nan)


def _assemble(**columns: Any) -> pd.DataFrame:
    """The contract's frame from its columns by name; every figure is null on an excluded row."""
    frame = pd.DataFrame({name: columns[name] for name in COLUMN_NAMES})
    counted = (frame["excluded"].astype(str) == "").to_numpy()
    for name in ("value", *FIGURES):
        frame[name] = _finite(frame[name].to_numpy(dtype=np.float64, na_value=np.nan), counted)
    frame.loc[~counted, "exit_kind"] = None
    return frame


def _bar_exit_kinds(stored: pd.DataFrame) -> np.ndarray:
    return np.where(_strings(stored, "outcome_status", "") == DELISTED, DELISTED, HORIZON).astype(
        object
    )


def _bars(stored: pd.DataFrame, *, short: bool, cost: float, borrow: np.ndarray) -> dict[str, Any]:
    """The share figures of rows over stored forward returns: the return on capital before and
    after cost, the dip, the underlying's return, the exit kind (one body for the harness's picks
    and the time-series windows)."""
    fwd = _column(stored, "fwd_return")
    gross = -fwd if short else fwd
    return {
        "return_on_capital_gross": gross,
        "return_on_capital": gross - cost - (borrow if short else 0.0),
        "max_adverse": np.full(len(stored), np.nan)
        if short
        else _column(stored, "fwd_max_drawdown"),
        "underlying_return": fwd,
        "exit_kind": _bar_exit_kinds(stored),
    }


def _no_capital(n: int) -> dict[str, Any]:
    nan = np.full(n, np.nan)
    return {
        "capital": nan, "return_on_capital_gross": nan, "return_on_capital": nan,
        "max_adverse": nan, "underlying_return": nan,
    }  # fmt: skip


def _options(stored: pd.DataFrame, cost: float) -> dict[str, Any]:
    """The option figures of rows of the option trade grain."""
    collateral = _column(stored, "collateral")
    with np.errstate(invalid="ignore", divide="ignore"):
        has = np.isfinite(collateral) & (collateral > 0)
        spread = _column(stored, "entry_half_spread") + _column(stored, "exit_half_spread")
        mid = _column(stored, "pnl_mid")
        spot = _column(stored, "entry_spot")
        gross = np.where(has, mid / collateral, np.nan)
        net = np.where(has, (mid - spread - cost * spot) / collateral, np.nan)
    kinds = (
        stored["exit_kind"] if "exit_kind" in stored.columns else pd.Series([None] * len(stored))
    )
    return {
        "capital": np.where(has, collateral, np.nan),
        "return_on_capital_gross": gross,
        "return_on_capital": net,
        "max_adverse": _column(stored, "max_adverse"),
        "underlying_return": np.full(len(stored), np.nan),
        "exit_kind": kinds.astype(object).where(kinds.notna(), None).to_numpy(dtype=object),
    }


def trade_frame(
    edge: Edge, rows: pd.DataFrame, result: pd.DataFrame, *, entry: date,
    bars_exit: date | None, side: str,
) -> pd.DataFrame:  # fmt: skip
    """The contract's rows for ``result`` (``apply_outcome``'s frame, or ``hit.short_view`` of it
    for a short leg; ``instrument_id`` a column or the index): one row per name of it, from the
    stored outcome ``rows`` it was scored over (the first row of each name, the edge's own
    position key for an option trade). ``entry``: S; ``bars_exit``: S + h sessions, the exit of a
    row over stored prices."""
    o = edge.outcome
    res = result if "instrument_id" in result.columns else result.reset_index()
    res = res.reset_index(drop=True)
    basis = capital_basis_of(edge)  # raises for a book: it has no name-by-name trades
    stored = (
        chain_rows(edge, rows)
        .drop_duplicates("instrument_id")
        .set_index("instrument_id")
        .reindex(res["instrument_id"])
        .reset_index()
    )
    n = len(res)
    cost = (o.cost_bps or 0.0) / 1e4
    borrow = borrow_cost(o.borrow_bps_annual, _column(stored, "horizon_sessions"))
    short = side == "short"
    source, licence = BARS, np.full(n, OPEN, dtype=object)
    exits: Sequence[date | None] = [bars_exit] * n
    figures: dict[str, Any]
    if o.kind == CHAIN_KIND:
        figures = _options(stored, cost)
        source = _strings(stored, "price_source", "cboe")  # type: ignore[assignment]
        licence = _strings(stored, "licence", OPEN)
        exits = _dates(stored["exit_session"]) if "exit_session" in stored.columns else [None] * n
    elif o.kind == "excess_return":
        figures = {"capital": np.full(n, np.nan), **_bars(
            stored, short=short, cost=cost, borrow=borrow
        )}  # fmt: skip
    elif o.kind in ("expires_otm", "hit_target"):
        figures = {**_no_capital(n), "underlying_return": _column(stored, "fwd_return")}
        figures["exit_kind"] = _bar_exit_kinds(stored)
    else:
        value = res["value"].to_numpy(dtype=np.float64, na_value=np.nan)
        gross = value + (2 * cost + borrow if o.kind == "pair_spread" else cost)
        figures = {**_no_capital(n), "return_on_capital_gross": gross, "return_on_capital": value,
                   "underlying_return": _column(stored, "fwd_return")}  # fmt: skip
        figures["exit_kind"] = _bar_exit_kinds(stored)
        source = MODEL if o.kind == "option_model_pnl" else BARS
    return _assemble(
        instrument_id=res["instrument_id"].to_numpy(dtype=object),
        side=side, entry_session=entry, exit_session=exits,
        value=res["value"].to_numpy(dtype=np.float64, na_value=np.nan),
        higher_is_better=o.sign > 0, hit=res["hit"].to_numpy(dtype=bool),
        excluded=res["excluded"].astype(str).to_numpy(dtype=object),
        delisted=res["delisted"].to_numpy(dtype=bool),
        capital_basis=basis, price_source=source, outcome_licence=licence, **figures,
    )  # fmt: skip


def series_trades(edge: Edge, rows: pd.DataFrame) -> pd.DataFrame:
    """The contract's rows for the measured forward ``rows`` (``select_outcomes``') of a
    time-series edge's windows: the value is the raw ``fwd_return``, a hit is a positive one, the
    exit the stored ``window_end``. Empty rows give an empty frame."""
    if rows.empty:
        return empty_trades()
    n = len(rows)
    rows = rows.reset_index(drop=True)
    value = _column(rows, "fwd_return")
    counted = np.isfinite(value)
    with np.errstate(invalid="ignore"):
        hit = value > 0
    bars = _bars(rows, short=False, cost=(edge.outcome.cost_bps or 0.0) / 1e4,
                 borrow=np.zeros(n))  # fmt: skip
    return _assemble(
        instrument_id=rows["instrument_id"].to_numpy(dtype=object), side="long",
        entry_session=_dates(rows["session_date"]),
        exit_session=_dates(rows["window_end"]) if "window_end" in rows.columns else [None] * n,
        value=value, higher_is_better=True, hit=hit,
        excluded=np.where(counted, "", "missing_value").astype(object),
        delisted=_strings(rows, "outcome_status", "") == DELISTED,
        capital_basis="notional", capital=np.full(n, np.nan), price_source=BARS,
        outcome_licence=OPEN, **bars,
    )  # fmt: skip


def book_trades(series: pd.DataFrame) -> pd.DataFrame:
    """The contract's rows for a ``portfolio_return`` run's ``results/edge_series`` rows (the
    screener's, measured sessions): one row per block, ``BOOK_ID``, the return on capital the
    block's ``pick_mean``. For the evidence only: the ledger never lists a book."""
    keep = series[(series["role"] == "screener") & (series["status"] == MEASURED)]
    keep = keep.reset_index(drop=True)
    n = len(keep)
    if not n:
        return empty_trades()
    mean = _column(keep, "pick_mean")
    nan = np.full(n, np.nan)
    with np.errstate(invalid="ignore"):
        hit = mean > 0
    return _assemble(
        instrument_id=BOOK_ID, side="long", entry_session=_dates(keep["entry_session"]),
        exit_session=_dates(keep["exit_session"]), exit_kind=HORIZON, value=mean,
        higher_is_better=True, hit=hit, excluded=np.where(np.isfinite(mean), "", "missing_value"),
        delisted=False, capital_basis=BOOK, capital=nan, return_on_capital_gross=mean,
        return_on_capital=mean, max_adverse=nan, underlying_return=nan, price_source=BARS,
        outcome_licence=OPEN,
    )  # fmt: skip


__all__ = ["book_trades", "series_trades", "trade_frame"]
