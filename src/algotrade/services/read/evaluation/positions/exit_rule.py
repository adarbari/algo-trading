"""The historical exit rule a share setup publishes for a pick (ADR 0083 decision 3): ``ExitRule``
and ``load_exit_rule``.

The *stop* is the drawdown that ``stop_percentile`` (80%) of the setup's winning trades never
exceeded: the percentile of ``edge_trades.max_drawdown`` (a fraction of the entry reference, the
window's dip) over the ``hit`` long trades of the verdict's basis in the canonical run, read only
through ``runs.load_run_trades`` (which keeps ``oos_hidden`` and tells PRUNED from NOT_STORED).
With fewer than ``min_winners`` such trades the stop is the fallback, ``atr_multiple`` x
``momentum.atr_14`` of the name at the session. The *hold* is the verdict's stored
``basis_horizon``. A setup that declares its own stop publishes it (``declared``: the hook the
declared share exits of E3c fill); the percentile applies only without one.

Point in time at the served session S: the canonical run must end by S (``range_to <= S``) and
only trades that exited by S count. Nothing is filled: a missing input is an ``Unknown`` with its
reason, never an older value. The rule is a reading of the evaluation's own winners and never feeds
back into it (so it is not a judge input and not in the verdict fingerprint).

An option setup (an ``option_pnl`` outcome, ADR 0088 decision 19, design 2.4a) publishes its own
declared ``[outcome.exit]``, the rule its backtest used: a declared ``stop_loss`` as it is (a
multiple of the credit), with ``take_profit``, ``exit_dte`` and the fields of the ``when``
condition beside it. Only without a declared stop is the stop the percentile of the contract's
``max_adverse`` (the worst mark loss over the collateral) over the basis's winners, under the
same point-in-time bounds; below ``min_winners`` it is UNKNOWN (no ATR fallback: an ATR of the
underlying is no loss on an option position). Its hold is the earlier of the cap (the basis
horizon) and the selected expiry, when the caller gives one. An exit chosen by case is published
only as the caller resolved it at the session (``resolved``), else UNKNOWN."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

import numpy as np

from algotrade.config.edges.document import Outcome
from algotrade.config.edges.positions.cases import EXIT_CASE_NAMES
from algotrade.config.edges.positions.exit_rule import ExitRuleSettings
from algotrade.config.edges.positions.spec import OPTION_KIND, ExitSettings, PositionSpec
from algotrade.config.site.settings import site_document
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session, sessions_to
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.edges import Edge, parsed_edges
from algotrade.services.read.evaluation.verdict import (
    EdgeSummary,
    load_edge_summary,
    load_stored_summary,
)
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

ATR = "momentum.atr_14"  # the fallback's catalogue field (usd per share)


class StopKind(StrEnum):
    HISTORY = "HISTORY"  # the percentile of the basis's winners' adverse moves
    FALLBACK = "FALLBACK"  # atr_multiple x ATR(14): not from this setup's history
    DECLARED = "DECLARED"  # the setup's own declared stop, published as it is


class StopBasis(StrEnum):
    ENTRY = "ENTRY"  # a share setup: a fall below the entry reference close
    CREDIT = "CREDIT"  # an option setup's declared stop: a loss of this multiple of the credit
    COLLATERAL = "COLLATERAL"  # an option setup's history: a mark loss of this share of collateral


@dataclass(frozen=True)
class Stop:
    """A stop. ``fraction`` of the ``basis``: how far below the entry reference close (ENTRY), a
    multiple of the credit received (CREDIT) or a share of the collateral (COLLATERAL); ``atr``
    and ``multiple``: the ATR(14) in usd per share and its multiple (FALLBACK, the distance is
    their product). ``winners``: the winning trades a HISTORY stop rests on; ``beyond``: the
    share of them that went past it (1 - the percentile)."""

    kind: StopKind
    fraction: float | None = None
    atr: float | None = None
    multiple: float | None = None
    winners: int | None = None
    beyond: float | None = None
    basis: StopBasis = StopBasis.ENTRY


@dataclass(frozen=True)
class ExitRule:
    """A setup's exit rule at the served session: the ``stop`` and the ``hold`` in sessions (the
    verdict's basis horizon), each None only with the ``unknown`` that says why. ``winners``: the
    basis's winning long trades read (0 when none), whichever stop was published."""

    edge_id: str
    stop: Stop | None
    hold_sessions: int | None
    unknown: Unknown | None = None
    winners: int = 0
    in_sample_only: bool = False  # the canonical run hides its out-of-sample trades: not read
    # an option setup's other declared exits, published as declared (None: not declared)
    take_profit: float | None = None  # close when this share of the credit is captured
    exit_dte: int | None = None  # close at this many calendar days to expiry
    condition_fields: tuple[str, ...] = ()  # the catalogue fields its exit condition reads
    expiry: date | None = None  # the selected expiry the hold was cut to (None: not given)


