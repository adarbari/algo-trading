"""Evaluate one edge over a range of sessions (ADR 0053 decisions 5 to 7 and its amendment of
2026-10-08, ``docs/edges-plan.md``).

Each row has a decision session D and an entry session S > D (``sessions``). For each horizon
the edge stores, the decision sessions of its schedule (an event schedule: the sessions with
events, ``events``, pooled into blocks of one horizon) are screened at D for every listed
screener and baseline (``picks``: only what was known at D); the eligible names, the implied
vol and the event names are read at D too. The picks, the base names and the screener's ranking
are joined to the closed outcomes of the partition at S, read as of the run's ``as_of``
(``hit.apply_outcome``), and measured per slice (``measures``). **This is the only module that
reads outcomes** (``read_outcomes``; the picks never see one: a fitness test checks both). A
window not closed has no outcome row and is excluded, never a miss; a name eligible at D with
no outcome row at S has no entry bar (``no_entry_bar``); a block with no closed window at all
is counted in ``unclosed_sessions``. A pick with no implied vol at D (an outcome that reads one)
is excluded and counted per session (``no_implied_vol``) beside whether the ``iv_field`` had a
value for any eligible name then (``implied_stored``): a field stored only after the range
reads as a stated gap, never a silent zero.

An edge's ``[[variants]]`` are evaluated like the edge itself under their own id
(``edge_variant``, "main" for the edge). The deflated Sharpe ratio counts every distinct
(edge variant, variant, config hash, horizon) tried in earlier runs of the edge plus this one
(the trial log, ``results.py``); the probability of backtest overfitting compares the variants'
per-session pick means over the same sessions.

The test slice starts at the run's effective split: the run's ``split_from``, else the edge's own
``frozen_from`` (a copy of a site edge may move it: ADR 0053 amendments ED5a and 2026-10-09). A
run whose split is not the ``frozen_from`` of the site edge the chain started from
(``Edge.site_frozen_from``), or whose edge carries the label ``split_moved_after_viewing``, is
EXPLORATORY: its rows carry its split in their key and the flag, and the split joins the run hash.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from functools import partial
from typing import Any

import pandas as pd

from algotrade.config.edges.document import (
    LEGACY_SITE_CUTOFF,
    LEGACY_SITE_OWNERS,
    MAIN,
    Edge,
    job_name,
)
from algotrade.config.strategy.regime import site_regime
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import MODEL_IMPL, Selection, parse_selection
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.outcomes import (
    OUTCOME_FIELDS,
    missing_outcomes,
    outcome_known,
    outcome_seqs,
    read_stored,
    select_outcomes,
    stored_sessions,
)
from algotrade.engines.screening.runner import RunCoverage
from algotrade.quant.edge_statistics import moments
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.events import EventSchedule, read_events_for
from algotrade.services.evaluation.cross_section.historical import (
    HistoricalCaveat,
)
from algotrade.services.evaluation.cross_section.hit import (
    IMPLIED_VOL_FIELD,
    INVALID_IMPLIED_VOL,
    NO_IMPLIED_VOL,
    UNMEASURED,
    apply_outcome,
    needs_implied_vol,
)
from algotrade.services.evaluation.cross_section.legs.key import (
    HARNESS_VERSION,
    expression_hash,
    leg_key,
    universe_hash,
)
from algotrade.services.evaluation.cross_section.legs.reuse import (
    FULL,
    LegId,
    Need,
    Reuse,
    lost_error,
    plan_reuse,
    tombstones,
)
from algotrade.services.evaluation.cross_section.legs.rows import (
    LegRecord,
    OutcomeRead,
    StoredLegs,
    decode_leg,
    encode_leg,
    encode_outcome,
    encode_reads,
)
from algotrade.services.evaluation.cross_section.legs.store import read_legs
from algotrade.services.evaluation.cross_section.measures import (
    SessionStat,
    SliceMeasure,
    decile_means,
    deflate,
    edge_slices,
    pool_stats,
    slice_measures,
)
from algotrade.services.evaluation.cross_section.random_picks import (
    DEFAULT_DRAWS,
    SEED_VERSION,
    RandomStat,
    generator,
    pool_random,
    random_measures,
    random_stat,
)
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.reporting.report_containment import (
    ReportContainment,
    containment,
    reports_after,
)
from algotrade.services.evaluation.cross_section.sessions import (
    Leg,
    leg_blocks,
)
from algotrade.services.features import catalogue
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.result_writer import ResultWriter

# What an edge contributes to a run's identity (``run_hash``); every other field of ``Edge`` is
# ``BOOKKEEPING`` (the user's or the server's state, prose, the site's decisions): changing one
# never changes what a run measures, so it never makes a new run (nor reseeds the random draws).
# A fitness test classifies every field: a new one fails until it is named here.
RUN_INPUTS = (
    "id", "outcome", "schedule", "universe", "top_k", "screeners", "baselines", "frozen_from",
    "site_frozen_from", "base", "picks", "variants", "scorer_features",
)  # fmt: skip
BOOKKEEPING = (
    "name", "thesis", "mechanism", "persistence", "sources", "quality_bar", "notes", "status",
    "rejection_reason", "evidence", "promoted", "compared", "basis_horizon", "extends", "follow",
    "audit", "owner",
)  # fmt: skip
BENCHMARK = "SPY"  # outcomes are read over SPY for every edge: returns and vols ignore it
# A stale universe stays measured (it is flagged pre_snapshot); partial or empty screens are not.
# A session is measured only when at least this share of the eligible names carries the edge's
# score; the rest are counted as ``unscored`` and never ranked (recent listings lack a year of
# history, but a session where the signal was not computed at all is dropped). The screen's own
# coverage (``DEFAULT_MIN_COVERAGE``) is a different check.
MIN_SCORE_COVERAGE = 0.8
# The one fixed implied-vol field of a run is never a field mixing sources by name or by rule.
MIXED_SOURCE_IV = ("feature.vrp_iv30",)
MEASURED_COVERAGE = (RunCoverage.COMPLETE, RunCoverage.UNIVERSE_INCOMPLETE)
SELECTIONS = "selections"
CHUNK_SESSIONS = 20  # decision sessions screened and measured before the frames are dropped
OUTCOME_COLUMNS = ("instrument_id", "horizon_sessions", *OUTCOME_FIELDS)  # kept per entry session


@dataclass(frozen=True)
class Variant:
    id: str
    role: str  # "screener" | "baseline"
    config: ResolvedConfig


@dataclass(frozen=True)
class VariantResult:
    variant: str
    role: str
    config_hash: str
    horizon: int
    stats: tuple[SessionStat, ...]
    measures: tuple[SliceMeasure, ...]
    edge_variant: str = MAIN  # the edge's own ``[[variants]]`` id, "main" for the edge itself
    iv_source: str | None = None  # the run's iv_field when the outcome reads an implied vol
    licence: str | None = None  # that field's catalogue licence
    lost_sessions: Mapping[str, int] = field(default_factory=dict)  # table -> decision sessions
    report_containment: ReportContainment | None = None  # earnings_expected edges: diagnostic


@dataclass(frozen=True)
class RandomPicks:
    """The random-pick backtest matched to one screener of one edge variant at one horizon:
    one measure per draw over the out-of-sample slice (``random_picks.py``)."""

    edge_variant: str
    horizon: int
    variant: str  # the screener the draws are matched to
    config_hash: str  # that screener's trial hash
    draws: tuple[SliceMeasure, ...]


@dataclass(frozen=True)
class EdgeEvaluation:
    edge_id: str
    run_hash: str
    user_id: str
    benchmark: str  # the edge document's: "SPY" or "none"
    start: date
    end: date
    as_of: datetime
    snapshot: date | None  # the first (here: earliest read) universe snapshot
    results: tuple[VariantResult, ...]
    trials: int
    start_sessions: Mapping[int, int]  # horizon -> decision blocks the schedule gave
    unclosed_sessions: Mapping[int, int]  # horizon -> of those, blocks with no closed window
    event_unknown: Mapping[str, int] = field(default_factory=dict)  # reason -> names excluded
    split_from: date | None = None  # the test slice's first session (None: no split)
    exploratory: bool = False  # the split is not the edge's frozen_from: never evidence
    # Sessions before the first reference snapshot, read from the listing history (ADR 0053
    # amendment 2026-10-09): the rule and the names by path; None when none was read.
    historical: HistoricalCaveat | None = None
    random_picks: tuple[RandomPicks, ...] = ()  # out-of-sample only: none without a split
    # The run's legs, the reads of its sessions and its outcome reads as ``results/edge_legs``
    # rows (``legs/rows.py``): what ``write_edge_eval`` stores with the run (ADR 0063).
    leg_rows: tuple[Mapping[str, Any], ...] = field(default=(), repr=False, compare=False)
    # How the run got its legs (ADR 0063): ``full`` or ``incremental``, the stored legs it
    # reused, the ones it computed and the stored ones it recomputed, by reason.
    mode: str = FULL
    legs_reused: int = 0
    legs_computed: int = 0
    legs_invalidated: Mapping[str, int] = field(default_factory=dict)


def run_hash(
    edge: Edge,
    variants: Sequence[Variant],
    start: date,
    end: date,
    as_of: datetime,
    iv_field: str = IMPLIED_VOL_FIELD,
    split_from: date | None = None,
    random_draws: int = DEFAULT_DRAWS,
) -> str:
    """Identity of one evaluation: the edge's ``RUN_INPUTS``, each variant's config hash, the range,
    the outcomes' ``as_of``, the run's implied-vol field, its effective split, the random draws
    per session and their seed scheme (``SEED_VERSION``), and the harness version."""
    payload = {
        "edge": {k: asdict(edge)[k] for k in RUN_INPUTS},
        "iv_field": iv_field,
        "variants": [(v.id, v.config.hash) for v in variants],
        "range": [start, end],
        "as_of": as_of,
        "split_from": split_from,
        "random": [random_draws, SEED_VERSION],
        "version": HARNESS_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _variants(configs: ConfigStore, user: UserContext, edge: Edge) -> list[Variant]:
    found = [
        *(Variant(s, "screener", resolve_config(configs, s, user)) for s in edge.screeners),
        *(Variant(s, "baseline", resolve_config(configs, s, user)) for s in edge.baselines),
    ]
    if not found:
        raise ConfigurationError(f"edge {edge.id}: no screeners or baselines to evaluate")
    return found


def edge_universe(configs: ConfigStore, user: UserContext, edge: Edge) -> Selection:
    if isinstance(edge.universe, Selection):
        return edge.universe
    for scope in (user.user_id, "site"):
        doc = configs.load(scope, SELECTIONS, edge.universe)
        if doc is not None:
            return parse_selection(doc, f"{scope}/{SELECTIONS}/{edge.universe}")
    raise ConfigurationError(f"edge {edge.id}: unknown selection {edge.universe!r}")


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
) -> SessionStat:
    """One variant at one decision session: ``rows`` are the stored outcomes at the entry
    session. The eligible names, the screen and the implied vol are read at D. ``event_names``
    (an event schedule): the picks are the qualified names within them, and the base is them
    (``base = "event"``) or every eligible name."""
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
    )


def effective_split(run: date | None, edge: Edge) -> tuple[date | None, bool]:
    """(split, exploratory): the run's split, else the edge's own ``frozen_from``. Exploratory
    when it is not the site edge's (a copy whose split moved), or the user moved the split of
    an edge whose out-of-sample result they had seen (a permanent label)."""
    split = run or edge.frozen_from
    moved = "split_moved_after_viewing" in edge.audit.labels
    return split, split != edge.site_frozen_from or moved


def _prior_trials(
    writer: ResultWriter, edge_id: str, user_id: str
) -> set[tuple[str, str, str, int]]:
    """(edge variant, variant, config hash, horizon) of earlier runs; a trial logged before
    edge variants existed is the edge's own ("main"). The site's log includes the runs recorded
    under ``LEGACY_SITE_OWNERS``, so the deflated Sharpe ratio still counts them."""
    found: set[tuple[str, str, str, int]] = set()
    records = list(writer.runs_for(job_name(edge_id, user_id)))
    if user_id == SITE_USER:  # the legacy owners' records from before the cutoff only
        for legacy in LEGACY_SITE_OWNERS:
            records += [
                r
                for r in writer.runs_for(job_name(edge_id, legacy))
                if (r.finished_at or r.started_at) < LEGACY_SITE_CUTOFF
            ]
    for record in records:
        for t in record.stats.get("trials", []):
            found.add(
                (t.get("edge_variant") or MAIN, t["variant"], t["config_hash"], int(t["horizon"]))
            )
    return found


def stored_outcome_sessions(reader: StoreReader) -> list[date]:
    """The start sessions with stored outcomes, ascending: the range an evaluation covers by
    default (empty: none stored). The one place outside the harness that asks, so the outcomes
    stay quarantined (ADR 0053)."""
    return stored_sessions(reader)


def evaluate_edge(
    reader: StoreReader,
    writer: ResultWriter,
    configs: ConfigStore,
    user: UserContext,
    edge: Edge,
    start: date,
    end: date,
    as_of: datetime,
    iv_field: str = IMPLIED_VOL_FIELD,
    split_from: date | None = None,
    random_draws: int = DEFAULT_DRAWS,
    full: bool = False,
) -> EdgeEvaluation:
    """``edge`` and its ``[[variants]]`` over the decision sessions in ``start..end`` for every
    horizon, its screeners and baselines, with outcomes known by ``as_of``. ``iv_field``: the
    one implied-vol field of the run (an outcome that reads one; its source and licence are
    recorded); ``split_from``: the run's own split over the edge's;
    ``random_draws``: random picks drawn per out-of-sample session (``random_picks.py``);
    ``full``: compute every leg, reusing none of the stored ones (``legs/reuse.py``). Raises
    ``ConfigurationError`` for an event class with no declared field and
    ``MissingDataError`` when no outcome is stored for a horizon."""
    variants = _variants(configs, user, edge)
    split, exploratory = effective_split(split_from, edge)
    label = site_regime(configs.load).label  # the site's, not a user's
    session = SessionReads(reader, label)
    days = sessions_between(start, end)
    scopes = _scopes(configs, user, edge, iv_field)
    licences: dict[str, str | None] = {}
    for scope in scopes:
        if scope.iv_field in MIXED_SOURCE_IV:
            raise ConfigurationError(
                f"iv_field {scope.iv_field!r} mixes sources: name one vendor's field"
            )
        licences[scope.key] = (
            _licence(configs, user, scope.iv_field) if needs_implied_vol(scope.edge) else None
        )
    schedules = _events(reader, session, scopes, days)
    session.release()  # the eligible sets read for the events are not kept
    plans = [
        _Plan(scope, horizon, leg_blocks(scope.edge, schedules.get(scope.key), days, horizon))
        for scope in scopes
        for horizon in scope.edge.outcome.horizon_sessions
    ]
    hashed = run_hash(edge, variants, start, end, as_of, iv_field, split, random_draws)
    spec = _RandomSpec(
        split,
        random_draws,
        expression_hash(catalogue(configs, user.user_id)),
        user.user_id,
        edge.id,
    )
    stored = read_legs(reader, user.user_id, edge.id, start, end)
    earnings = any(p.scope.edge.event_class == "earnings_expected" for p in plans)  # a diagnostic
    needs = _needs(plans, variants, schedules, spec)
    stamps = partial(_outcome_stamps, reader, as_of)
    reuse = plan_reuse(
        reader, stored, needs, as_of, stamps, "requested" if full or earnings else None
    )
    stats = _measure(reader, session, plans, variants, schedules, as_of, spec, reuse)
    results: list[VariantResult] = []
    randoms: list[RandomPicks] = []
    reports = None  # the real report dates, read once and only for an earnings_expected edge
    starts: dict[int, int] = {}
    unclosed: dict[int, int] = {}
    for plan in plans:
        scope, horizon = plan.scope, plan.horizon
        needs_iv = needs_implied_vol(scope.edge)
        closed = stats.closed[horizon]
        starts.setdefault(horizon, len(plan.blocks))  # the edge's own count, then its variants'
        unclosed.setdefault(
            horizon, sum(all(leg.entry not in closed for leg in b) for b in plan.blocks)
        )
        diagnostic = None
        if scope.edge.event_class == "earnings_expected":
            reports = reports_after(reader, as_of) if reports is None else reports
            diagnostic = containment(
                [
                    (i, leg.decision, leg.entry)
                    for b in plan.blocks
                    for leg in b
                    if leg.entry in closed
                    for i in sorted(schedules[scope.key].names[leg.decision])
                    if i in stats.stored[horizon, leg.entry]  # measured: has an entry bar
                ],
                horizon,
                reports,
            )
        for variant in variants:
            legs = stats.randoms.get((plan.key, variant.id), {})
            pooled = [
                pool_random([legs[leg.decision] for leg in block if leg.decision in legs])
                for block in plan.blocks
                if _drawn(block, legs, closed)
            ]
            if pooled:
                randoms.append(
                    RandomPicks(
                        scope.key,
                        horizon,
                        variant.id,
                        _trial_hash(scope, variant),
                        random_measures(pooled),
                    )
                )
            found = stats.legs.get((plan.key, variant.id), {})
            block_stats = tuple(
                pool_stats([found[leg.decision] for leg in block if leg.entry in closed])
                for block in plan.blocks
                if any(leg.entry in closed for leg in block)
            )
            measures = tuple(
                slice_measures(
                    block_stats,
                    edge_slices(block_stats, split, exploratory),
                    variant.config.config.impl == MODEL_IMPL,
                    edge.frozen_from,
                )
            )
            results.append(
                VariantResult(
                    variant.id,
                    variant.role,
                    _trial_hash(scope, variant),
                    horizon,
                    block_stats,
                    measures,
                    edge_variant=scope.key,
                    iv_source=scope.iv_field if needs_iv else None,
                    licence=licences[scope.key],
                    report_containment=diagnostic,
                    lost_sessions=dict(
                        Counter(stats.lost.get((plan.key, variant.id), {}).values())
                    ),
                )
            )
    unknown: dict[str, int] = {}
    for events in schedules.values():
        for reason, n in events.unknown_total().items():
            unknown[reason] = unknown.get(reason, 0) + n
    tried = {(r.edge_variant, r.variant, r.config_hash, r.horizon) for r in results}
    trials = len(tried | _prior_trials(writer, edge.id, user.user_id))
    snapshot = min(session.snapshots(), default=None)
    return EdgeEvaluation(
        edge_id=edge.id,
        run_hash=hashed,
        user_id=user.user_id,
        benchmark=edge.outcome.benchmark,
        start=start,
        end=end,
        as_of=as_of,
        snapshot=snapshot,
        results=tuple(deflate(results, trials)),
        trials=trials,
        start_sessions=starts,
        unclosed_sessions=unclosed,
        event_unknown=unknown,
        split_from=split,
        exploratory=exploratory,
        historical=session.caveat(),
        random_picks=tuple(randoms),
        leg_rows=_leg_rows(stats, session, user.user_id, edge.id, stored, reuse, needs),
        mode=reuse.mode,
        legs_reused=len(reuse.reused),
        legs_computed=len(stats.rows),
        legs_invalidated=dict(reuse.invalidated),
    )


def _leg_rows(
    stats: "_Measured",
    session: SessionReads,
    user_id: str,
    edge_id: str,
    stored: StoredLegs,
    reuse: Reuse,
    needs: Sequence[Need],
) -> tuple[Mapping[str, Any], ...]:
    """The legs measured, the reads log of each decision session that has one, the outcome reads
    and the tombstones of the stored legs not carried, as ``results/edge_legs`` rows (a session
    reused whole is not rewritten)."""
    held = {row["session_date"] for row in stats.rows}
    reads = [
        encode_reads(session.day_reads(d), user_id, edge_id) for d in session.attributed_days()
    ]
    outcomes = [encode_outcome(o, user_id, edge_id) for o in stats.outcome_reads.values()]
    gone = tombstones(stored, reuse, stats.rows, needs, held, user_id, edge_id)
    return (*stats.rows, *(r for r in reads if r["session_date"] in held), *outcomes, *gone)


def _outcome_stamps(
    reader: StoreReader, as_of: datetime, entries: Collection[date]
) -> tuple[dict[tuple[date, int], datetime], dict[date, int]]:
    """What reuse asks of the outcome partitions of ``entries``: per (S, horizon) the latest
    ``knowledge_ts`` known by ``as_of`` and per S the commit sequence (the harness is the one
    reader of outcomes)."""
    return outcome_known(reader, entries, as_of), outcome_seqs(reader, entries)


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
    not. ``user_id`` and ``edge_id`` name the rows the legs are stored as."""

    split: date | None
    draws: int
    expr_hash: str
    user_id: str
    edge_id: str
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
                stat = _stat(p.scope, session, variant, leg, p.horizon, rows, names)
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


