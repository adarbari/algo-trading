"""The turnover pass of a buy/hold band (ADR 0053 amendment 2026-10-18; ``[outcome] hold_rank``):
one pass over a variant's decision sessions in session order that turns its legs' picks into the
names a book with a band would hold, and charges the round-trip cost on entries and exits only.

Legs stay independent (ADR 0063): a leg holds the picks of its own session (ranks ``1..top_k``) and
the band's (``top_k + 1..hold_rank``) and never looks at another session. The pass is reporting,
over the legs a run decoded, so it needs no leg to be computed again and a run that reuses legs
and one that computes them give the same series.

The rule, per session in order: a name is *held* when it is one of the counted picks (it enters
at rank <= ``top_k``), or when it is a counted band name that the previous session held. A name
in neither leaves. An entry pays half a round trip and an exit half, so a name held through two
sessions pays one trip over both and a name held through none pays one each. A session the screen
did not measure (coverage) breaks the chain: everything held before it exits and the next
session's names enter. The last session's names exit (charged: the book is closed at the end of
the data, never left open for free). Gross figures are untouched: ``pick_values`` and every hit
stay the legs'; the pass sets ``banded_values`` (the net series) and ``round_trips`` (the
turnover the break-even is scaled by). Decision sessions are taken to be a book's rebalances, one
window each; the document refuses a band where windows overlap (``config/edges/document.py``)."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from algotrade.config.edges.portfolio import CASH
from algotrade.services.evaluation.cross_section.measures import SessionStat

ENTRY, EXIT = 0.5, 0.5  # the share of a round trip an entry and an exit pay


def _named(stat: SessionStat) -> tuple[list[str], dict[str, float], list[str]]:
    """``(counted ids best-first, value by id of the counted picks and the band names, band ids
    best-first)``: oriented values net of one round trip, as the legs store them."""
    values: dict[str, float] = {}
    top: list[str] = []
    counted = iter(stat.pick_values)
    for pick in stat.picks:
        if pick.reason == "":
            values[pick.instrument_id] = next(counted)
            top.append(pick.instrument_id)
    band: list[str] = []
    for pick in stat.band:
        if pick.value is not None:
            values[pick.instrument_id] = pick.value
            band.append(pick.instrument_id)
    return top, values, band


def _held(stats: Sequence[SessionStat]) -> list[tuple[str, ...]]:
    """The names held at each session, in rank order (counted picks, then the band's)."""
    held: list[tuple[str, ...]] = []
    before: frozenset[str] = frozenset()
    for stat in stats:
        if stat.excluded_coverage:
            held.append(())
            before = frozenset()
            continue
        top, _, band = _named(stat)
        now = (*top, *(i for i in band if i in before and i not in top))
        held.append(now)
        before = frozenset(now)
    return held


def apply_hold_bands(
    stats: Sequence[SessionStat], cost_bp: float | None, sign: float = 1.0
) -> tuple[SessionStat, ...]:
    """``stats`` (one variant at one horizon, one per decision session) with the
    band's net series: ``banded_values`` per session and ``round_trips``. ``cost_bp``: the
    document's round-trip cost the legs' values are net of (None: 0); ``sign``: the outcome's
    orientation (``Outcome.sign``). The result is in the order given and deterministic: the same
    legs give the same series whichever run read them."""
    order = sorted(range(len(stats)), key=lambda i: stats[i].session)
    ordered = [stats[i] for i in order]
    held = _held(ordered)
    cost = (cost_bp or 0.0) / 1e4
    done: list[SessionStat] = []
    for at, stat in enumerate(ordered):
        if stat.excluded_coverage:
            done.append(stat)
            continue
        _, values, _ = _named(stat)
        before = frozenset(held[at - 1]) if at else frozenset()
        after = frozenset(held[at + 1]) if at + 1 < len(held) else frozenset()
        banded, trips = [], 0.0
        for name in held[at]:
            paid = (0.0 if name in before else ENTRY) + (0.0 if name in after else EXIT)
            # value = sign * (gross - cost): the same name pays ``paid`` of one round trip
            banded.append(values[name] + sign * cost * (1.0 - paid))
            trips += paid
        done.append(replace(stat, banded_values=tuple(banded), round_trips=trips))
    out = list(stats)
    for slot, stat in zip(order, done, strict=True):
        out[slot] = stat
    return tuple(out)


def _traded(weights: Mapping[str, float]) -> dict[str, float]:
    """The weights a book pays to trade: cash is free to hold and to leave."""
    return {i: w for i, w in weights.items() if i != CASH}


def apply_rebalances(
    stats: Sequence[SessionStat], cost_bp: float | None
) -> tuple[SessionStat, ...]:
    """``stats`` (one portfolio_return variant at one horizon, one per decision session) with the
    net series of a book that trades only the weight change (ADR 0074): ``banded_values`` (the
    session's one value) and ``round_trips`` per session.

    The legs' value is net of one full round trip (the convention of every leg: the whole book
    bought and sold); the book pays ``sum |w_t - w_(t-1)| / 2`` round trips instead, over the
    names (cash excluded), so a book that holds still pays nothing and a full replacement pays
    one. The first session buys its whole book (half a trip per unit of weight), the last
    session's book is sold at the end of the data (charged, as in a band), a session the screen
    could not value breaks the chain (everything held before it is sold, the next session buys
    afresh). The net value is ``stored + cost * (1 - trips)``. Gross figures and the hit stay the
    legs' own. Deterministic and in the order given."""
    order = sorted(range(len(stats)), key=lambda i: stats[i].session)
    ordered = [stats[i] for i in order]
    cost = (cost_bp or 0.0) / 1e4
    books = [_traded(dict(s.weights)) if s.weights else None for s in ordered]
    done: list[SessionStat] = []
    for at, stat in enumerate(ordered):
        book = books[at]
        if book is None:
            done.append(stat)
            continue
        before = (books[at - 1] if at else None) or {}  # a gap or the first session: none held
        into = sum(abs(w - before.get(i, 0.0)) for i, w in book.items())
        into += sum(w for i, w in before.items() if i not in book)  # sold at this rebalance
        trips = into * ENTRY
        if at + 1 == len(books) or books[at + 1] is None:  # the last book, or one before a gap
            trips += sum(book.values()) * EXIT  # is sold
        net = stat.pick_values[0] + cost * (1.0 - trips)
        done.append(replace(stat, banded_values=(net,), round_trips=trips))
    out = list(stats)
    for slot, stat in zip(order, done, strict=True):
        out[slot] = stat
    return tuple(out)