def _unknown(edge: Edge, code: UnknownCode, why: str) -> Unknown:
    return Unknown(code, run_cause(edge.id, why))


def history_stop(dips: list[float], share: float, basis: StopBasis = StopBasis.ENTRY) -> Stop:
    """The stop of ``dips`` (the winners' adverse moves): the smallest observed dip that ``share``
    of them did not exceed (numpy's ``inverted_cdf``: an observed value, never an interpolated
    one), with the real share that went past it (ties make it differ from ``1 - share``)."""
    values = np.asarray(dips, dtype=float)
    stop = float(np.quantile(values, share, method="inverted_cdf"))
    beyond = float((values > stop).mean())
    return Stop(StopKind.HISTORY, fraction=stop, winners=len(dips), beyond=beyond, basis=basis)


def _settings(ctx: ReadContext) -> ExitRuleSettings:
    found = ExitRuleSettings.from_document(site_document(ctx.configs.load, "verdict"))
    if found is None:
        raise ConfigurationError("verdict.toml has no [exit_rule] section")
    return found


def _fallback(
    ctx: ReadContext, edge: Edge, instrument_id: str | None, multiple: float, winners: int
) -> tuple[Stop | None, Unknown | None]:
    if instrument_id is None:
        why = f"only {winners} winning trades and no name to take the fallback from"
        return None, _unknown(edge, UnknownCode.NOT_APPLICABLE, why)
    cell = load_feature_values(ctx, [instrument_id], [ATR])[instrument_id][0]
    if cell.value is None:
        return None, cell.unknown
    return Stop(StopKind.FALLBACK, atr=float(cell.value), multiple=multiple, winners=winners), None


def _ledger(
    ctx: ReadContext, edge: Edge, run: runs.EdgeRun, summary: EdgeSummary
) -> tuple[list[runs.TradeRow], Unknown | None]:
    """The basis's trades in the canonical run that exited by the session, or why they cannot be
    read (no ledger, or one under a licence the viewer does not hold)."""
    ledger = runs.load_run_trades(
        ctx, run, variant=summary.basis_screener or "", horizon=summary.basis_horizon or 0
    )
    unknown = ledger.unknown
    if unknown is None and ledger.licence not in (None, "", runs.OPEN, *ctx.licences):
        why = f"the winners' outcomes are under the {ledger.licence} data licence"
        unknown = _unknown(edge, UnknownCode.LICENCE, why)
    day = ctx.session.date
    return [t for t in ledger.rows if t.exit_session is not None and t.exit_session <= day], unknown