def iv_field_of(edge: Edge, run_field: str = IMPLIED_VOL_FIELD) -> str:
    """The implied-vol field an edge's outcome reads: its own ``iv_field``, else the run's."""
    return edge.outcome.iv_field or run_field


def _scopes(configs: ConfigStore, user: UserContext, edge: Edge, iv_field: str) -> list[_Scope]:
    """The edge itself (``main``), then each of its ``[[variants]]`` with its overrides. Each
    reads one implied-vol field: its outcome's ``iv_field``, else the run's."""
    scopes = [_Scope(MAIN, edge, edge_universe(configs, user, edge), iv_field_of(edge, iv_field))]
    for v in edge.variants:
        base, picks = v.base or edge.base, v.picks or edge.picks
        applied = replace(
            edge, outcome=v.outcome, universe=v.universe, base=base, picks=picks, variants=()
        )
        field_name = v.outcome.iv_field or iv_field
        marks = (f"base={base}", f"picks={picks}") if v.base or v.picks else ()
        scopes.append(
            _Scope(v.id, applied, edge_universe(configs, user, applied), field_name, marks)
        )
    return scopes


def _events(
    reader: StoreReader, session: SessionReads, scopes: Sequence[_Scope], days: Sequence[date]
) -> dict[str, EventSchedule]:
    """The event names by decision session of each scope with an event schedule (by scope key;
    the others are absent). Scopes with the same event class and offset share one read of the
    event fields."""
    groups: dict[tuple[str, int], list[_Scope]] = {}
    for scope in scopes:
        if scope.edge.event_class is not None:
            key = (scope.edge.event_class, scope.edge.outcome.start_offset_sessions)
            groups.setdefault(key, []).append(scope)
    found: dict[str, EventSchedule] = {}
    for (cls, offset), members in groups.items():
        found.update(
            read_events_for(
                reader,
                cls,
                offset,
                days,
                {m.key: partial(session.eligible, m.universe) for m in members},
            )
        )
    return found


def _licence(configs: ConfigStore, user: UserContext, iv_field: str) -> str:
    """The catalogue licence of ``iv_field`` (a stored rollup column or an expression feature)."""
    found = catalogue(configs, user.user_id).feature(iv_field)
    if found is None:
        raise ConfigurationError(f"iv_field {iv_field!r} is not a catalogue feature")
    return str(found.licence)


def _day(value: Any) -> date:
    return pd.Timestamp(value).date()
