"""Measure an edge's legs over chunks of decision sessions (ADR 0053, ADR 0063): the scopes and
variants a run evaluates, the outcome rows of each chunk's entry sessions, one statistic per
(plan, variant, leg) kept as a stored row and decoded back, and the random-pick draws matched to
a screener's legs. Split from ``harness.py`` (at its line cap): the harness plans and reuses
legs and assembles the evaluation; this module computes them and reads outcomes only through the
store readers it is handed (``data.outcomes``), as the harness does."""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.config.edges.document import (
    Edge,
)
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.outcomes import (
    OUTCOME_FIELDS,
    missing_outcomes,
    outcome_seqs,
    read_stored,
    select_outcomes,
)
from algotrade.engines.screening.runner import RunCoverage
from algotrade.quant.edges.statistics import moments
from algotrade.services.evaluation.cross_section.events import EventSchedule
from algotrade.services.evaluation.cross_section.hit import (
    INVALID_IMPLIED_VOL,
    NO_IMPLIED_VOL,
    UNMEASURED,
    apply_outcome,
    is_return,
    needs_implied_vol,
)
from algotrade.services.evaluation.cross_section.legs.key import (
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
    Pick,
    SessionStat,
    decile_means,
)
from algotrade.services.evaluation.cross_section.random_picks import (
    RandomStat,
    generator,
    random_stat,
)
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.sessions import (
    Leg,
)

BENCHMARK = "SPY"  # outcomes are read over SPY for every edge: returns and vols ignore it


# A stale universe stays measured (it is flagged pre_snapshot); partial or empty screens are not.
# A session is measured only when at least this share of the eligible names carries the edge's
# score; the rest are counted as ``unscored`` and never ranked (recent listings lack a year of
# history, but a session where the signal was not computed at all is dropped). The screen's own
# coverage (``DEFAULT_MIN_COVERAGE``) is a different check.
MIN_SCORE_COVERAGE = 0.8


MEASURED_COVERAGE = (RunCoverage.COMPLETE, RunCoverage.UNIVERSE_INCOMPLETE)


CHUNK_SESSIONS = 20  # decision sessions screened and measured before the frames are dropped
OUTCOME_COLUMNS = ("instrument_id", "horizon_sessions", *OUTCOME_FIELDS)  # kept per entry session
NO_ENTRY_BAR = "no_entry_bar"  # a pick's reason when its name has no outcome row at S


@dataclass(frozen=True)
class Variant:
    id: str
    role: str  # "screener" | "baseline"
    config: ResolvedConfig


@dataclass(frozen=True)
class _Scope:
    """One evaluation of the edge: ``main`` or one of its ``[[variants]]``."""

    key: str
    edge: Edge  # the edge with the variant's outcome and universe applied
    universe: Selection
    iv_field: str  # the outcome's own, else the run's
    overrides: tuple[str, ...] = ()  # the variant's base / picks overrides, in its trial key


@dataclass(frozen=True)
class Names:
    """The names of one edge variant at one decision session: ``ids`` the base (the rate and
    the deciles are over them), ``pickable`` those a pick may be."""

    ids: frozenset[str]
    pickable: frozenset[str]


def names_for(edge: Edge, eligible: frozenset[str], event_names: frozenset[str] | None) -> Names:
    """The base and the pickable names: an event schedule narrows them to the event's names
    (``base = "event"``; ``picks = "universe"`` keeps every eligible name pickable)."""
    pickable = (
        eligible if event_names is None or edge.picks == "universe" else event_names & eligible
    )
    ids = (
        (eligible if event_names is None else event_names & eligible)
        if edge.base == "event"
        else eligible
    )
    return Names(ids, pickable)


def _outcomes(
    scope: _Scope,
    session: SessionReads,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    eligible: frozenset[str],
    ids: frozenset[str],
) -> pd.DataFrame:
    """The stored outcomes of ``ids`` scored by the edge's outcome (``apply_outcome``), indexed
    by instrument; ``excluded`` is non-empty for a name that does not count. It depends only on
    the scope, the horizon and D (``rows`` are that horizon's at the entry), so it is kept."""
    day = leg.decision

    def score() -> pd.DataFrame:
        inside = rows[rows["instrument_id"].isin(ids)]
        implied = (
            session.implied(scope.iv_field, eligible, day)
            if needs_implied_vol(scope.edge)
            else None
        )
        return apply_outcome(scope.edge, inside, implied).set_index("instrument_id")

    return session.outcomes(scope.key, horizon, day, score)


