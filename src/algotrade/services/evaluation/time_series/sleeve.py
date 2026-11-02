"""A named option sleeve (ADR 0088 decision 14, amending ADR 0073 decision 1): an edge with
``base = "delta_equivalent"`` holds its option position on each of 1 to 10 named instruments at
every decision session D its schedule places (S = D + the offset, the cross-section's legs:
``cross_section/sessions.leg_blocks``) and is judged against the delta-equivalent stock: at the
same S, the position's entry delta in shares, held to the position's hold cap. Both are returns on
the position's collateral net of the document's ``cost_bps`` of the stock each controls (the
option: one unit's entry spot, as ``trade_frame`` charges it; the stock: ``|delta|`` of it), so
the pair differs by what the option structure adds over its linear exposure.

A trial is one (edge variant, symbol): the edge itself, each ``[[variants]]`` and each
``[[variant_grid]]`` point (``positions/key.grid_outcomes``), each read under its own
``position_key``. A measured trade gives the period's value (the trade contract's
``return_on_capital``, ``evidence/shapes.trade_frame``) and the base value beside it, as two
observations of one period (``inside`` the trade, outside the base), so ``measures.measure`` reads
the trade against the base and the paired series (the trade minus the base) as it reads a window
against its stretch: Welch t, the Sharpe ratio of the pairs, the hit rates. A trade with no row or
no value is counted under its reason in ``lost``, never filled; a trade whose base has no value is
unpaired (``excluded_missing``). No random window sets and no timing Sharpe ratio: the base is the
same-session stock, not other periods. A known approximation: the stock is held to the hold cap
even when a trade's exit rule closed it earlier (the stock outcome is stored at fixed horizons).

The one-session rule holds: the option and stock rows are read at their own S as of ``as_of``
through ``harness.py`` (the package's one importer of ``data.outcomes``)."""

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.config.edges.document import MAIN, Edge, Outcome
from algotrade.config.edges.named import DELTA_EQUIVALENT, named_symbols
from algotrade.config.edges.positions.key import grid_outcomes, position_key
from algotrade.config.edges.positions.templates import Templates
from algotrade.config.edges.verdict import OptionCosts
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.evaluation.cross_section.hit import apply_outcome, chain_rows
from algotrade.services.evaluation.cross_section.reads.cases import (
    case_keys,
    cased_rows,
    check_cases,
    read_cases,
)
from algotrade.services.evaluation.cross_section.sessions import leg_blocks
from algotrade.services.evaluation.evidence.contract import empty_trades
from algotrade.services.evaluation.evidence.shapes import trade_frame
from algotrade.services.evaluation.time_series import harness
from algotrade.services.evaluation.time_series.evaluate import InstrumentResult, TimeSeriesRun
from algotrade.services.evaluation.time_series.measures import Obs, measures
from algotrade.services.evaluation.time_series.periods import Period
from algotrade.services.features import site_features

NO_VALUE = "NO_VALUE"  # a measured trade the contract gives no return on capital (no collateral)


def sleeve_outcomes(edge: Edge, templates: Templates) -> tuple[tuple[str, Outcome], ...]:
    """``(edge variant, outcome)`` of every trial of a sleeve: ``main``, each ``[[variants]]``,
    then each grid point (``templates``: the site's, to resolve a point's legs)."""
    return (
        (MAIN, edge.outcome),
        *((v.id, v.outcome) for v in edge.variants),
        *grid_outcomes(edge, templates),
    )


