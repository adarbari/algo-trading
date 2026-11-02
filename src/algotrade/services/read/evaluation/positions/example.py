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
- ``book``: a book's name with its weight (never shown as a size), no stop (a book exits at its
  next rebalance, the hold).

A part that cannot be computed (no close, no exit rule, no basis) is an ``Unknown`` with its
reason, never filled. One read of the closes for every pick and the exit rule once per setup; when
the setup falls back to the ATR stop, the rule once more for its multiple and one read of every
long pick's ATR. Measured on the store for 15 picks: about 0.04 s beyond the exit rule's own read,
so no table (the 0.2 s bar). The option shape is a later slice (E9 2c)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from algotrade.core.time.calendar import next_session
from algotrade.services.read.availability.cause import run_cause
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import Edge
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


class Shape(StrEnum):
    LONG_SHARES = "long_shares"
    SHORT_SHARES = "short_shares"
    BOOK = "book"


@dataclass(frozen=True)
class PickInput:
    """One pick of a setup at S: its id, side and, in a book, its weight (None: not a book)."""

    instrument_id: str
    side: str = LONG
    weight: float | None = None


@dataclass(frozen=True)
class ExamplePosition:
    """The example position of one pick. ``reference_close`` (S's close), ``stop_price`` with the
    ``stop`` it came from, ``entry_session`` and ``exit_session``: each None only with its
    unknown (``close_unknown``, ``stop_unknown``, ``exit_unknown``). ``weight``: a book's weight
    of the name, never a size; ``borrow_assumed``: a short pick."""

    edge_id: str
    instrument_id: str
    shape: Shape
    reference_close: float | None
    stop_price: float | None
    stop: Stop | None
    entry_session: date
    exit_session: date | None
    weight: float | None = None
    borrow_assumed: bool = False
    close_unknown: Unknown | None = None
    stop_unknown: Unknown | None = None
    exit_unknown: Unknown | None = None


def advance(day: date, sessions: int) -> date:
    """The exchange session ``sessions`` after ``day`` (``day`` itself for 0)."""
    for _ in range(sessions):
        day = next_session(day)
    return day


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
    if pick.weight is not None:
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


def _fallbacks(
    ctx: ReadContext, edge: Edge, shared: ExitRule, longs: list[str], declared: Stop | None
) -> dict[str, ExitRule]:
    """Each long pick's own exit rule when the setup's falls back to ATR(14): the multiple from
    one rule asked for the first pick, every pick's ATR in one read (empty: no fallback)."""
    if shared.stop is not None or shared.hold_sessions is None or not longs:
        return {}
    first = exit_rule_at(ctx, edge, longs[0], declared, bounded=True)
    if first.stop is None or first.stop.kind is not StopKind.FALLBACK:
        return {}
    multiple, hold = first.stop.multiple, first.hold_sessions
    atrs = load_feature_values(ctx, longs, [ATR])
    out = {}
    for iid in longs:
        cell = atrs[iid][0]
        stop = (
            None
            if cell.value is None
            else Stop(StopKind.FALLBACK, atr=float(cell.value), multiple=multiple,
                      winners=first.stop.winners)
        )  # fmt: skip
        out[iid] = ExitRule(edge.id, stop, hold, None if stop else cell.unknown, first.winners)
    return out


def load_example_positions(
    ctx: ReadContext,
    edge: Edge,
    picks: Sequence[PickInput],
    start_offset_sessions: int = 1,
    declared: Stop | None = None,
) -> tuple[ExamplePosition, ...]:
    """The example position of each of ``picks`` (``edge``'s at ``ctx.session``), in order;
    ``start_offset_sessions``: the setup's entry delay (the entry is that many closes after S);
    ``declared``: the setup's own stop, published as it is."""
    if not picks:
        return ()
    ids = [p.instrument_id for p in picks]
    closes = load_feature_values(ctx, ids, [CLOSE])
    entry = advance(ctx.session.date, start_offset_sessions)
    shared = exit_rule_at(ctx, edge, None, declared, bounded=True)
    longs = [p.instrument_id for p in picks if _shape(p) is Shape.LONG_SHARES]
    own = _fallbacks(ctx, edge, shared, longs, declared)
    out = []
    for pick in picks:
        cell = closes[pick.instrument_id][0]
        close = None if cell.value is None else float(cell.value)
        shape = _shape(pick)
        rule = own.get(pick.instrument_id, shared)
        price, stop, stop_unknown = _stop(edge, shape, close, rule)
        hold = rule.hold_sessions
        out.append(
            ExamplePosition(
                edge.id, pick.instrument_id, shape, close, price, stop, entry,
                None if hold is None else advance(entry, hold), pick.weight,
                shape is Shape.SHORT_SHARES, cell.unknown if close is None else None,
                stop_unknown, rule.unknown if hold is None else None,
            )
        )  # fmt: skip
    return tuple(out)
