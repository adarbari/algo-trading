"""The example position of a share pick at the served session S (ADR 0083 decision 3, ADR 0088
design 2.8, decision 22): ``ExamplePosition`` and ``load_example_positions``.

What the setup's rule would open from S's stored prices, never a size: the *reference close*
(S's ``rollup.price_stats@v2.close``, labelled as the reference: the entry is the close
``start_offset_sessions`` later), the *stop price* from the historical exit rule
(``exit_rule.exit_rule_at``: the winners' percentile, a declared stop, or the labelled ATR
fallback) and the *exit session*, the hold counted in exchange sessions from the entry.
One shape per pick side:

- ``long_shares``: the stop below the reference close;
- ``short_shares``: borrow assumed, the stop UNKNOWN (the exit rule is published for long picks
  only in P1);
- ``book``: a book's name, no weight or size (decision 22), no stop: it exits at its next
  rebalance (the entry after the schedule's next decision session).

A setup with an entry condition (E13a) enters when its condition holds, so its entry and exit are
UNKNOWN here, never S's.

A part that cannot be computed (no close, no exit rule, no basis) is an ``Unknown`` with its
reason, never filled. One read of the closes for every pick and the exit rule once per setup (asked
for the first long pick, so a fallback stop carries its multiple); when it falls back to the ATR
stop, one read of every long pick's ATR. Measured on the store for 15 picks: about 0.04 s beyond
the exit rule's own read, so no table (the 0.2 s bar). The option shape is a later slice (E9 2c).

``load_setup_examples`` is what a page asks (``Edge.examplePositions``): the setup's own inputs
from its document (the entry delay, an entry condition, a book outcome) and each name's side from
what the setup stored for the session (``pick_edges.load_edge_night``; a name it did not pick, or a
night not stored, reads ``long``)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.positions.exit_rule import ExitRuleSettings
from algotrade.config.site.settings import site_document
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import last_session_of_month, next_session
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation import pick_edges
from algotrade.services.read.evaluation.edges import Edge, parsed_edges
from algotrade.services.read.evaluation.positions.exit_rule import (
    ATR,
    ExitRule,
    Stop,
    StopKind,
    exit_rule_at,
)
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.values import Unknown, UnknownCode

CLOSE = "rollup.price_stats@v2.close"  # the reference close's catalogue field (usd per share)
LONG, SHORT = "long", "short"
EVERY_SESSION, MONTH_END = "every_session", "month_end"  # a book's schedules
ATR_GAPS = (UnknownCode.NO_PARTITION, UnknownCode.NO_ROW, UnknownCode.NULL)  # no ATR stored


class Shape(StrEnum):
    LONG_SHARES = "long_shares"
    SHORT_SHARES = "short_shares"
    BOOK = "book"


@dataclass(frozen=True)
class PickInput:
    """One pick of a setup at S: its id, side and whether it is a name of a book."""

    instrument_id: str
    side: str = LONG
    book: bool = False


@dataclass(frozen=True)
class ExamplePosition:
    """The example position of one pick. ``reference_close`` (S's close), ``stop_price`` with the
    ``stop`` it came from, ``entry_session`` and ``exit_session``: each None only with its
    unknown (``close_unknown``, ``stop_unknown``, ``exit_unknown``; a missing entry makes the
    exit unknown too). ``borrow_assumed``: a short pick."""

    edge_id: str
    instrument_id: str
    shape: Shape
    reference_close: float | None
    stop_price: float | None
    stop: Stop | None
    entry_session: date | None
    exit_session: date | None
    borrow_assumed: bool = False
    close_unknown: Unknown | None = None
    stop_unknown: Unknown | None = None
    exit_unknown: Unknown | None = None


def advance(day: date, sessions: int) -> date:
    """The exchange session ``sessions`` after ``day`` (``day`` itself for 0)."""
    for _ in range(sessions):
        day = next_session(day)
    return day


def next_rebalance(schedule: str, day: date) -> date | None:
    """The schedule's next decision session after ``day`` (a book's rebalance; None: a schedule
    that is not a book's, ``every_session`` or ``month_end``)."""
    if schedule == EVERY_SESSION:
        return next_session(day)
    if schedule == MONTH_END:
        end = last_session_of_month(day.year, day.month)
        if end > day:
            return end
        after = date(day.year + day.month // 12, day.month % 12 + 1, 1)
        return last_session_of_month(after.year, after.month)
    return None


def stop_price(close: float, stop: Stop) -> float | None:
    """A long pick's stop price below ``close``: ``close`` x (1 - fraction) for a history or
    declared stop, ``close`` - multiple x ATR for the fallback (None: the stop has neither)."""
    if stop.kind is StopKind.FALLBACK:
        if stop.atr is None or stop.multiple is None:
            return None
        return close - stop.multiple * stop.atr
    return None if stop.fraction is None else close * (1.0 - stop.fraction)


def _not_applicable(edge: Edge, why: str) -> Unknown:
    return Unknown(UnknownCode.NOT_APPLICABLE, run_cause(edge.id, why))


def _shape(pick: PickInput) -> Shape:
    if pick.book:
        return Shape.BOOK
    return Shape.SHORT_SHARES if pick.side == SHORT else Shape.LONG_SHARES


def _stop(
    edge: Edge, shape: Shape, close: float | None, rule: ExitRule
) -> tuple[float | None, Stop | None, Unknown | None]:
    """``(stop price, stop, unknown)`` of one pick from the setup's exit rule."""
    if shape is Shape.SHORT_SHARES:
        return None, None, _not_applicable(edge, "a short pick has no published stop yet")
    if shape is Shape.BOOK:
        return None, None, _not_applicable(edge, "a book exits at its next rebalance, no stop")
    if rule.stop is None:
        return None, None, rule.unknown
    if close is None:
        return None, rule.stop, _not_applicable(edge, "no reference close to place the stop")
    return stop_price(close, rule.stop), rule.stop, None


def _falls_back(rule: ExitRule) -> bool:
    """Whether ``rule`` is the ATR fallback: its stop, or no stop because the name's ATR is not
    stored (a feature gap: ``ATR_GAPS``). Any other unknown (a missing, pruned or hidden ledger, a
    licence, no basis) is not a fallback: the stop stays UNKNOWN (fail closed)."""
    if rule.stop is not None:
        return rule.stop.kind is StopKind.FALLBACK
    return (
        rule.hold_sessions is not None
        and rule.unknown is not None
        and (rule.unknown.code in ATR_GAPS)
    )


def _fallbacks(
    ctx: ReadContext, edge: Edge, rule: ExitRule, longs: list[str]
) -> dict[str, ExitRule]:
    """Each long pick's own ATR(14) stop when ``rule`` (asked for the first long pick) falls back
    to it: every pick's ATR in one read, the multiple the site's (empty: no fallback)."""
    if not longs or not _falls_back(rule):
        return {}
    multiple = rule.stop.multiple if rule.stop is not None else fallback_multiple(ctx)
    atrs = load_feature_values(ctx, longs, [ATR])
    out = {}
    for iid in longs:
        cell = atrs[iid][0]
        stop = (
            None
            if cell.value is None
            else Stop(StopKind.FALLBACK, atr=float(cell.value), multiple=multiple,
                      winners=rule.winners)
        )  # fmt: skip
        out[iid] = ExitRule(
            edge.id, stop, rule.hold_sessions, None if stop else cell.unknown, rule.winners,
            rule.in_sample_only,
        )  # fmt: skip
    return out


def _exit(
    edge: Edge, shape: Shape, entry: date | None, rule: ExitRule, rebalance: date | None,
    offset: int,
) -> tuple[date | None, Unknown | None]:  # fmt: skip
    """``(exit session, unknown)``: the hold after the entry, a book's next rebalance entry."""
    if entry is None:
        return None, _not_applicable(edge, "the setup enters when its entry condition holds")
    if shape is Shape.BOOK:
        if rebalance is None:
            return None, _not_applicable(edge, f"no rebalance session for {edge.schedule}")
        return advance(rebalance, offset), None
    if rule.hold_sessions is None:
        return None, rule.unknown
    return advance(entry, rule.hold_sessions), None


def fallback_multiple(ctx: ReadContext) -> float:
    """The site's ATR multiple of the fallback stop (``verdict.toml [exit_rule]``)."""
    found = ExitRuleSettings.from_document(site_document(ctx.configs.load, "verdict"))
    if found is None:
        raise ConfigurationError("verdict.toml has no [exit_rule] section")
    return found.atr_multiple


def load_example_positions(
    ctx: ReadContext,
    edge: Edge,
    picks: Sequence[PickInput],
    start_offset_sessions: int = 1,
    declared: Stop | None = None,
    entry_condition: bool = False,
) -> tuple[ExamplePosition, ...]:
    """The example position of each of ``picks`` (``edge``'s at ``ctx.session``), in order;
    ``start_offset_sessions``: the setup's entry delay (the entry is that many closes after S);
    ``declared``: the setup's own stop, published as it is; ``entry_condition``: the setup enters
    when a condition holds (its entry and exit are then UNKNOWN)."""
    if not picks:
        return ()
    ids = [p.instrument_id for p in picks]
    closes = load_feature_values(ctx, ids, [CLOSE])
    day = ctx.session.date
    entry = None if entry_condition else advance(day, start_offset_sessions)
    longs = [p.instrument_id for p in picks if _shape(p) is Shape.LONG_SHARES]
    shared = exit_rule_at(ctx, edge, longs[0] if longs else None, declared, bounded=True)
    own = _fallbacks(ctx, edge, shared, longs)
    rebalance = next_rebalance(edge.schedule, day)
    out = []
    for pick in picks:
        cell = closes[pick.instrument_id][0]
        close = None if cell.value is None else float(cell.value)
        shape = _shape(pick)
        rule = own.get(pick.instrument_id, shared)
        price, stop, stop_unknown = _stop(edge, shape, close, rule)
        exit_on, exit_unknown = _exit(edge, shape, entry, rule, rebalance, start_offset_sessions)
        out.append(
            ExamplePosition(
                edge.id, pick.instrument_id, shape, close, price, stop, entry, exit_on,
                shape is Shape.SHORT_SHARES, cell.unknown if close is None else None,
                stop_unknown, exit_unknown,
            )
        )  # fmt: skip
    return tuple(out)


def load_setup_examples(
    ctx: ReadContext | None, edge: Edge, instrument_ids: Sequence[str]
) -> tuple[ExamplePosition, ...] | None:
    """The example position of each of ``instrument_ids`` under ``edge`` at the served session,
    with the setup's own inputs (None: no session is served; empty: the document is not
    readable)."""
    if ctx is None:
        return None
    doc = next((e for e in parsed_edges(ctx, ctx.user.user_id) if e.id == edge.id), None)
    if doc is None:
        return ()
    outcome = doc.outcome
    night = pick_edges.load_edge_night(ctx, edge.id)
    sides = {} if night is None else night.sides
    book = outcome.kind == PORTFOLIO_KIND
    picks = [PickInput(i, sides.get(i, LONG), book) for i in instrument_ids]
    return load_example_positions(
        ctx, edge, picks, outcome.start_offset_sessions, entry_condition=outcome.entry is not None
    )