def evaluate_sleeve(
    reader: StoreReader,
    edge: Edge,
    outcomes: Sequence[tuple[str, Outcome]],
    start: date,
    end: date,
    as_of: datetime,
    label: Callable[[date], str],
    split: date | None,
    exploratory: bool,
    gate: Callable[[date], str] | None = None,
    option_costs: OptionCosts | None = None,
    domains: Mapping[str, Sequence[str]] | None = None,
    features: FeatureSet | None = None,
) -> TimeSeriesRun:
    """``edge`` (``base = "delta_equivalent"``) for each of ``outcomes`` (``sleeve_outcomes``)
    over the decision sessions in ``start..end``; ``label``, ``split`` and ``gate`` as for
    ``evaluate_time_series``; ``option_costs``: the commission a trade pays. A trial with case
    values (E13b) takes, at each D, the point the symbol's cases resolve to from D's partition
    (``reads/cases.py``; ``domains``: the catalogue's string domains), never the default when a
    case is UNKNOWN (``CASE_UNKNOWN``, lost); ``features``: the catalogue its case fields are
    checked against at run start (G9-M4)."""
    if edge.base != DELTA_EQUIVALENT or not isinstance(edge.universe, Selection):
        raise ConfigurationError(f"edge {edge.id}: not a named option sleeve")
    for _, outcome in outcomes:  # each trial's case values (a variant's or a grid point's)
        check_cases(reader, replace(edge, outcome=outcome), features or site_features(), start,
                    end, as_of)  # fmt: skip
    symbols = named_symbols(edge.universe, base=DELTA_EQUIVALENT)
    ids, unknown = harness.resolve_symbols(reader, symbols, end, as_of)
    days = sessions_between(start, end)
    # by (hold, entry offset): a variant may move either, and its legs and keys move with them
    reads: dict[tuple[int, int], tuple[list[Period], pd.DataFrame, harness.Returns]] = {}
    results = []
    for variant, outcome in outcomes:
        held = replace(edge, outcome=outcome, variants=(), variant_grid=())
        horizon = outcome.horizon_sessions[0]
        at = (horizon, outcome.start_offset_sessions)
        if at not in reads:
            ps = [
                Period(leg.entry, leg.entry, leg.decision, True)
                for block in leg_blocks(held, None, days, horizon)
                for leg in block
            ]
            entries = [p.entry for p in ps]
            found = list(ids.values())
            reads[at] = (
                ps,
                harness.read_trades(reader, found, entries, horizon, as_of),
                harness.read_returns(reader, found, entries, horizon, as_of),
            )
        ps, trades, stock = reads[at]
        mine, out = _cased(reader, held, trades, ps, list(ids.values()), domains)
        for symbol in symbols:
            results.append(
                _trial(held, variant, symbol, ids.get(symbol), unknown.get(symbol), ps, mine,
                       stock, label, gate, split, exploratory, option_costs, out)
            )  # fmt: skip
    main = reads[edge.outcome.horizon_sessions[0], edge.outcome.start_offset_sessions][0]
    measured = {e for r in results if r.edge_variant == MAIN for e, _ in r.in_window}
    return TimeSeriesRun(
        edge.schedule,
        edge.outcome.horizon_sessions[0],
        len(main),
        sum(p.entry not in measured for p in main),
        tuple(results),
    )


