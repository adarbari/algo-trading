"""A multi-stage option position's book over stored rows (ADR 0088, X7, EF-G13): the generic
reader of ``portfolio/cycle.py``'s phases. Each phase is an outcome (its position at its delta
and tenor); each is stored at every hold in its ``horizon_sessions``, and on an entry session the
row that counts is the one whose hold ends on its own expiry: chosen from the row's legs and
window alone, never from how it ended, so no outcome picks its own row and only what the entry's
chain and the calendar fix is read. Only the rows of the phase's own position key count.

The book is the cycles' evidence (``portfolio/ladder.py``: one slot per named instrument, a cycle
holds one slot's capital, no overlap, so depth 1) with the split of the return into stock and
option legs. Each phase is valued as ``trade_frame`` values any option trade (net of the site's
option cost levels and commission), so a cycle adds no second valuation. A new cycle starts only
where ``may_start`` (the setup's gate at the entry's decision session) lets it; a cycle in
progress is never cut by the gate (its shares are held either way)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Edge, Outcome
from algotrade.config.edges.positions.key import position_key
from algotrade.config.edges.verdict import OptionCosts
from algotrade.core.time.calendar import next_session
from algotrade.data import StoreReader
from algotrade.engines.structures.trades import SHARES_PER_CONTRACT
from algotrade.services.evaluation.cross_section.hit import apply_outcome
from algotrade.services.evaluation.cross_section.portfolio.cycle import (
    CycleRow,
    Transitions,
    chain,
    stock_share,
)
from algotrade.services.evaluation.cross_section.portfolio.ladder import book_figures, cohorts
from algotrade.services.evaluation.evidence.shapes import trade_frame
from algotrade.services.evaluation.time_series import harness


def cycle_book(
    reader: StoreReader,
    edge: Edge,
    phases: Mapping[str, Outcome],
    transitions: Transitions,
    start: str,
    symbols: Mapping[str, str],
    names: int,
    entries: Sequence[date],
    may_start: Callable[[date], bool | None],
    as_of: datetime,
    option_costs: OptionCosts | None = None,
) -> dict[str, float | int | str | None]:
    """``edge``'s cycle book over the ``entries`` (S) of ``symbols`` (symbol -> instrument id) of
    ``names`` named instruments (one slot each, resolved or not): the book's figures
    (``ladder.book_figures``), the split of its return (``cycle.stock_share``) and ``lost``, the
    phases dropped (a missing row or spot ends a cycle)."""
    placements = sorted(set(entries))
    sessions = sorted({*placements, *(next_session(s) for s in placements)})
    holds = sorted({h for o in phases.values() for h in o.horizon_sessions})
    read = harness.read_trade_holds(reader, list(symbols.values()), sessions, holds, as_of)
    trades: list[tuple[str, date, date, float]] = []
    lost = 0
    stock = option = 0.0
    for symbol, instrument in symbols.items():
        rows = {
            phase: _phase_rows(edge, outcome, instrument, sessions, read, option_costs)
            for phase, outcome in phases.items()
        }
        made, dropped = chain(rows, placements, next_session, may_start, transitions, start)
        lost += sum(dropped.values())
        trades += [(symbol, t.entry, t.exit, t.value) for t in made]
        share = stock_share(made)
        stock += float(share["stock_return"] or 0.0)
        option += float(share["option_return"] or 0.0)
    book = cohorts(trades, names, 1)
    total = stock + option
    return {
        **book_figures(book, names),
        "stock_return": stock,
        "option_return": option,
        "stock_share": stock / total if total > 0 else None,
        "lost": lost,
    }


def _phase_rows(
    edge: Edge,
    outcome: Outcome,
    instrument: str,
    sessions: Sequence[date],
    read: Mapping[int, tuple[pd.DataFrame, pd.DataFrame]],
    option_costs: OptionCosts | None,
) -> dict[date, CycleRow | None]:
    """The phase's row entered on each of ``sessions``, from the hold that ends on its expiry;
    None for an entry whose expiry-held row is UNMEASURED or has no value (the cycle breaks
    there), absent where no stored row is held to its expiry (no row)."""
    out: dict[date, CycleRow | None] = {}
    for hold in outcome.horizon_sessions:
        held = replace(edge, outcome=replace(outcome, horizon_sessions=(hold,)),
                       variants=(), variant_grid=())  # fmt: skip
        key = position_key(held.outcome, hold)
        trades, paths = read[hold]
        if paths.empty or trades.empty:
            continue
        trades = trades[(trades["instrument_id"] == instrument) & (trades["position_key"] == key)]
        paths = paths[(paths["instrument_id"] == instrument) & (paths["position_key"] == key)]
        trade_days = pd.to_datetime(trades["session_date"]).dt.date
        path_days = pd.to_datetime(paths["session_date"]).dt.date
        for s in sessions:
            if s in out:
                continue
            at, raw = trades[(trade_days == s).to_numpy()], paths[(path_days == s).to_numpy()]
            if at.empty or raw.empty or not _held_to_expiry(raw.iloc[0]):
                continue
            out[s] = _row(held, at, raw.iloc[0], s, option_costs)
    return out


def _items(value: object) -> list[Any]:
    """A stored list column's value as a list (the store hands back arrays; null: empty)."""
    return [] if value is None else list(value)  # type: ignore[call-overload]


def _held_to_expiry(raw: pd.Series) -> bool:
    """The row's window ends on its legs' first expiry (an option leg expires with the hold)."""
    expiries = [pd.Timestamp(e).date() for e in _items(raw.get("leg_expiries")) if pd.notna(e)]
    return bool(expiries) and pd.Timestamp(raw["window_end"]).date() == min(expiries)


def _row(
    edge: Edge, at: pd.DataFrame, raw: pd.Series, s: date, option_costs: OptionCosts | None
) -> CycleRow | None:
    if raw["outcome_status"] == "UNMEASURED":
        return None
    result = apply_outcome(edge, at.iloc[:1], option_costs=option_costs)
    frame = trade_frame(edge, at.iloc[:1], result, entry=s, bars_exit=None, side="long",
                        option_costs=option_costs)  # fmt: skip
    value = float(pd.to_numeric(frame["return_on_capital"]).iloc[0])
    capital = float(pd.to_numeric(frame["capital"]).iloc[0])
    exit_ = frame["exit_session"].iloc[0]
    if not (np.isfinite(value) and np.isfinite(capital) and capital > 0) or exit_ is None:
        return None
    path = [float(x) for x in _items(raw.get("spot_path"))]
    stock = pd.to_numeric(pd.Series([raw.get("stock_pnl")]), errors="coerce").iloc[0]
    kinds, qty = _items(raw.get("leg_kinds")), _items(raw.get("leg_qty"))
    return CycleRow(
        entry=s,
        exit=pd.Timestamp(exit_).date(),
        pnl=value * capital,
        stock=0.0 if not np.isfinite(stock) else float(stock),
        assigned=str(frame["exit_kind"].iloc[0]) == "ASSIGNED",
        collateral=capital,
        entry_spot=float(raw["entry_spot"]) if np.isfinite(raw["entry_spot"]) else None,
        last_spot=path[-1] if path and np.isfinite(path[-1]) else None,
        shares=float(sum(q for k, q in zip(kinds, qty, strict=False) if k == "shares"))
        / SHARES_PER_CONTRACT,  # per share of one contract, as the engine counts it
    )