def _from_history(
    ctx: ReadContext, edge: Edge, run: runs.EdgeRun, summary: EdgeSummary, instrument_id: str | None
) -> ExitRule:
    """The percentile stop of the basis's winners, else the ATR fallback (the rules of the module
    docstring: a ledger the viewer's licences do not cover, or that is long-only, is UNKNOWN)."""
    horizon = summary.basis_horizon or 0
    known, unknown = _ledger(ctx, edge, run, summary)
    if unknown is None and any(t.side != "long" for t in known):
        why = "the exit rule is published for long picks only"
        unknown = _unknown(edge, UnknownCode.NOT_APPLICABLE, why)
    if unknown is not None:
        return ExitRule(edge.id, None, horizon, unknown, in_sample_only=run.oos_hidden)
    dips = [t.max_drawdown for t in known if t.hit is True and t.max_drawdown is not None]
    t = _settings(ctx)
    if len(dips) >= t.min_winners:
        stop = history_stop(dips, t.stop_percentile)
        return ExitRule(edge.id, stop, horizon, winners=len(dips), in_sample_only=run.oos_hidden)
    fallback, unknown = _fallback(ctx, edge, instrument_id, t.atr_multiple, len(dips))
    return ExitRule(edge.id, fallback, horizon, unknown, len(dips), run.oos_hidden)


def option_outcome(ctx: ReadContext, edge: Edge) -> Outcome | None:
    """``edge``'s main outcome when it is an option setup (an ``option_pnl`` outcome with a
    position), else None. The ledger and the verdict basis are the main edge variant's
    (``edge_variant`` null), so its declared exits are the main outcome's."""
    doc = next((e for e in parsed_edges(ctx, ctx.user.user_id) if e.id == edge.id), None)
    if doc is None or doc.outcome.kind != OPTION_KIND or doc.outcome.position is None:
        return None
    return doc.outcome


def _declared_exits(
    edge: Edge, spec: PositionSpec, resolved: Mapping[str, float] | None
) -> tuple[ExitSettings, Unknown | None]:
    """The declared exits with each case-valued one replaced by its value ``resolved`` at the
    session (0: off, as a grid spells it); one not resolved makes the rule UNKNOWN."""
    exits = spec.exit or ExitSettings()
    chosen = {c.name for c in spec.cases if c.name in EXIT_CASE_NAMES}
    missing = sorted(chosen - set(resolved or {}))
    if missing:
        why = f"{missing[0]} is chosen by case for each pick: not resolved for this one"
        return exits, _unknown(edge, UnknownCode.NOT_APPLICABLE, why)
    got = {k: v for k, v in (resolved or {}).items() if k in chosen}
    take_profit = (float(got["take_profit"]) or None) if "take_profit" in got else exits.take_profit
    stop_loss = (float(got["stop_loss"]) or None) if "stop_loss" in got else exits.stop_loss
    exit_dte = (int(got["exit_dte"]) or None) if "exit_dte" in got else exits.exit_dte
    return ExitSettings(take_profit, stop_loss, exit_dte, exits.when), None


def _option_hold(ctx: ReadContext, offset: int, cap: int, expiry: date | None) -> int:
    """The earlier of the cap and the selected expiry, in sessions after the entry session (the
    ``offset``-th session after the served one)."""
    if expiry is None:
        return cap
    entry = ctx.session.date
    for _ in range(offset):
        entry = next_session(entry)
    return min(cap, sessions_to(entry, expiry))