def _trial(
    edge: Edge,
    variant: str,
    symbol: str,
    instrument: str | None,
    unknown: str | None,
    ps: list[Period],
    rows: pd.DataFrame,
    stock: harness.Returns,
    label: Callable[[date], str],
    gate: Callable[[date], str] | None,
    split: date | None,
    exploratory: bool,
    option_costs: OptionCosts | None,
    held_out: Mapping[tuple[str, date], str] | None = None,
) -> InstrumentResult:
    horizon = edge.outcome.horizon_sessions[0]
    mine = rows[rows["instrument_id"] == instrument] if instrument is not None else rows.iloc[:0]
    starts = pd.to_datetime(mine["session_date"]).dt.date
    lost: Counter[str] = Counter()
    obs: list[Obs] = []
    frames: dict[date, pd.DataFrame] = {}
    for p in ps:
        at = mine[(starts == p.entry).to_numpy()]
        if instrument is None:
            lost[unknown or harness.UNKNOWN_SYMBOL] += 1
            continue
        why = (held_out or {}).get((instrument, p.entry))
        if why:  # its cases were UNKNOWN at D (or D's market row was missing): never the default
            lost[why] += 1
            continue
        if at.empty:
            lost[harness.NO_OUTCOME] += 1
            continue
        row = at.iloc[0]
        if row["outcome_status"] == "UNMEASURED":
            lost[f"UNMEASURED:{row.get('outcome_reason') or 'UNKNOWN'}"] += 1
            continue
        result = apply_outcome(edge, at.iloc[:1], option_costs=option_costs)
        trade = trade_frame(edge, at.iloc[:1], result, entry=p.entry, bars_exit=None,
                            side="long", option_costs=option_costs)  # fmt: skip
        why = str(trade.at[0, "excluded"] or "")
        value = float(pd.to_numeric(trade["return_on_capital"]).iloc[0])
        if why or not np.isfinite(value):
            lost[why or NO_VALUE] += 1
            continue
        base = _base(row, stock.values.get((instrument, p.entry)), edge.outcome.cost_bps)
        state = "" if gate is None else gate(p.decision)
        regime = label(p.decision)
        paired = value - base if base is not None else None
        obs.append(Obs(p, value, regime, state, paired))
        if base is not None:
            obs.append(Obs(replace(p, inside=False), base, regime, state))
        frames[p.entry] = trade
    every = obs
    if gate is not None:  # the sleeve's own series: the open sessions (the slices hold the rest)
        obs = [o for o in obs if o.gate == "open"]
    inside = [o for o in obs if o.period.inside]
    kept = [frames[o.period.entry] for o in inside]
    key = position_key(edge.outcome, horizon)
    spec = edge.outcome.position
    if spec is not None and spec.points:  # a case-valued trial is the set of its points
        key = hashlib.sha256("|".join(sorted(k for _, _, k in spec.points)).encode()).hexdigest()
    return InstrumentResult(
        symbol=symbol,
        horizon=horizon,
        measures=measures(every, horizon, split, exploratory),
        randoms=(),
        in_window=tuple((o.period.entry, o.value) for o in inside),
        paired=tuple((o.period.entry, o.paired) for o in inside if o.paired is not None),
        timing={},
        lost=dict(lost),
        trades=pd.concat(kept, ignore_index=True) if kept else empty_trades(),
        edge_variant=variant,
        identity=f"{edge.id}|{edge.schedule}|{symbol}|{key}|{edge.outcome.cost_bps}",
    )


def _cased(
    reader: StoreReader,
    edge: Edge,
    trades: pd.DataFrame,
    ps: Sequence[Period],
    ids: Sequence[str],
    domains: Mapping[str, Sequence[str]] | None,
) -> tuple[pd.DataFrame, dict[tuple[str, date], str]]:
    """``trades`` (every key) narrowed to ``edge``'s own rows (``chain_rows``) and, for a trial
    with case values, each symbol's row at the point its cases resolve to at each period's D (from
    D's partition only, relabelled to the default key: ``reads/cases.cased_rows``), with why each
    (instrument, S) has none (``CASE_UNKNOWN``, or the market table of a gap at D)."""
    keys = case_keys(edge.outcome)
    if keys is None:
        return chain_rows(edge, trades), {}
    starts = pd.to_datetime(trades["session_date"]).dt.date
    parts, out = [], {}
    for p in ps:
        resolved = read_cases(reader, keys.cases, ids, p.decision, domains)
        why = dict.fromkeys(ids, resolved.gap) if resolved.gap else resolved.reasons
        out.update({(i, p.entry): reason for i, reason in why.items()})
        at = trades[(starts == p.entry).to_numpy()]
        parts.append(at if resolved.gap else cased_rows(at, resolved, keys))
    kept = pd.concat(parts, ignore_index=True) if parts else trades.iloc[:0]
    return chain_rows(edge, kept), out


def _base(row: pd.Series, stock_return: float | None, cost_bps: float | None) -> float | None:
    """The delta-equivalent stock's return on the trade's collateral: ``position_delta`` shares
    per unit bought at the entry spot, held to the hold cap, less ``cost_bps`` of their value;
    None when the stock return, the delta, the spot or a positive collateral is missing."""
    figures = [
        stock_return,
        row.get("position_delta"),
        row.get("entry_spot"),
        row.get("collateral"),
    ]
    values = pd.to_numeric(pd.Series(figures, dtype=object), errors="coerce").to_numpy(dtype=float)
    r, delta, spot, collateral = values
    if not np.all(np.isfinite(values)) or collateral <= 0:
        return None
    cost = (cost_bps or 0.0) / 1e4
    return float(delta * spot * (r - np.sign(delta) * cost) / collateral)