def _stat(
    scope: _Scope,
    session: SessionReads,
    variant: Variant,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    event_names: frozenset[str] | None,
    costs: Sequence[float],
) -> SessionStat:
    """One variant at one decision session: ``rows`` are the stored outcomes at the entry
    session. The eligible names, the screen, the implied vol and the picks' ADV are read at D.
    ``event_names`` (an event schedule): the picks are the qualified names within them, and the
    base is them (``base = "event"``) or every eligible name. ``costs``: the site's cost grid
    (bp), whose hits a return outcome's leg also counts."""
    edge, day = scope.edge, leg.decision
    run, eligible = session.run(variant, day), session.eligible(scope.universe, day)
    if (
        run is None or run.coverage not in MEASURED_COVERAGE
    ):  # read incomplete data: not measured, counted
        return SessionStat(session=day, regime=session.label(day), excluded_coverage=1)
    names = names_for(scope.edge, eligible, event_names)
    pickable, ids = names.pickable, names.ids
    scored = {i: v for i, v in run.scores.items() if i in ids}
    thin = len(scored) < MIN_SCORE_COVERAGE * len(ids)  # too few scores to rank: no deciles
    res = _outcomes(scope, session, leg, horizon, rows, eligible, ids)
    counted = res[res["excluded"] == ""]
    in_universe = [i for i in run.qualified if i in eligible]
    chosen = [i for i in in_universe if i in pickable]
    picks = chosen if edge.top_k is None else chosen[: edge.top_k]
    pick_set = set(picks)
    unmeasured = set(res.index[res["excluded"] == UNMEASURED])  # a window over a bad bar (ADR 0061)
    lost = [i for i in picks if i in unmeasured]
    if picks and len(lost) * 2 > len(picks):  # most picks unmeasured: the session is not measured
        return SessionStat(session=day, regime=session.label(day), excluded_coverage=1)
    have = set(res.index)
    got = [i for i in picks if i in counted.index]
    no_iv = set(res.index[res["excluded"].isin((NO_IMPLIED_VOL, INVALID_IMPLIED_VOL))])
    implied = (
        session.implied(scope.iv_field, eligible, day)  # cached by ``_outcomes``
        if needs_implied_vol(edge)
        else {}
    )
    ranked = (
        []
        if thin
        else sorted((i for i in scored if i in counted.index), key=lambda i: (-scored[i], i))
    )
    deciles = decile_means(counted.loc[ranked, "oriented"].to_list()) if ranked else ()
    levels = _hits_at(scope, session, leg, horizon, rows, ids, costs)
    return SessionStat(
        session=day,
        regime=session.label(day),
        pick_values=tuple(float(v) for v in counted.loc[got, "oriented"]),
        pick_hits=int(counted.loc[got, "hit"].sum()),
        rest=moments(counted.loc[~counted.index.isin(pick_set), "oriented"].to_numpy(dtype=float)),
        base_hits=int(counted["hit"].sum()),
        top_decile=deciles[0] if deciles else None,
        spread=deciles[0] - deciles[-1] if deciles else None,
        deciles=deciles,
        ranked=len(ranked),
        unscored=0 if thin else len(ids) - len(scored),
        excluded_score_coverage=int(thin),
        excluded_missing=sum(
            1 for i in picks if i in have and i not in counted.index and i not in unmeasured
        ),
        excluded_unmeasured=len(lost),
        unmeasured_base=len(unmeasured),
        delisted=int(counted.loc[got, "delisted"].sum()),
        pre_snapshot=run.pre_snapshot,
        outside_universe=len(run.qualified) - len(in_universe),
        no_entry_bar=len(ids - have),
        pick_reference=tuple(float(v) for v in counted.loc[got, "reference"].dropna()),
        pick_touches=int(counted.loc[got, "touch"].fillna(0).sum()),
        no_implied_vol=sum(1 for i in picks if i in no_iv),
        implied_stored=any(v is not None for v in implied.values()),
        picks=_picks(scope.edge, picks, run.scores, res, rows, session.adv(eligible, day)),
        base_hits_at=tuple(int(hits.sum()) for hits in levels),
        pick_hits_at=tuple(int(hits.loc[got].sum()) for hits in levels),
    )


