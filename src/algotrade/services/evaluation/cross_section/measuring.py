"""Measure an edge's legs over chunks of decision sessions (ADR 0053, ADR 0063): the scopes and
variants a run evaluates, the outcome rows of each chunk's entry sessions, one statistic per
(plan, variant, leg) kept as a stored row and decoded back, and the random-pick draws matched to
a screener's legs. Split from ``harness.py`` (at its line cap): the harness plans and reuses
legs and assembles the evaluation; this module computes them and reads outcomes only through the
store readers it is handed (``data.outcomes``), as the harness does."""

import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.edges.identity import LONG, SHORT, identity_dict
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.verdict import OptionCosts
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.calendar import window_end
from algotrade.data import StoreReader
from algotrade.data.outcomes import (
    RESIDUAL_FIELDS,
    STOCK,
    GrainReads,
    attach_residuals,
    missing_outcomes,
    read_residuals,
    reads_of,
)
from algotrade.engines.screening.gate import OPEN
from algotrade.features.framework.feature import strictest
from algotrade.services.evaluation.cross_section.baselines.variant import (
    Variant,
    _Scope,
    beside,
    grain_of,
    run_keys,
    variant_scope,
)
from algotrade.services.evaluation.cross_section.detail.licences import outcome_licence
from algotrade.services.evaluation.cross_section.events import EventSchedule
from algotrade.services.evaluation.cross_section.hit import (
    needs_residual,
    own_rows,
    short_view,
)
from algotrade.services.evaluation.cross_section.legs.key import (
    DRAW_LEG_VERSION,
    LEG_VERSION,
    leg_key,
    universe_hash,
)
from algotrade.services.evaluation.cross_section.legs.reuse import (
    LegId,
    Need,
    Reuse,
    lost_error,
)
from algotrade.services.evaluation.cross_section.legs.rows import (
    LegRecord,
    OutcomeRead,
    decode_leg,
    encode_leg,
)
from algotrade.services.evaluation.cross_section.measures import (
    SessionStat,
)
from algotrade.services.evaluation.cross_section.random_picks import (
    RandomStat,
    generator,
    long_short_stat,
    random_stat,
)
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.scoring.pick_rows import (  # noqa: F401
    NO_ENTRY_BAR,
    _picks,
)
from algotrade.services.evaluation.cross_section.scoring.session_stat import (  # noqa: F401
    MEASURED_COVERAGE,
    Names,
    _outcomes,
    _stat,
    names_for,
)
from algotrade.services.evaluation.cross_section.sessions import Leg
from algotrade.services.evaluation.portfolio_level.ordered import in_order
from algotrade.services.evaluation.portfolio_level.trades import trades_of
from algotrade.services.evaluation.portfolio_level.walk import Book
from algotrade.services.evaluation.training.bound import scored_identity

CHUNK_SESSIONS = 20  # decision sessions screened and measured before the frames are dropped


def _drawing(spec: "_RandomSpec", variant: Variant, block: Sequence[Leg], edge: Edge) -> bool:
    """Whether the screener's legs in ``block`` carry random draws: out of sample only, and never
    for a portfolio_return book (its value is the book's, not a name's: no random names to draw)."""
    return (
        spec.split is not None
        and variant.role == "screener"
        and block[0].decision >= spec.split
        and edge.outcome.kind != PORTFOLIO_KIND
    )


def _needs(
    plans: Sequence["_Plan"],
    variants: Sequence[Variant],
    schedules: Mapping[str, EventSchedule],
    spec: "_RandomSpec",
) -> list[Need]:
    """Every leg of the run (``legs/reuse.py`` keeps those whose window has closed)."""
    found = []
    for p in plans:
        events = schedules.get(p.scope.key)
        for variant in variants:
            key = spec.key_for(variant_scope(p.scope, variant), variant)
            for block in p.blocks:
                drawing = _drawing(spec, variant, block, p.scope.edge)
                for leg in block:
                    names = None if events is None else tuple(sorted(events.names[leg.decision]))
                    id_: LegId = (key, p.scope.key, variant.id, p.horizon, leg.decision)
                    found.append(Need(id_, leg.entry, drawing, names))
    return found


