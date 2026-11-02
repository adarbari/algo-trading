"""The example position of an option pick at the served session S (ADR 0088 design 2.8, decision
19): ``OptionExample`` and ``load_option_examples``.

What the setup's template would open on the pick's chain at S, chosen by the harness's own rule
(``wing_search.select_legs`` over S's stored quotes alone, the expiry no earlier than the hold's
end, as ``engines.structures.trades.select_window`` chooses it): each leg's contract, strike,
expiry, quantity, bid, ask, mid, our delta, the feed's IV and theta, open interest and volume
(one row per contract, the spot the chain's closing spot, as the harness reads them); a share
leg's entry close;
the net credit and the collateral per share of one contract (``trades.collateral_of``); the
setup's exit rule (``exit_rule.exit_rule_at`` given the selected expiry: its declared stop, take
profit and DTE, else the percentile stop) as dollar marks on that credit and collateral; and the
exit session, the earlier of the expiry and the hold cap. The entry is the close
``start_offset_sessions`` after S (the hold and the expiry's floor are counted from it, as the
harness counts them); the legs are chosen from S's chain, the one the reader has. ``chain_asof``
is S. Deferred to O4 (not published, so never read as zero): the position's theta per day, the
quoted ITM probability, a one-sigma-day loss, and the report / ex-dividend flags.

Fail closed: a pick with no OK chain at S, no underlying price captured with it, or no legs by
the rule is UNKNOWN with its reason; a setup with case-valued parameters is UNKNOWN until a run
applies them (E13b), so a published example is never one the backtest did not take. Reads
``chains/*`` for S only, never the bought history (``data.option_history``)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.config.edges.document import Outcome
from algotrade.config.edges.positions.templates import SHARES
from algotrade.core.time.calendar import is_session, next_session, session_on_or_before
from algotrade.engines.structures.trades import collateral_of
from algotrade.features.rollups.options.wing_search import LegSelection, select_legs
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import Edge
from algotrade.services.read.evaluation.positions.exit_rule import ExitRule, StopBasis, exit_rule_at
from algotrade.services.read.instruments.chains import (
    load_chain_quotes,
    load_chain_spots,
    load_chains,
)
from algotrade.services.read.values import Unknown, UnknownCode

OK = "OK"  # a usable chain's status (``engines.structures.chain.Labels``)


@dataclass(frozen=True)
class OptionLeg:
    """One chosen contract: ``qty`` signed (negative: sold); prices per share; ``delta`` ours
    (r = q = 0, as the selector's), ``iv`` and ``theta`` the feed's (None: not stored)."""

    instrument_id: str
    right: str
    strike: float
    expiry: date
    qty: int
    bid: float | None
    ask: float | None
    mid: float
    delta: float | None
    iv: float | None
    theta: float | None
    open_interest: float | None
    volume: float | None


@dataclass(frozen=True)
class OptionExample:
    """The example position of one option pick. ``net_credit`` (positive: a credit) and
    ``collateral`` per share of one contract; ``stop_debit``: the price to close at the declared
    stop (credit x (1 + multiple)), ``stop_loss``: the loss at a history stop (its share of the
    collateral), ``take_profit_debit``: the price to close at the declared take profit,
    ``exit_dte_date``: the session of the declared DTE exit (the first on or after expiry less
    its days); each None when not declared or
    not computable (a rule part's own reason is ``rule.unknown``). ``unknown``: why there is no
    example at all (every other field empty)."""

    edge_id: str
    underlying_id: str
    chain_asof: date
    legs: tuple[OptionLeg, ...] = ()
    spot: float | None = None
    share_entry_close: float | None = None  # a share leg's entry close (the spot; None: no leg)
    entry_session: date | None = None
    net_credit: float | None = None
    collateral: float | None = None
    rule: ExitRule | None = None
    stop_debit: float | None = None
    stop_loss: float | None = None
    take_profit_debit: float | None = None
    exit_dte_date: date | None = None
    exit_session: date | None = None
    unknown: Unknown | None = None


def _finite(value: object) -> float | None:
    try:
        found = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return found if np.isfinite(found) else None


def _advance(day: date, sessions: int) -> date:
    for _ in range(sessions):
        day = next_session(day)
    return day


def _legs(quotes: pd.DataFrame, picked: LegSelection) -> tuple[OptionLeg, ...]:
    by_id = quotes.drop_duplicates("instrument_id").set_index("instrument_id")
    out = []
    for chosen in picked.legs:
        row = by_id.loc[chosen.instrument_id]
        out.append(
            OptionLeg(
                chosen.instrument_id, str(chosen.leg.right), chosen.strike, chosen.expiry,
                chosen.leg.qty, _finite(row.get("bid")), _finite(row.get("ask")), chosen.mid,
                _finite(chosen.delta), _finite(row.get("iv")), _finite(row.get("theta")),
                _finite(row.get("open_interest")), _finite(row.get("volume")),
            )
        )  # fmt: skip
    return tuple(out)


def _marks(example: OptionExample, rule: ExitRule) -> OptionExample:
    """The rule's exits as dollar marks on the example's credit and collateral."""
    credit, stop = example.net_credit, rule.stop
    stop_debit = stop_loss = None
    if stop is not None and stop.fraction is not None:
        if stop.basis is StopBasis.CREDIT and credit is not None:
            stop_debit = credit * (1.0 + stop.fraction)
        elif stop.basis is StopBasis.COLLATERAL and example.collateral is not None:
            stop_loss = stop.fraction * example.collateral
    take = None if rule.take_profit is None or credit is None else credit * (1 - rule.take_profit)
    expiry = min((leg.expiry for leg in example.legs), default=None)
    dte = (
        None
        if rule.exit_dte is None or expiry is None
        else _on_or_after(expiry - timedelta(rule.exit_dte))
    )
    entry = example.entry_session
    exit_on = None if entry is None else _exit_session(entry, rule, expiry)
    return replace(
        example, rule=rule, stop_debit=stop_debit, stop_loss=stop_loss, take_profit_debit=take,
        exit_dte_date=dte, exit_session=exit_on,
    )  # fmt: skip


def _on_or_after(day: date) -> date:
    """The first exchange session on or after ``day`` (a DTE exit acts at that close)."""
    return day if is_session(day) else next_session(day)


def _exit_session(entry: date, rule: ExitRule, expiry: date | None) -> date | None:
    """The earlier of the hold cap (the rule's hold, already cut to the expiry) and the expiry's
    session, counted from the entry close."""
    if rule.hold_sessions is None:
        return None
    held = _advance(entry, rule.hold_sessions)
    return held if expiry is None else min(held, session_on_or_before(expiry))


def _none(edge: Edge, underlying: str, day: date, code: UnknownCode, why: str) -> OptionExample:
    """No example for ``underlying``, with the reason."""
    return OptionExample(edge.id, underlying, day, unknown=Unknown(code, run_cause(edge.id, why)))


def _one(
    ctx: ReadContext, edge: Edge, outcome: Outcome, underlying: str, quotes: pd.DataFrame,
    status: str | None, spot: float | None, cap: int, rules: dict[date, ExitRule],
) -> OptionExample:  # fmt: skip
    """One pick's example; ``rules``: the exit rule by selected expiry, shared by the picks (the
    rule depends on the expiry alone)."""
    day = ctx.session.date
    spec = outcome.position
    assert spec is not None
    if status != OK or quotes.empty:
        return _none(edge, underlying, day, UnknownCode.NO_ROW, f"no usable chain at {day}")
    if spot is None:
        why = f"no underlying price captured with the chain at {day}"
        return _none(edge, underlying, day, UnknownCode.NO_ROW, why)
    entry = _advance(day, outcome.start_offset_sessions)
    picked = select_legs(
        quotes, spec.legs, spot, day, int(outcome.tenor_days or 0), spec.expiry_cycle,
        not_before=_advance(entry, cap),
    )  # fmt: skip
    if picked.reason is not None:
        why = f"no legs by the rule at {day}: {picked.reason}"
        return _none(edge, underlying, day, UnknownCode.NOT_APPLICABLE, why)
    net_mid = sum(c.leg.qty * c.mid for c in picked.legs)
    collateral = _finite(collateral_of(spec.collateral, spec.legs, picked, spot, net_mid))
    legs = _legs(quotes, picked)
    expiry = min(leg.expiry for leg in legs)
    if expiry not in rules:
        rules[expiry] = exit_rule_at(ctx, edge, bounded=True, expiry=expiry, resolved={})
    rule = rules[expiry]
    shares = any(leg.kind == SHARES for leg in spec.legs)
    filled = OptionExample(
        edge.id, underlying, day, legs, spot, spot if shares else None, entry, -net_mid,
        collateral,
    )  # fmt: skip
    return _marks(filled, rule)


def load_option_examples(
    ctx: ReadContext, edge: Edge, outcome: Outcome, underlyings: Sequence[str]
) -> tuple[OptionExample, ...]:
    """The example position of each of ``underlyings`` (``edge``'s option picks at
    ``ctx.session``, ``outcome`` its document's option outcome), in order: one read of the
    chains, the statuses and the underlying prices for them all."""
    if not underlyings:
        return ()
    day = ctx.session.date
    spec = outcome.position
    refused = (
        (UnknownCode.NOT_APPLICABLE, f"{edge.id} declares no option position")
        if spec is None or not spec.legs
        else (
            UnknownCode.NOT_APPLICABLE,
            f"{edge.id}'s case-valued parameters are not applied by any run yet (E13b)",
        )
        if spec.cases
        else None
    )
    cap = None if refused else exit_rule_at(ctx, edge, bounded=True).hold_sessions
    if refused is None and cap is None:
        refused = (UnknownCode.NOT_RUN, f"{edge.id} has no hold at {day} (no verdict basis)")
    if refused is not None or cap is None:
        code, why = refused or (UnknownCode.NOT_RUN, "no hold")
        return tuple(_none(edge, u, day, code, why) for u in underlyings)
    quotes = load_chain_quotes(ctx, underlyings)
    chains = load_chains(ctx, underlyings)
    spots = load_chain_spots(ctx, underlyings)
    out = []
    rules: dict[date, ExitRule] = {}
    for u in underlyings:
        chain = chains.get(u)
        mine = quotes[quotes["underlying_id"].astype(str) == u] if not quotes.empty else quotes
        spot = spots.get(u)
        status = None if chain is None else chain.status
        out.append(_one(ctx, edge, outcome, u, mine, status, spot, cap, rules))
    return tuple(out)