def _from_option(
    ctx: ReadContext,
    edge: Edge,
    run: runs.EdgeRun,
    summary: EdgeSummary,
    outcome: Outcome,
    expiry: date | None,
    resolved: Mapping[str, float] | None,
) -> ExitRule:
    """An option setup's own declared exits; only without a declared stop the percentile of its
    winners' ``max_adverse``, UNKNOWN below ``min_winners`` (the module docstring)."""
    assert outcome.position is not None  # option_outcome returns only an outcome with one
    hold = _option_hold(ctx, outcome.start_offset_sessions, summary.basis_horizon or 0, expiry)
    exits, unknown = _declared_exits(edge, outcome.position, resolved)
    fields = tuple(sorted({r.field for r in exits.when.rules()})) if exits.when else ()
    rule = ExitRule(
        edge.id, None, hold, unknown, in_sample_only=run.oos_hidden, take_profit=exits.take_profit,
        exit_dte=exits.exit_dte, condition_fields=fields, expiry=expiry,
    )  # fmt: skip
    if unknown is not None:
        return replace(rule, take_profit=None, exit_dte=None)
    if exits.stop_loss is not None:
        own = Stop(StopKind.DECLARED, fraction=exits.stop_loss, basis=StopBasis.CREDIT)
        return replace(rule, stop=own, in_sample_only=False)
    known, unknown = _ledger(ctx, edge, run, summary)
    winners = [t.max_adverse for t in known if t.hit is True]
    hidden = next((c.unknown for c in winners if c.unknown is not None), None)
    losses = [float(c.value) for c in winners if c.value is not None]
    count, least = len(losses), _settings(ctx).min_winners
    if unknown is None and hidden is not None:
        unknown = hidden  # one winner's loss the viewer may not read: never a partial percentile
    elif unknown is None and winners and not losses:
        why = f"run {run.run_id} is older than the trades' max_adverse: re-run the backtest"
        unknown = _unknown(edge, UnknownCode.NOT_STORED, why)
    elif unknown is None and count < least:
        why = f"only {count} winning trades, fewer than {least}: no stop from so few"
        unknown = _unknown(edge, UnknownCode.NOT_APPLICABLE, why)
    if unknown is not None:
        return replace(rule, unknown=unknown, winners=count)
    stop = history_stop(losses, _settings(ctx).stop_percentile, StopBasis.COLLATERAL)
    return replace(rule, stop=stop, winners=count)


def exit_rule_at(
    ctx: ReadContext,
    edge: Edge,
    instrument_id: str | None = None,
    declared: Stop | None = None,
    bounded: bool = False,
    expiry: date | None = None,
    resolved: Mapping[str, float] | None = None,
) -> ExitRule:
    """The exit rule of ``edge`` at ``ctx.session``; ``instrument_id``: the pick, for the ATR
    fallback; ``declared``: a share setup's own stop, published as it is when given (an option
    setup's comes from its document). Nothing, the hold included, is read from a canonical run
    that ends after the session. ``bounded``: the canonical run is the latest committed on or
    before the session (as Ideas reads the verdict, ``runs.load_canonical_run``), so the rule and
    the verdict it sits beside name one run. ``expiry`` and ``resolved``: an option pick's
    selected expiry and its case-valued exits resolved at the session (the example position)."""
    canonical = (
        runs.load_canonical_run(ctx, edge, True) if bounded else runs.load_canonical_run(ctx, edge)
    )
    run = canonical.run
    if run is None:
        return ExitRule(edge.id, None, None, canonical.not_run)
    if run.range_to > ctx.session.date:  # its verdict, basis and ledger are not known then
        why = f"the canonical run ends {run.range_to}, after the session {ctx.session.date}"
        return ExitRule(edge.id, None, None, _unknown(edge, UnknownCode.NOT_RUN, why))
    summary = (
        load_stored_summary(ctx, edge, bounded=True) if bounded else None
    ) or load_edge_summary(ctx, edge)
    if summary.basis_screener is None or summary.basis_horizon is None:
        why = f"{edge.id} has no verdict basis ({summary.result})"
        return ExitRule(edge.id, None, None, _unknown(edge, UnknownCode.NOT_RUN, why))
    option = option_outcome(ctx, edge)
    if option is not None:
        return _from_option(ctx, edge, run, summary, option, expiry, resolved)
    if declared is not None:
        return ExitRule(edge.id, declared, summary.basis_horizon)
    return _from_history(ctx, edge, run, summary, instrument_id)


def load_exit_rule(
    ctx: ReadContext | None,
    edge: Edge,
    instrument_id: str | None = None,
    declared: Stop | None = None,
) -> ExitRule | None:
    """``exit_rule_at`` for the served session (None: no session is served)."""
    return None if ctx is None else exit_rule_at(ctx, edge, instrument_id, declared)
