"""One idea's page (ADR 0083 amendment 2026-11-01 (b); plan V4): ``IdeaDetail`` for a ticker that
a qualifying setup picked at the served session, filled from the setup and never written per
pick, one section each:

* ``why``: the setup's thesis and mechanism and the criteria this name met in its basis screener's
  run (the stored result row of that pick);
* ``exit_rule``: the setup's historical exit rule for the pick (``positions.exit_rule``: the
  stop and the hold, or why not) and ``exit_prices``: the stop and target as prices from the
  reference close at S;
* ``evidence``: the stored verdict headline the setup was listed on (every figure is backtested,
  hypothetical, a statement the page labels);
* ``risks``: why the setup's edge should persist (what would break it), the ticker's own earnings
  inside the hold window and the pick's watch-outs;
* ``learn``: the setup's id, the key of its Guide entry.

A section whose input is missing carries an ``unknown`` with its reason, never an empty body. The
setup shown is the one asked for among those that picked the ticker, else the best by the one
ranking rule (``inverse.load_setups_of_instrument`` lists them strongest first). A ticker no
qualifying setup picked at the session has no idea page (None): nothing is read for an older
night. A pick of a Premium setup adds ``option`` (``option_detail``: the example position, the
declared exits as marks, the most you can lose, the position's figures and calendar flags);
``tab`` says which kind it is."""

from dataclasses import dataclass
from datetime import date

from algotrade.core.time.calendar import next_session
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.positions.example import CLOSE, stop_price
from algotrade.services.read.evaluation.positions.exit_rule import (
    ExitRule,
    StopBasis,
    exit_rule_at,
)
from algotrade.services.read.events.ahead import AheadEvent
from algotrade.services.read.events.instrument_events import load_instrument_events
from algotrade.services.read.ideas import of_setup
from algotrade.services.read.ideas.inverse import InstrumentSetup, load_setups_of_instrument
from algotrade.services.read.ideas.option_detail import IdeaOption, load_idea_option
from algotrade.services.read.ideas.setups import PREMIUM, QualifyingSetup, load_session_setups
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.instruments.identity import Instrument, load_instruments, resolve_id
from algotrade.services.read.screens.ideas import (
    IdeaMetric,
    display_metrics,
    earnings_first,
    watch_out,
)
from algotrade.services.read.screens.results import CriterionResult, ScreenResult, load_results
from algotrade.services.read.values import Unknown, UnknownCode

OWN_EARNINGS = ("own_earnings", "reference_earnings")


@dataclass(frozen=True)
class IdeaWhy:
    """Why the name is here: the setup's ``thesis`` and ``mechanism``, the ``decision`` of its
    ``basis_screener`` (the screener the verdict rests on) for the name and the ``criteria`` it
    met (``unknown``: the pick's row could not be read)."""

    thesis: str
    mechanism: str
    basis_screener: str
    decision: str | None
    criteria: tuple[CriterionResult, ...]
    unknown: Unknown | None = None


@dataclass(frozen=True)
class IdeaExitPrices:
    """The exit rule in prices for the pick, from the reference close at the session: ``stop`` (a
    fall of the entry close: close x (1 - fraction), or close - multiple x ATR for the fallback)
    and ``target`` (close x (1 + take profit)). Each is None when the rule publishes none or its
    meaning is not a move of the entry price (an option's credit); ``unknown``: the close could
    not be read (the rule's own gaps are on ``IdeaDetail.exit_rule``)."""

    stop: float | None = None
    target: float | None = None
    unknown: Unknown | None = None


@dataclass(frozen=True)
class IdeaEvidence:
    """The stored verdict headline of the setup (backtested, hypothetical): its ``level``, the
    one line ``result``, ``basis`` in words and the figures it rests on (None: not measured)."""

    level: str
    result: str
    basis: str | None
    basis_horizon: int | None
    lift_pts: float | None
    lift: float | None
    trades: int | None
    oos_trades: int | None


@dataclass(frozen=True)
class IdeaRisks:
    """What could go wrong: ``persistence`` (why the setup's edge should last, so what would end
    it), the ticker's own ``events`` before the hold ends on ``hold_ends`` (None: the hold is not
    known, so no events are listed, ``unknown`` says why) and the pick's ``watch_out`` ids."""

    persistence: str
    hold_ends: date | None
    events: tuple[AheadEvent, ...]
    watch_out: tuple[str, ...]
    unknown: Unknown | None = None


@dataclass(frozen=True)
class IdeaDetail:
    """The page of one idea at ``session``: the ``setup`` it is shown under and its ``place``
    there, every ``setups`` that picked it (strongest first), then the sections."""

    session: date
    instrument_id: str
    instrument: Instrument | None
    tab: str
    setup: InstrumentSetup
    setups: tuple[InstrumentSetup, ...]
    why: IdeaWhy
    exit_rule: ExitRule
    exit_prices: IdeaExitPrices
    evidence: IdeaEvidence
    risks: IdeaRisks
    learn: str
    metrics: tuple[IdeaMetric, ...] = ()
    option: IdeaOption | None = None