def _picks(
    edge: Edge,
    picks: Sequence[str],
    scores: Mapping[str, float],
    res: pd.DataFrame,
    rows: pd.DataFrame,
    adv: Mapping[str, float | None],
) -> tuple[Pick, ...]:
    """Every pick of a session in rank order (leg v2, ADR 0064): counted or with its reason.
    ``res`` is the scored outcomes of the base names, ``rows`` the stored ones at S."""
    stored = rows[rows["instrument_id"].isin(set(picks))].set_index("instrument_id")
    gross = is_return(edge)
    out = []
    for rank, i in enumerate(picks, start=1):
        if i not in res.index:
            out.append(Pick(i, rank, NO_ENTRY_BAR, score=scores.get(i), adv=adv.get(i)))
            continue
        r = res.loc[i]
        counted = r["excluded"] == ""
        out.append(
            Pick(
                instrument_id=i,
                rank=rank,
                reason=str(r["excluded"]),
                value=_finite(r["oriented"]) if counted else None,
                hit=bool(r["hit"]),
                delisted=bool(r["delisted"]),
                score=scores.get(i),
                gross=_finite(stored.at[i, "fwd_excess_return"]) if gross and counted else None,
                drawdown=_finite(stored.at[i, "fwd_max_drawdown"]),
                adv=adv.get(i),
                reference=_finite(r["reference"]),
                touch=None if _finite(r["reference"]) is None else bool(r["touch"]),
            )
        )
    return tuple(out)


def _finite(value: object) -> float | None:
    number = None if value is None else float(value)  # type: ignore[arg-type]
    return number if number is not None and math.isfinite(number) else None


def _hits_at(
    scope: _Scope,
    session: SessionReads,
    leg: Leg,
    horizon: int,
    rows: pd.DataFrame,
    ids: frozenset[str],
    costs: Sequence[float],
) -> list[pd.Series]:
    """Per level of the cost grid, the ``hit`` of each base name were the round trip to cost
    that many bp instead of the document's ``cost_bps`` (``apply_outcome``'s own rule; ADR 0064
    decision 5); none for an outcome that is not a return. Exclusions do not depend on the cost,
    so the counted names are the session's own."""
    if not is_return(scope.edge):
        return []
    found = []
    for level in costs:
        costed = replace(scope.edge, outcome=replace(scope.edge.outcome, cost_bps=level))

        def score(edge: Edge = costed) -> pd.DataFrame:
            inside = rows[rows["instrument_id"].isin(ids)]
            return apply_outcome(edge, inside).set_index("instrument_id")

        found.append(session.outcomes(f"{scope.key}@{level:g}bp", horizon, leg.decision, score))
    return [frame["hit"] for frame in found]


def _drawing(spec: "_RandomSpec", variant: Variant, block: Sequence[Leg]) -> bool:
    """Whether the screener's legs in ``block`` carry random draws: out of sample only."""
    return spec.split is not None and variant.role == "screener" and block[0].decision >= spec.split


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
            key = spec.key_for(p.scope, variant)
            for block in p.blocks:
                drawing = _drawing(spec, variant, block)
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
    keys: dict[tuple[str, str], str] = field(default_factory=dict)  # (scope, variant) -> leg key

    def key_for(self, scope: "_Scope", variant: "Variant") -> str:
        """The leg key of one scope's screener: what its legs (and draws) are a function of."""
        found = self.keys.get((scope.key, variant.id))
        if found is None:
            found = self.keys[scope.key, variant.id] = leg_key(
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
            )
        return found


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
    todo = reuse.days
    legs = [lg for p in plans for b in p.blocks for lg in b if todo is None or lg.decision in todo]
    days = sorted({leg.decision for leg in legs})
    out.seqs = outcome_seqs(reader, {leg.entry for leg in legs})  # before any outcome row is read
    failed: dict[int, MissingDataError] = {}
    out.closed.update({p.horizon: set(reuse.closed.get(p.horizon, ())) for p in plans})
    for at in range(0, len(days), CHUNK_SESSIONS):
        chunk = set(days[at : at + CHUNK_SESSIONS])
        closed = _read_closed(reader, plans, chunk, as_of, out, failed)
        for day in sorted(chunk):  # lockstep over the scopes: one selection read per session
            with session.attribute(day):
                for p in plans:
                    if any(leg.decision == day for b in p.blocks for leg in b):
                        session.eligible(p.scope.universe, day)
        for p in plans:
            for variant in variants:
                events = schedules.get(p.scope.key)
                _measure_plan(p, variant, session, events, chunk, closed, out, spec, as_of)
        session.release()
    reuse.adopt(out.legs, out.lost, out.randoms, {p.key for p in plans})
    for reads in reuse.reads.values():
        session.adopt(reads, reuse.snapshots())
    for horizon, missing in failed.items():
        if not out.closed[horizon]:  # nothing stored for any session of the range
            raise missing
    for (_, variant_id), lost in out.lost.items():  # a variant measured nowhere is a failure
        if lost and len(lost) == len(out.legs[_, variant_id]):
            raise lost_error(lost)
    return out


