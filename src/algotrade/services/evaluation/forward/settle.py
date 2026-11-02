"""Settle open paper trades from the stored outcomes (ADR 0053 amendment 2026-10-09).

An open trade (a name bought at ``buy_session``, sold ``horizon`` sessions later) is closed by
the outcome stored for it: ``cross_section/hit.apply_outcome`` is the one place an edge's
``[outcome]`` meets the stored fields, so a paper trade wins or loses exactly as a backtest row
would. Outcomes are read as of ``now`` (a window not closed has no row: the trade stays open,
never a loss). The edge's outcome is judged by the definition it had at the signal: a trade
whose edge's ``[outcome]`` changed since (``outcome_hash``) is skipped with that reason. A name
with no outcome row although its window's partition is stored has no entry bar (skipped); a
window with no outcome at all ``GRACE_SESSIONS`` after its sell session is skipped too, with
the reason: a missing result is never a loss and never a zero. An outcome that reads the implied
vol (``expires_otm``: the strike is set from it) reads it at the signal session D, as the harness
does (``reads.session.implied_at``, ``harness.iv_field_of``); a name whose vol
is missing or invalid there is skipped with that reason, never a loss. ``excess_return`` of a
settled trade is set only when the outcome's value is a return (not an ``expires_otm`` cushion);
``raw_return`` is the name's own ``fwd_return`` over the window (``forward_returns@v2``: the
close-to-close price return, no benchmark, no cost), set for a settled trade whose stored row has
one (not for an option P&L, whose ``fwd_return`` is the option's); the Past lists read it. It
comes from the trade contract (``evidence.shapes.trade_frame``, ADR 0088 2.5a), which also gives a
settled trade its ``exit_kind``, ``return_on_capital`` and ``price_source``."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.verdict import OptionCosts
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.outcomes import (
    NO_RESIDUAL_ROW,
    attach_residuals,
    read_chain,
    read_outcomes,
    read_residuals,
)
from algotrade.services.evaluation.cross_section.harness import iv_field_of
from algotrade.services.evaluation.cross_section.hit import (
    INVALID_IMPLIED_VOL,
    MISSING_DRAWDOWN,
    MISSING_VALUE,
    NO_IMPLIED_VOL,
    apply_outcome,
    is_return,
    needs_implied_vol,
    needs_residual,
)
from algotrade.services.evaluation.cross_section.measuring import BENCHMARK
from algotrade.services.evaluation.cross_section.reads.session import implied_at
from algotrade.services.evaluation.evidence.shapes import trade_frame
from algotrade.services.evaluation.forward.signals import advance

GRACE_SESSIONS = 5  # sessions after a window's close an outcome may still be stored
OPEN, WON, LOST, SKIPPED = "open", "won", "lost", "skipped"
# What a reader sees for the harness's exclusion codes (a trader's sentence, never the code).
REASONS = {
    MISSING_VALUE: "the result could not be computed (no benchmark return)",
    MISSING_DRAWDOWN: "the worst drawdown of the window could not be computed",
    NO_IMPLIED_VOL: "no implied vol was stored for the name at the signal session",
    INVALID_IMPLIED_VOL: "the implied vol stored at the signal session was not usable",
}


@dataclass(frozen=True)
class Settled:
    """One trade's new state (``status`` won / lost / skipped); ``excess_return`` None unless
    counted; ``raw_return`` the stored ``fwd_return`` (None: skipped, or none stored)."""

    instrument_id: str
    status: str
    reason: str
    excess_return: float | None
    delisted: bool
    raw_return: float | None = None
    exit_kind: str | None = None  # the trade contract's (ADR 0088, 2.5a), for a settled trade
    return_on_capital: float | None = None
    price_source: str | None = None
    outcome_licence: str | None = None  # the outcome row's licence (bought history is personal)


def outcome_hash(edge: Edge) -> str:
    """A fingerprint of the edge's ``[outcome]``: what a hit means."""
    text = json.dumps(identity_dict(asdict(edge.outcome)), sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _finite(value: Any) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if pd.notna(number) and abs(number) != float("inf") else None


def _finite_text(value: Any) -> str | None:
    return None if pd.isna(value) else str(value)


def _skipped(instrument: str, why: str) -> Settled:
    return Settled(instrument, SKIPPED, why, None, False)


def settle_group(
    reader: StoreReader,
    edge: Edge,
    trades: pd.DataFrame,
    session: date,
    now: datetime,
    option_costs: OptionCosts | None = None,
) -> list[Settled]:
    """The trades of one (edge, buy session, horizon) group (open rows of the book) that
    ``now`` settles; a trade still waiting is not returned. ``option_costs``: the commission an
    option P&L pays, as the backtest does (the verdict's ``[option_costs]``)."""
    first = trades.iloc[0]
    buy, horizon = first["buy_session"], int(first["horizon_sessions"])
    names = [str(i) for i in trades["instrument_id"]]
    changed = trades["outcome_hash"] != outcome_hash(edge)
    out = [
        _skipped(i, "the edge's outcome changed after the signal")
        for i in trades.loc[changed, "instrument_id"]
    ]
    names = [i for i in names if i not in {s.instrument_id for s in out}]
    if not names:
        return out
    if edge.outcome.kind == PORTFOLIO_KIND:  # a book is valued whole, never name by name
        return out + [_skipped(i, "a portfolio book is not settled name by name") for i in names]
    try:
        if edge.outcome.kind == CHAIN_KIND:  # an option P&L reads the chain grain (EB H13)
            stored = read_chain(reader, horizon, [buy], as_of=now)
        else:
            stored = read_outcomes(reader, horizon, [buy], BENCHMARK, as_of=now)
    except MissingDataError:
        stored = pd.DataFrame()
    if stored.empty:
        late = session >= advance(first["sell_session"], GRACE_SESSIONS)
        return out + (
            [_skipped(i, "no outcome stored for its window") for i in names] if late else []
        )
    mine = stored[stored["instrument_id"].isin(names)]
    if needs_residual(edge):  # a factor-neutral edge settles on the residual rows (EB H11)
        mine = attach_residuals(mine, read_residuals(reader, [buy], now), horizon)
        waiting = set(mine.loc[mine["residual_reason"] == NO_RESIDUAL_ROW, "instrument_id"])
        late = session >= advance(first["sell_session"], GRACE_SESSIONS)
        out += [_skipped(i, "no residual return stored for its window") for i in waiting if late]
        names = [i for i in names if i not in waiting]  # not yet stored: stays open until late
        mine = mine[~mine["instrument_id"].isin(waiting)]
        if not names:
            return out
    try:
        implied = (
            implied_at(reader, iv_field_of(edge), names, first["signal_session"])
            if needs_implied_vol(edge)
            else None
        )
    except MissingDataError:
        return out + [_skipped(i, "no implied vol stored at the signal session") for i in names]
    scored = (
        apply_outcome(edge, mine, option_costs=option_costs, implied=implied) if len(mine) else None
    )
    result = None if scored is None else scored.set_index("instrument_id")
    contract = (  # the trade contract's columns of each scored name (ADR 0088, 2.5a); paper is long
        None
        if scored is None
        else trade_frame(
            edge,
            mine,
            scored,
            entry=buy,
            bars_exit=first["sell_session"],
            side="long",
            option_costs=option_costs,
        ).set_index("instrument_id")
    )
    for name in names:
        if result is None or name not in result.index:
            out.append(_skipped(name, "no entry bar at the buy session"))
            continue
        row = result.loc[name]
        if row["excluded"]:
            out.append(_skipped(name, REASONS.get(str(row["excluded"]), str(row["excluded"]))))
            continue
        assert contract is not None
        trade = contract.loc[name]
        out.append(
            Settled(
                name,
                WON if row["hit"] else LOST,
                "",
                float(str(row["value"])) if is_return(edge) else None,
                bool(row["delisted"]),
                _finite(trade["underlying_return"]),
                _finite_text(trade["exit_kind"]),
                _finite(trade["return_on_capital"]),
                _finite_text(trade["price_source"]),
                _finite_text(trade["outcome_licence"]),
            )
        )
    return out