@dataclass(frozen=True)
class _Plan:
    """One scope at one horizon: its blocks of decision legs."""

    scope: _Scope
    horizon: int
    blocks: Sequence[Sequence[Leg]]

    @property
    def key(self) -> tuple[str, int]:
        return self.scope.key, self.horizon


@dataclass
class _Measured:
    """What the chunks left: per plan and variant the statistic of each leg (by decision
    session) and the legs lost to a missing table (with it); per horizon the entry sessions
    with a closed window. Frames and screens are gone."""

    legs: dict[tuple[tuple[str, int], str], dict[date, SessionStat]]
    lost: dict[tuple[tuple[str, int], str], dict[date, str]]
    closed: dict[int, set[date]]
    stored: dict[tuple[int, date], frozenset[str]]  # (horizon, S) -> names with an outcome row
    randoms: dict[tuple[tuple[str, int], str], dict[date, RandomStat]]  # per plan and screener
    rows: list[Mapping[str, Any]] = field(default_factory=list)  # the legs, as stored rows
    outcome_reads: dict[tuple[str, int, date], OutcomeRead] = field(default_factory=dict)
    seqs: Mapping[date, int] = field(default_factory=dict)  # entry session -> outcome partition seq
    outcome_licence: str = "open"  # the strictest licence of the outcome rows read (E1)
    closed_other: dict[int, set[date]] = field(default_factory=dict)  # a position baseline's grain
    # per plan (scope key, horizon): the entry sessions with a row of ITS position key; ``closed``
    # is per horizon, over every key of the run (one setup's rows never close another's S)
    plan_closed: dict[tuple[str, int], set[date]] = field(default_factory=dict)
    # an in-order edge (a rule reads ``portfolio.*``, ADR 0088 G15): per plan and variant the
    # book of its trades decided so far, and the gate state decided with its row at each session
    books: dict[tuple[tuple[str, int], str], Book] = field(default_factory=dict)
    gates: dict[tuple[tuple[str, int], str], dict[date, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class _RandomSpec:
    """What a leg is keyed and drawn by: the first out-of-sample session (None: no draws), the
    draws per session and the hash of the user's expression-feature definitions, which with the
    trial seed the draws through the leg key (``legs/key.py``); the run's range and ``as_of`` do
    not. ``user_id`` and ``edge_id`` name the rows the legs are stored as; ``costs`` is the site's
    cost grid in bp (each leg counts its hits at every level, so it is in the key too)."""

    split: date | None
    draws: int
    expr_hash: str
    user_id: str
    edge_id: str
    costs: tuple[float, ...]
    adv_floor: float | None = None  # a short leg's least dollar volume (in the key of its legs)
    option_costs: OptionCosts | None = None  # an option_pnl leg's levels (in the key of its legs)
    keys: dict[tuple[str, str], str] = field(default_factory=dict)  # (scope, variant) -> leg key
    draw_keys: dict[tuple[str, str], str] = field(default_factory=dict)  # same, for the draws

    def key_for(self, scope: "_Scope", variant: "Variant") -> str:
        """The leg key of one scope's screener: what its legs are a function of."""
        found = self.keys.get((scope.key, variant.id))
        if found is None:
            found = self.keys[scope.key, variant.id] = self._key(scope, variant, LEG_VERSION)
        return found

    def draw_key_for(self, scope: "_Scope", variant: "Variant") -> str:
        """The key that seeds the draws: ``key_for`` at the frozen ``DRAW_LEG_VERSION``."""
        found = self.draw_keys.get((scope.key, variant.id))
        if found is None:
            found = self.draw_keys[scope.key, variant.id] = self._key(
                scope,
                variant,
                DRAW_LEG_VERSION,
                costed=False,  # a seed never moves with costs
            )
        return found

    def _key(
        self, scope: "_Scope", variant: "Variant", leg_version: int, costed: bool = True
    ) -> str:
        """One leg key at ``leg_version``; ``costed``: an option leg's key holds the costs."""
        priced = costed and scope.edge.outcome.kind == CHAIN_KIND and self.option_costs is not None
        key = leg_key(
            _trial_hash(scope, variant),
            universe_hash(scope.universe),
            scope.iv_field,
            scope.edge.event_class,
            scope.edge.outcome.start_offset_sessions,
            self.draws,
            self.expr_hash,
            scope.edge.top_k,
            scope.edge.base,
            scope.edge.picks,
            self.costs,
            None if scope.edge.outcome.side == LONG else self.adv_floor,
            scope.edge.event_subtype,
            scope.edge.outcome.hold_rank,
            leg_version,
            asdict(self.option_costs) if priced and self.option_costs else None,
        )
        return key


def _measure(
    reader: StoreReader,
    session: SessionReads,
    plans: Sequence[_Plan],
    variants: Sequence[Variant],
    schedules: Mapping[str, EventSchedule],
    as_of: datetime,
    spec: _RandomSpec,
    reuse: Reuse,
) -> _Measured:
    """One statistic per (plan, variant, leg), over chunks of ``CHUNK_SESSIONS`` decision
    sessions: each chunk reads the outcomes of its entry sessions, screens its sessions and
    keeps only the statistics, so peak memory does not grow with the range. Every leg is
    stored as a row (``legs/rows.py``) and measured from that row's decoded form, so a run that
    computes a leg and one that reads it hold the same numbers. Only the sessions of ``reuse``
    are computed; its stored legs are taken as they are (``legs/reuse.py``)."""
    out = _Measured({}, {}, {}, {}, {})
    reads = _reads(plans)  # the one outcome grain the plans read (an option_pnl: the chain's)
    cross = _beside(plans, variants)  # a position baseline on the other outcome grain
    out.outcome_licence = _entries_licence(reader, reads, cross, plans, as_of)  # reused legs too
    todo = reuse.days
    legs = [lg for p in plans for b in p.blocks for lg in b if todo is None or lg.decision in todo]
    days = sorted({leg.decision for leg in legs})
    residuals = any(needs_residual(p.scope.edge) for p in plans)  # their stamps count too
    entries = {day for leg in legs for day in leg.candidates}
    out.seqs = reads.seqs(reader, entries, residuals)  # before any outcome row is read
    out.seqs = both_seqs(reader, entries, out.seqs, cross)  # a commit to either is new
    failed: dict[int, MissingDataError] = {}
    out.closed.update({p.horizon: set(reuse.closed.get(p.horizon, ())) for p in plans})
    out.closed_other.update({h: set(c) for h, c in out.closed.items()})
    out.plan_closed.update({p.key: set(reuse.closed.get(p.horizon, ())) for p in plans})
    step = 1 if any(in_order(p.scope.edge) for p in plans) else CHUNK_SESSIONS
    for at in range(0, len(days), step):  # in order: one session per chunk, the book between
        chunk = set(days[at : at + step])
        closed = _read_closed(reader, plans, chunk, as_of, out, failed, reads)
        aside = (  # the other grain: a baseline lacking its rows is not measured, never a failure
            _read_closed(reader, plans, chunk, as_of, out, {}, cross, out.closed_other)
            if cross
            else closed
        )
        for day in sorted(chunk):  # lockstep over the scopes: one selection read per session
            with session.attribute(day):
                for p in plans:
                    if any(leg.decision == day for b in p.blocks for leg in b):
                        session.eligible(p.scope.universe, day)
        for p in plans:
            for variant in variants:
                events = schedules.get(p.scope.key)
                grains = {reads.grain: closed, (cross or reads).grain: aside}
                _measure_plan(p, variant, session, events, chunk, grains, out, spec, as_of)
        session.release()
    reuse.adopt(out.legs, out.lost, out.randoms, {p.key for p in plans})
    for (entry, horizon), names in reuse.names.items():  # the entries no chunk read
        out.stored.setdefault((horizon, entry), names)
    for held in reuse.reads.values():
        session.adopt(held, reuse.snapshots())
    for horizon, missing in failed.items():
        if not out.closed[horizon]:  # nothing stored for any session of the range
            raise missing
    _refuse_unowned(out, plans, reads, bool(legs), entries)
    for (_, variant_id), lost in out.lost.items():  # a variant measured nowhere is a failure
        if lost and len(lost) == len(out.legs[_, variant_id]):
            raise lost_error(lost)
    return out


def both_seqs(
    reader: StoreReader,
    entries: Collection[date],
    seqs: Mapping[date, int],
    other: GrainReads | None,
) -> dict[date, int]:
    """``seqs`` (those of the run's own grain) plus the ``other`` grain's of each entry session
    when there is one (a position baseline reads it): a commit to either makes a stored leg stale
    (ADR 0063)."""
    if other is None:
        return dict(seqs)
    found = other.seqs(reader, entries)
    return {d: n + found.get(d, 0) for d, n in seqs.items()}


def _entries_licence(
    reader: StoreReader,
    reads: GrainReads,
    cross: GrainReads | None,
    plans: Sequence[_Plan],
    as_of: datetime,
) -> str:
    """The strictest licence recorded on the outcome rows of every entry session the plans
    cover, a stored leg reused by this run included (its outcome rows are not read again, so the
    chunk reads alone would miss them); ``cross``: the other grain's rows a position baseline
    reads."""
    entries = {day for p in plans for b in p.blocks for leg in b for day in leg.candidates}
    found = reads.licence(reader, entries, as_of)
    if cross is not None:
        found = [*found, *cross.licence(reader, entries, as_of)]
    return strictest(outcome_licence(f) for f in found)


def _grain(plans: Sequence[_Plan]) -> str:
    """The one outcome grain the plans read (option trades, share paths or price windows): an
    edge's variants all read one (``config/edges/positions/chain.check_kinds``)."""
    grains = {grain_of(p.scope) for p in plans}
    if len(grains) > 1:
        raise ConfigurationError(f"the plans read several outcome grains: {sorted(grains)}")
    return next(iter(grains), STOCK)


def _refuse_unowned(
    out: _Measured, plans: Sequence[_Plan], reads: GrainReads, measured: bool, entries: set[date]
) -> None:
    """A plan of a keyed grain with no row of its own key at any entry session is missing data,
    never an uncovered session (the horizon's closed sessions are every key's)."""
    for p in plans:
        if measured and reads.grain != STOCK and not out.plan_closed[p.key]:
            raise reads.missing(sorted(entries))


def _reads(plans: Sequence[_Plan]) -> GrainReads:
    """The reads of the grain the plans' outcomes are on."""
    return reads_of(_grain(plans), run_keys(plans))


def _beside(plans: Sequence[_Plan], variants: Sequence[Variant]) -> GrainReads | None:
    """The reads of the other grain a position baseline is valued on, if any."""
    other = beside(plans, variants)
    return None if other is None else reads_of(other, run_keys(plans))


def _read_closed(
    reader: StoreReader,
    plans: Sequence[_Plan],
    chunk: set[date],
    as_of: datetime,
    out: _Measured,
    failed: dict[int, MissingDataError],
    reads: GrainReads | None = None,
    seen: dict[int, set[date]] | None = None,
) -> dict[int, dict[date, pd.DataFrame]]:
    """The outcome rows of the chunk's entry sessions by horizon and entry session, of the grain
    ``reads`` (the plans' own when None). ``seen``: the closed entry sessions of the other grain
    (``out`` keeps the plans' own, and the names it holds, for the plans' grain only)."""
    closed: dict[int, dict[date, pd.DataFrame]] = {}
    wanted = {
        h: sorted(
            {day for p in plans if p.horizon == h for b in p.blocks for leg in b
             if leg.decision in chunk for day in leg.candidates}
        )
        for h in sorted({p.horizon for p in plans})
    }  # fmt: skip
    entries = sorted({d for days in wanted.values() for d in days})
    reads = _reads(plans) if reads is None else reads
    stored = reads.read_stored(reader, entries, as_of) if entries else None  # once for the horizons
    residual_horizons = {
        p.horizon for p in plans if needs_residual(p.scope.edge) and reads.grain == STOCK
    }
    residuals = read_residuals(reader, entries, as_of) if entries and residual_horizons else None
    have: set[date] = set()  # the entry sessions with a partition visible at ``as_of``
    if stored is not None:  # plain strings: the ``isin`` over arrow strings is the slow path
        stored = stored.assign(instrument_id=stored["instrument_id"].astype(object))
        have = {_day(v) for v in stored["session_date"].unique()}
    for horizon, days in wanted.items():
        closed[horizon] = {}
        if not days:
            continue
        if stored is None or not any(days[0] <= d <= days[-1] for d in have):
            failed.setdefault(horizon, reads.missing(days))
            continue  # nothing stored in its span
        frame = reads.at_hold(stored, horizon, days, as_of)
        columns = list(reads.columns)
        if horizon in residual_horizons:  # a factor-neutral outcome of this horizon (EB H11)
            frame = attach_residuals(frame, residuals, horizon)
            columns += RESIDUAL_FIELDS
        kept = frame[columns]  # what apply_outcome reads, no more
        closed[horizon] = dict(tuple(kept.groupby(frame["session_date"].map(_day))))
        if seen is not None:
            seen[horizon] |= set(closed[horizon])
            continue
        out.closed[horizon] |= set(closed[horizon])
        for p in (q for q in plans if q.horizon == horizon):
            owned = (
                {e for e, r in closed[horizon].items() if not own_rows(p.scope.edge, r).empty}
                if reads.grain != STOCK
                else set(closed[horizon])
            )
            out.plan_closed.setdefault(p.key, set()).update(owned)
        for entry, rows in closed[horizon].items():
            out.stored[horizon, entry] = frozenset(rows["instrument_id"])
    return closed


def _measure_plan(
    p: _Plan,
    variant: Variant,
    session: SessionReads,
    events: EventSchedule | None,
    chunk: set[date],
    grains: Mapping[str, Mapping[int, Mapping[date, pd.DataFrame]]],
    out: _Measured,
    spec: _RandomSpec,
    as_of: datetime,
) -> None:
    """The statistic of each of ``p``'s legs in the chunk whose window closed; for a screener
    and a split, also its random-pick draws on the legs it measured (``_measure_random``). The
    reads of a leg are logged against its decision session."""
    scope = variant_scope(p.scope, variant)  # a position baseline: the template's outcome
    other = grain_of(scope) != grain_of(p.scope)  # on the grain the plans do not read
    closed = grains[grain_of(scope)]
    mine = out.legs.setdefault((p.key, variant.id), {})
    lost = out.lost.setdefault((p.key, variant.id), {})
    ordered = in_order(p.scope.edge)  # a rule reads the book of the setup's own trades (G15)
    option = scope.edge.outcome.kind == CHAIN_KIND
    for block in p.blocks:
        for leg in block:
            if leg.decision not in chunk:
                continue
            if _unclosed(leg, closed[p.horizon], out.plan_closed[p.key], other):
                _unknown_book(out, p, variant, leg, ordered, option)
                continue  # no partition at its entry (or rows of another setup's key only)
            names = None if events is None else events.names[leg.decision]
            rows = closed[p.horizon][leg.entry]
            drawing = _drawing(spec, variant, block, scope.edge)
            with session.attribute(leg.decision):
                book = (
                    out.books.setdefault((p.key, variant.id), Book(option=option))
                    if ordered
                    else None
                )
                extra = _row_at(book, session, leg.decision)  # trades decided before D only
                state = None
                if p.scope.edge.gate is not None:  # its market read is logged against D
                    state = session.gate(p.scope.edge.gate, leg.decision, extra)
                    if ordered:
                        out.gates.setdefault((p.key, variant.id), {})[leg.decision] = state
                entered, kept, missing = session.entered(  # an entry condition: own S per name
                    scope.edge,
                    scope.universe,
                    variant.id,
                    leg,
                    closed[p.horizon],
                    rows,
                    p.scope.edge,
                    extra,
                )
                if missing is not None:  # no partition at an S a name entered at: lost
                    session.lost[variant.id, leg.decision] = missing_outcomes([missing]).dataset
                if kept is None:  # lost to a table (``session.lost``): counted, not measured
                    regime, drawn = session.label(leg.decision), None
                    stat = SessionStat(leg.decision, regime, excluded_coverage=1)
                else:
                    stat = _stat(
                        scope, session, variant, leg, p.horizon, kept, names, spec.costs,
                        spec.adv_floor, spec.option_costs, entered,
                    )  # fmt: skip
                    drawn = (
                        _measure_random(p, variant, leg, stat, session, names, kept, spec)
                        if drawing
                        else None
                    )
            record = LegRecord(
                key=spec.key_for(scope, variant),
                trial_hash=_trial_hash(scope, variant),
                edge_variant=p.scope.key,
                variant=variant.id,
                horizon=p.horizon,
                entry=leg.entry,
                stat=stat,
                outcomes_as_of=as_of,
                random=drawn,
                event_ids=None if names is None else tuple(sorted(names)),
                lost_table=session.lost.get((variant.id, leg.decision)),
                snapshot=session.snapshot_of(variant, leg.decision),
                outcome_seq=out.seqs.get(leg.entry),
            )
            row = encode_leg(record, spec.user_id, spec.edge_id)
            out.rows.append(row)
            stored = decode_leg(row)  # the numbers every statistic below is computed from
            mine[leg.decision] = stored.stat
            _book_in(book, p.scope.edge.gate is None or state == OPEN, stored.stat, leg, p.horizon)
            if stored.random is not None:
                out.randoms.setdefault((p.key, variant.id), {})[leg.decision] = stored.random
            if stored.lost_table is not None:
                lost[leg.decision] = stored.lost_table
            if not other:  # the plans' own grain is the one whose reads are logged
                out.outcome_reads[p.scope.key, p.horizon, leg.decision] = OutcomeRead(
                    leg.decision, p.scope.key, p.horizon, leg.entry, as_of, out.seqs.get(leg.entry)
                )


def _unclosed(leg: Leg, closed: Mapping[date, Any], owned: set[date], other: bool) -> bool:
    """Whether ``leg`` has no closed window to measure: no partition at its entry, or (the plans'
    own grain) none of this setup's own key."""
    return leg.entry not in closed or (not other and leg.entry not in owned)


def _unknown_book(
    out: _Measured, p: _Plan, variant: Variant, leg: Leg, ordered: bool, option: bool
) -> None:
    """A leg never measured has trades no one knows: an in-order setup's book is unknown through
    its window, so a later session never reads a book too empty."""
    if ordered:
        book = out.books.setdefault((p.key, variant.id), Book(option=option))
        book.lost(window_end(leg.entry, p.horizon))


def _row_at(book: Book | None, session: SessionReads, day: date) -> Mapping[str, Any] | None:
    """The portfolio row's values at D (None: the edge reads no book), from trades decided at
    sessions before D; the open trades' sectors are read at D."""
    if book is None:
        return None
    return book.row_at(day, lambda d, ids: session.sectors(frozenset(ids), d)).values


def _book_in(book: Book | None, open_: bool, stat: SessionStat, leg: Leg, horizon: int) -> None:
    """Put the trades of the leg just measured into the book when its gate was open (or there is
    none); a leg whose picks are not known (not measured) leaves the book unknown through the end
    of its window, never too empty."""
    if book is None or not open_:
        return
    if stat.excluded_coverage:
        book.lost(window_end(leg.entry, horizon))
    else:
        book.add(trades_of(stat.picks, leg.entry, horizon))


def _measure_random(
    p: _Plan,
    variant: Variant,
    leg: Leg,
    stat: SessionStat,
    session: SessionReads,
    event_names: frozenset[str] | None,
    rows: pd.DataFrame,
    spec: _RandomSpec,
) -> RandomStat | None:
    """The random-pick draws matched to one screener at one leg it measured: as many names as
    the screener held there (``k = 0`` still keeps the leg's base), so the null has the same
    sample size, sessions and base as the screener's own result (``random_picks.py``)."""
    if stat.excluded_coverage:
        return None
    eligible = session.eligible(p.scope.universe, leg.decision)
    names = names_for(p.scope.edge, eligible, event_names)
    res = _outcomes(p.scope, session, leg, p.horizon, rows, eligible, names.ids, spec.option_costs)
    counted = res[res["excluded"] == ""]
    key, label = spec.draw_key_for(p.scope, variant), f"{p.scope.key}|{variant.id}"
    rng = generator(key, label, p.horizon, leg.decision)
    side = p.scope.edge.outcome.side
    if side == LONG:  # the sector-matched draws are the long leg's (a short leg has none)
        return random_stat(
            leg.decision,
            counted,
            names.pickable,
            len(stat.pick_values),
            spec.draws,
            rng,
            sectors=session.sectors(frozenset(counted.index), leg.decision),
            pick_ids=[x.instrument_id for x in stat.picks if x.reason == ""],
            sector_rng=generator(key, f"{label}|sector", p.horizon, leg.decision),
        )
    # The short leg is drawn from the names it could hold (the dollar volume floor), minus the
    # draw; a long-short spread is two draws, the long's then the short's, one generator.
    adv = session.adv(eligible, leg.decision)
    floor = spec.adv_floor or 0.0
    liquid = {i for i in names.pickable if (v := adv.get(i)) is not None and v >= floor}
    shorts = short_view(res).loc[counted.index]
    if side == SHORT:
        return random_stat(leg.decision, shorts, liquid, len(stat.pick_values), spec.draws, rng)
    long = random_stat(
        leg.decision, counted, names.pickable, len(stat.pick_values), spec.draws, rng
    )
    short = random_stat(leg.decision, shorts, liquid, len(stat.short_values or ()), spec.draws, rng)
    return None if long is None or short is None else long_short_stat(long, short)


def _drawn(block: Sequence[Leg], legs: Mapping[date, RandomStat], closed: set[date]) -> bool:
    """Whether a block has draws: every leg whose window closed has them, as ``pool_stats`` drops
    a block with a day the screener could not measure, so must the draws matched to it."""
    mine = [leg for leg in block if leg.entry in closed]
    return bool(mine) and all(leg.decision in legs for leg in mine)


def _trial_hash(scope: _Scope, variant: Variant) -> str:
    """The trial's identity: the screener's config hash, the edge variant's id and the resolved
    outcome and universe (the edge's own for ``main``), so an edited override, offset or
    horizon is another trial. The split is not part of it: an exploratory run adds no trial (its
    "all" slice, which the deflated Sharpe ratio reads, does not depend on the split)."""
    payload: list[Any] = [
        variant.hash,
        scope.key,
        identity_dict(asdict(scope.edge.outcome)),
        scope.edge.universe,
    ]
    if scope.edge.picks != "event":
        payload.append(f"picks={scope.edge.picks}")
    if scope.overrides:  # a main or plain variant keeps its earlier key
        payload.append(scope.overrides)
    if scope.scores:  # a refit is another feature version, so another trial (E14)
        payload.append(scored_identity(scope.scores))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _day(value: Any) -> date:
    return pd.Timestamp(value).date()