def _read_closed(
    reader: StoreReader,
    plans: Sequence[_Plan],
    chunk: set[date],
    as_of: datetime,
    out: _Measured,
    failed: dict[int, MissingDataError],
) -> dict[int, dict[date, pd.DataFrame]]:
    """The outcome rows of the chunk's entry sessions by horizon and entry session."""
    closed: dict[int, dict[date, pd.DataFrame]] = {}
    wanted = {
        h: sorted(
            {leg.entry for p in plans if p.horizon == h for b in p.blocks for leg in b
             if leg.decision in chunk}
        )
        for h in sorted({p.horizon for p in plans})
    }  # fmt: skip
    entries = sorted({d for days in wanted.values() for d in days})
    stored = read_stored(reader, entries, as_of) if entries else None  # once for the horizons
    have: set[date] = set()  # the entry sessions with a partition visible at ``as_of``
    if stored is not None:  # plain strings: the ``isin`` over arrow strings is the slow path
        stored = stored.assign(instrument_id=stored["instrument_id"].astype(object))
        have = {_day(v) for v in stored["session_date"].unique()}
    for horizon, days in wanted.items():
        closed[horizon] = {}
        if not days:
            continue
        if stored is None or not any(days[0] <= d <= days[-1] for d in have):
            failed.setdefault(horizon, missing_outcomes(days))  # nothing stored in its span
            continue
        frame = select_outcomes(stored, horizon, days, BENCHMARK, as_of)
        kept = frame[list(OUTCOME_COLUMNS)]  # what apply_outcome reads, no more
        closed[horizon] = dict(tuple(kept.groupby(frame["session_date"].map(_day))))
        out.closed[horizon] |= set(closed[horizon])
        for entry, rows in closed[horizon].items():
            out.stored[horizon, entry] = frozenset(rows["instrument_id"])
    return closed


def _measure_plan(
    p: _Plan,
    variant: Variant,
    session: SessionReads,
    events: EventSchedule | None,
    chunk: set[date],
    closed: Mapping[int, Mapping[date, pd.DataFrame]],
    out: _Measured,
    spec: _RandomSpec,
    as_of: datetime,
) -> None:
    """The statistic of each of ``p``'s legs in the chunk whose window closed; for a screener
    and a split, also its random-pick draws on the legs it measured (``_measure_random``). The
    reads of a leg are logged against its decision session."""
    mine = out.legs.setdefault((p.key, variant.id), {})
    lost = out.lost.setdefault((p.key, variant.id), {})
    for block in p.blocks:
        for leg in block:
            if leg.decision not in chunk or leg.entry not in closed[p.horizon]:
                continue
            names = None if events is None else events.names[leg.decision]
            rows = closed[p.horizon][leg.entry]
            drawing = _drawing(spec, variant, block)
            with session.attribute(leg.decision):
                stat = _stat(p.scope, session, variant, leg, p.horizon, rows, names, spec.costs)
                drawn = (
                    _measure_random(p, variant, leg, stat, session, names, rows, spec)
                    if drawing
                    else None
                )
            record = LegRecord(
                key=spec.key_for(p.scope, variant),
                trial_hash=_trial_hash(p.scope, variant),
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
            if stored.random is not None:
                out.randoms.setdefault((p.key, variant.id), {})[leg.decision] = stored.random
            if stored.lost_table is not None:
                lost[leg.decision] = stored.lost_table
            out.outcome_reads[p.scope.key, p.horizon, leg.decision] = OutcomeRead(
                leg.decision, p.scope.key, p.horizon, leg.entry, as_of, out.seqs.get(leg.entry)
            )


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
    res = _outcomes(p.scope, session, leg, p.horizon, rows, eligible, names.ids)
    return random_stat(
        leg.decision,
        res[res["excluded"] == ""],
        names.pickable,
        len(stat.pick_values),
        spec.draws,
        generator(
            spec.key_for(p.scope, variant), f"{p.scope.key}|{variant.id}", p.horizon, leg.decision
        ),
    )


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
        variant.config.hash,
        scope.key,
        asdict(scope.edge.outcome),
        scope.edge.universe,
    ]
    if scope.edge.picks != "event":
        payload.append(f"picks={scope.edge.picks}")
    if scope.overrides:  # a main or plain variant keeps its earlier key
        payload.append(scope.overrides)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _day(value: Any) -> date:
    return pd.Timestamp(value).date()