def _chosen(found: tuple[InstrumentSetup, ...], wanted: str | None) -> InstrumentSetup | None:
    if wanted is not None:
        return next((s for s in found if s.edge_id == wanted), None)
    return found[0] if found else None


def _result(ctx: ReadContext, pick: of_setup.SetupPickSet, iid: str) -> ScreenResult | None:
    if pick.run is None:
        return None
    return load_results(ctx, {pick.run.run_id: [iid]}, [pick.run]).get((pick.run.run_id, iid))


def _hold_end(day: date, sessions: int | None) -> date | None:
    if sessions is None:
        return None
    end = day
    for _ in range(sessions):
        end = next_session(end)
    return end


def _why(
    ctx: ReadContext,
    setup: QualifyingSetup,
    result: ScreenResult | None,
    pick: of_setup.SetupPickSet,
) -> IdeaWhy:
    edge = setup.edge
    if result is None:
        text = f"{setup.basis_screener} has no readable row for the pick at {ctx.session.date}"
        cause = run_cause(setup.basis_screener, text, ctx.session.date)
        unknown = Unknown(UnknownCode.NOT_STORED, cause)
        return IdeaWhy(
            edge.thesis, edge.mechanism, setup.basis_screener, None, (), pick.unknown or unknown
        )
    return IdeaWhy(
        edge.thesis, edge.mechanism, setup.basis_screener, result.decision, tuple(result.criteria)
    )


def _risks(
    ctx: ReadContext, setup: QualifyingSetup, iid: str, rule: ExitRule, flags: tuple[str, ...]
) -> IdeaRisks:
    ends = _hold_end(ctx.session.date, rule.hold_sessions)
    persistence = setup.edge.persistence
    if ends is None:
        return IdeaRisks(persistence, None, (), flags, rule.unknown)
    days = (ends - ctx.session.date).days + 1
    found = load_instrument_events(ctx, [iid], days=days).get(iid)
    if found is None:
        text = f"{iid} has no events read for {ctx.session.date}"
        unknown = Unknown(UnknownCode.NOT_STORED, run_cause(iid, text, ctx.session.date))
        return IdeaRisks(persistence, ends, (), flags, unknown)
    gap = next((g for g in found.gaps if g.part in OWN_EARNINGS and g.instrument_id == iid), None)
    events = tuple(e for e in found.ahead if e.kind in OWN_EARNINGS and e.date <= ends)
    return IdeaRisks(persistence, ends, events, flags, None if gap is None else gap.unknown)


def _exit_prices(ctx: ReadContext, iid: str, rule: ExitRule) -> IdeaExitPrices:
    """The stop and target of ``rule`` as prices of the name's close at the session; only a move
    of the entry price (``StopBasis.ENTRY``) has one."""
    stop = rule.stop if rule.stop is not None and rule.stop.basis is StopBasis.ENTRY else None
    rise = rule.take_profit if rule.take_profit_basis is StopBasis.ENTRY else None
    if stop is None and rise is None:
        return IdeaExitPrices()
    cell = load_feature_values(ctx, [iid], [CLOSE])[iid][0]
    if cell.value is None:
        return IdeaExitPrices(unknown=cell.unknown)
    close = float(cell.value)
    return IdeaExitPrices(
        None if stop is None else stop_price(close, stop),
        None if rise is None else close * (1.0 + rise),
    )


def load_idea_detail(ctx: ReadContext, key: str, setup_id: str | None = None) -> IdeaDetail | None:
    """The idea page of ``key`` (a ticker or an instrument id) under ``setup_id`` (default: the
    best setup that picked it); None when the name is unknown, no qualifying setup picked it at
    ``ctx.session`` or ``setup_id`` is not one that did."""
    iid = resolve_id(ctx, key)
    if iid is None:
        return None
    found = load_setups_of_instrument(ctx, iid)
    chosen = _chosen(found, setup_id)
    qualifying = {s.edge.id: s for s in load_session_setups(ctx).qualifying}
    if chosen is None or chosen.edge_id not in qualifying:
        return None
    setup = qualifying[chosen.edge_id]
    pick = of_setup.load_pick_set(ctx, setup)
    result = _result(ctx, pick, iid)
    rule = exit_rule_at(ctx, setup.edge, iid, bounded=True)
    early = earnings_first(ctx, [iid]) if result is not None else set()
    flags = () if result is None else watch_out(result, iid in early)
    s = setup.summary
    return IdeaDetail(
        session=ctx.session.date,
        instrument_id=iid,
        instrument=load_instruments(ctx, [iid]).get(iid),
        tab=setup.tab,
        setup=chosen,
        setups=found,
        why=_why(ctx, setup, result, pick),
        exit_rule=rule,
        exit_prices=_exit_prices(ctx, iid, rule),
        evidence=IdeaEvidence(
            s.verdict,
            s.result,
            s.basis,
            setup.basis_horizon,
            s.lift_pts,
            s.lift,
            s.trades,
            s.oos_trades,
        ),
        risks=_risks(ctx, setup, iid, rule, flags),
        learn=setup.edge.id,
        metrics=() if result is None else display_metrics(result),
        option=load_idea_option(ctx, setup.edge, iid, rule) if setup.tab == PREMIUM else None,
    )
