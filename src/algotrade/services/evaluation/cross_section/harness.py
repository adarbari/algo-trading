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

import numpy as np

from algotrade.config.edges.document import (
    LEGACY_SITE_CUTOFF,
    LEGACY_SITE_OWNERS,
    MAIN,
    PAIR_KIND,
    Edge,
    Outcome,
    job_name,
)
from algotrade.config.edges.identity import LONG, LONG_SHORT, identity_dict
from algotrade.config.edges.named import OUT_OF_WINDOW
from algotrade.config.edges.portfolio import ENSEMBLE, PORTFOLIO_KIND
from algotrade.config.site.settings import load_verdict
from algotrade.config.strategy.regime import site_regime
from algotrade.config.strategy.schema import MODEL_IMPL, Selection, parse_selection
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.outcomes import (
    chain_seqs,
    chain_stamps,
    outcome_seqs,
    outcome_stamps,
    stored_sessions,
)
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.detail.licences import (
    TrialLicences,
    trial_licences,
)
from algotrade.services.evaluation.cross_section.detail.windows import (
    SeriesFacts,
    counts_wins,
    plan_exits,
    projection_count,
    series_facts,
    unit_of,
)
from algotrade.services.evaluation.cross_section.events import EventSchedule, read_events_for
from algotrade.services.evaluation.cross_section.historical import (
    HistoricalCaveat,
)
from algotrade.services.evaluation.cross_section.hit import (
    IMPLIED_VOL_FIELD,
    is_return,
    needs_implied_vol,
    needs_residual,
)
from algotrade.services.evaluation.cross_section.legs.key import (
    HARNESS_VERSION,
    expression_hash,
)
from algotrade.services.evaluation.cross_section.legs.reuse import (
    FULL,
    Need,
    Reuse,
    plan_reuse,
    tombstones,
)
from algotrade.services.evaluation.cross_section.legs.rows import (
    StoredLegs,
    encode_outcome,
    encode_reads,
)
from algotrade.services.evaluation.cross_section.legs.store import read_legs
from algotrade.services.evaluation.cross_section.measures import (
    BASELINE,
    MEMBER,
    SCREENER,
    CostGrid,
    SessionStat,
    SliceMeasure,
    TailSpec,
    cost_measures,
    deflate,
    edge_slices,
    pool_stats,
    slice_measures,
)
from algotrade.services.evaluation.cross_section.measuring import (
    Variant,
    _chain,
    _drawn,
    _measure,
    _Measured,
    _needs,
    _Plan,
    _RandomSpec,
    _Scope,
    _trial_hash,
)
from algotrade.services.evaluation.cross_section.random_picks import (
    DEFAULT_DRAWS,
    RANDOM,
    SECTOR_RANDOM,
    SEED_VERSION,
    RandomStat,
    pool_random,
    random_measures,
)
from algotrade.services.evaluation.cross_section.reads.screens import ScreenCache
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.reporting.report_containment import (
    ReportContainment,
    containment,
    reports_after,
)
from algotrade.services.evaluation.cross_section.reporting.turnover import (
    apply_hold_bands,
    apply_rebalances,
)
from algotrade.services.evaluation.cross_section.sessions import (
    Leg,
    leg_blocks,
)
from algotrade.services.evaluation.evidence.contract import capital_basis_of
from algotrade.services.evaluation.evidence.measures import BOOTSTRAP_SEED_VERSION
from algotrade.services.evaluation.time_series.evaluate import evaluate_time_series
from algotrade.services.evaluation.time_series.measures import deflate_trial, pbo_among
from algotrade.services.features import catalogue
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.result_writer import ResultWriter

# What an edge contributes to a run's identity (``run_hash``); every other field of ``Edge`` is
# ``BOOKKEEPING`` (the user's or the server's state, prose, the site's decisions): changing one
# never changes what a run measures, so it never makes a new run (nor reseeds the random draws).
# A fitness test classifies every field: a new one fails until it is named here.
RUN_INPUTS = (
    "id", "outcome", "schedule", "universe", "top_k", "screeners", "baselines", "frozen_from",
    "site_frozen_from", "base", "picks", "variants", "scorer_features", "ensemble", "gate",
    "variant_grid", "position_baselines",
)  # fmt: skip
BOOKKEEPING = (
    "name", "thesis", "mechanism", "persistence", "sources", "quality_bar", "notes", "status",
    "rejection_reason", "evidence", "promoted", "compared", "basis_horizon", "extends", "follow",
    "audit", "owner", "published", "family", "oos_class",
    "mechanism_kind", "asset_class", "plain_reason", "verdict_profile",
)  # fmt: skip
# The one fixed implied-vol field of a run is never a field mixing sources by name or by rule.
MIXED_SOURCE_IV = ("feature.vrp_iv30",)
SELECTIONS = "selections"


@dataclass(frozen=True)
class LegDetail:
    """One leg of a measured block (leg v2, ADR 0064): its decision session D and entry session
    S, the block's measured first session (the side of the split it is on, as for the slices)
    and its statistic with every pick. What the ledger is framed from."""

    decision: date
    entry: date
    block: date
    stat: SessionStat


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
    licences: TrialLicences | None = None  # the trial's and its ledger columns' (ADR 0064)
    legs: tuple[LegDetail, ...] = ()  # the main edge variant's measured legs, for the ledger
    side: str = LONG  # the outcome's side (``edge_eval.side``; ADR 0053 amendment)
    capital_basis: str | None = None  # the trade contract's (ADR 0088); None for a book
    timing: Mapping[str, Any] | None = None  # a time-series edge: timing vs buy-and-hold Sharpe
    grid: int | None = (
        None  # an ensemble: the size of its pre-registered grid (ADR 0074); else None
    )

    @property
    def licence(self) -> str | None:
        """The trial's: the strictest of its implied-vol field, screen and universe features."""
        return None if self.licences is None else self.licences.trial

    @property
    def unit(self) -> str | None:
        """What the values measure (``series.unit``); None when no series was built."""
        return None if self.series is None else self.series.unit

    @property
    def wins(self) -> bool:
        """The trial statistics read the excess wins: the values are not returns."""
        return counts_wins(self.unit)

    lost_sessions: Mapping[str, int] = field(default_factory=dict)  # table -> decision sessions
    report_containment: ReportContainment | None = None  # earnings_expected edges: diagnostic
    series: SeriesFacts | None = None  # the windows of ``stats``, the unit, the projection (0064)
    costs: tuple[SliceMeasure, ...] = ()  # cost rows of a return outcome (ADR 0064 decision 5)


def _slice_rows(
    stats: tuple[SessionStat, ...],
    split: date | None,
    exploratory: bool,
    model: bool,
    frozen_from: date | None,
    costs: CostGrid | None,
    adv_floor: float,
    wins: bool = False,
    horizon: int = 1,
    tail: TailSpec | None = None,
) -> tuple[tuple[SliceMeasure, ...], tuple[SliceMeasure, ...]]:
    """One variant's slice rows and, for a return outcome (``costs``), its cost rows (ADR 0064
    decision 5: none for an outcome that is not a return). ``wins``: the Sharpe ratio is of the
    excess wins (``measures.trial_value``); ``horizon``: the holding period, for the overlap of
    the windows the t-ratios count; ``tail``: the evidence measures' inputs (``TailSpec``)."""
    slices = edge_slices(stats, split, exploratory)
    measures = slice_measures(stats, slices, model, frozen_from, adv_floor, wins, horizon, tail)
    costed = cost_measures(stats, slices, measures, costs) if costs is not None else []
    return tuple(measures), tuple(costed)


@dataclass(frozen=True)
class RandomPicks:
    """The random-pick backtest matched to one screener of one edge variant at one horizon:
    one measure per draw over the out-of-sample slice (``random_picks.py``)."""

    edge_variant: str
    horizon: int
    variant: str  # the screener the draws are matched to
    config_hash: str  # that screener's trial hash
    draws: tuple[SliceMeasure, ...]
    kind: str = RANDOM  # ``RANDOM`` (uniform) or ``SECTOR_RANDOM`` (matched to the picks' sectors)
    side: str = LONG


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
    # The share of an in-sample Sharpe ratio to expect lost out of sample (``verdict.toml
    # [oos_haircut]`` of the edge's ``oos_class``; None: the edge has none), for the report.
    oos_haircut: float | None = None
    # Each screener's config hash as the run resolved it (``Variant.hash``), recorded in the run
    # record's stats so the provenance line can tell a screener changed since (empty: none).
    screener_hashes: Mapping[str, str] = field(default_factory=dict)
    # The bootstrap's draws, mean block and seed version, recorded in the run record's stats
    # (the evidence measures' audit, ADR 0088 2.6); empty: no tail measures (a time-series run).
    bootstrap: Mapping[str, Any] = field(default_factory=dict)


def _random_sets(
    edge_variant: str,
    horizon: int,
    screener: str,
    trial: str,
    pooled: Sequence[RandomStat],
    side: str = LONG,
) -> list[RandomPicks]:
    """The random-pick sets matched to one screener over its pooled blocks: the uniform draws and,
    when every block holds them (leg v3), the sector-matched ones beside."""
    if not pooled:
        return []
    found = [
        RandomPicks(edge_variant, horizon, screener, trial, random_measures(pooled), side=side)
    ]
    strata = [p.stratified() for p in pooled]
    if all(x is not None for x in strata):
        drawn = random_measures([x for x in strata if x is not None])
        found.append(
            RandomPicks(edge_variant, horizon, screener, trial, drawn, SECTOR_RANDOM, side)
        )
    return found


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
        "edge": identity_dict({k: asdict(edge)[k] for k in RUN_INPUTS}),
        "iv_field": iv_field,
        "variants": [(v.id, v.hash) for v in variants],
        "range": [start, end],
        "as_of": as_of,
        "split_from": split_from,
        "random": [random_draws, SEED_VERSION],
        "version": HARNESS_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _variants(configs: ConfigStore, user: UserContext, edge: Edge) -> list[Variant]:
    """The screeners, the baselines and, for an ``[ensemble]``, the combined variant (ADR 0074):
    its grid's screeners are ``member``s (reported, never a trial nor a basis) and the ensemble
    itself the one trial, counted once whatever the grid's size."""
    found = [
        *(
            Variant(s, MEMBER if s in edge.ensemble else SCREENER, resolve_config(configs, s, user))
            for s in edge.screeners
        ),
        *(Variant(s, BASELINE, resolve_config(configs, s, user)) for s in edge.baselines),
    ]
    if edge.ensemble:
        members = tuple(v for v in found if v.role == MEMBER)
        found.append(Variant(ENSEMBLE, SCREENER, members[0].config, members))
    if not found:
        raise ConfigurationError(f"edge {edge.id}: no screeners or baselines to evaluate")
    return found


def screen_uses(configs: ConfigStore, edges: Sequence[Edge]) -> list[tuple[str, str]]:
    """The (owner, config hash) of every screener and baseline the ``edges`` score, one pair
    per use: what ``shared_screens`` counts to choose the screens worth caching for a run."""
    uses: list[tuple[str, str]] = []
    for edge in edges:
        if edge.base == OUT_OF_WINDOW:
            continue  # measured by time_series/, no screener runs
        try:
            found = _variants(configs, UserContext(edge.owner), edge)
        except ConfigurationError:
            continue  # the run of that edge reports it
        uses.extend((edge.owner, v.config.hash) for v in found if not v.members)
    return uses


def edge_universe(configs: ConfigStore, user: UserContext, edge: Edge) -> Selection:
    if isinstance(edge.universe, Selection):
        return edge.universe
    for scope in (user.user_id, "site"):
        doc = configs.load(scope, SELECTIONS, edge.universe)
        if doc is not None:
            return parse_selection(doc, f"{scope}/{SELECTIONS}/{edge.universe}")
    raise ConfigurationError(f"edge {edge.id}: unknown selection {edge.universe!r}")


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
    under ``LEGACY_SITE_OWNERS``, so the deflated Sharpe ratio still counts them. A logged
    baseline is not a trial."""
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
            if t.get("role") in (BASELINE, MEMBER):  # a comparison or a grid member, not a trial
                continue  # (no role: counted; an ensemble is one trial, whatever its grid)
            found.add(
                (t.get("edge_variant") or MAIN, t["variant"], t["config_hash"], int(t["horizon"]))
            )
    return found


def stored_outcome_sessions(reader: StoreReader) -> list[date]:
    """The start sessions with stored outcomes, ascending: the range an evaluation covers by
    default (empty: none stored). The one place outside the harness that asks, so the outcomes
    stay quarantined (ADR 0053)."""
    return stored_sessions(reader)


def _turned_over(o: Outcome, stats: tuple[SessionStat, ...]) -> tuple[SessionStat, ...]:
    """``stats`` with the net series of an outcome whose cost is its turnover's: a buy/hold band
    (entries and exits) or a rebalanced portfolio book (the weight change); any other as given."""
    if o.hold_rank is not None:
        return apply_hold_bands(stats, o.cost_bps, o.sign)
    if o.kind == PORTFOLIO_KIND:
        return apply_rebalances(stats, o.cost_bps)
    return stats


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
    screens: ScreenCache | None = None,
) -> EdgeEvaluation:
    """``edge`` and its ``[[variants]]`` over the decision sessions in ``start..end`` for every
    horizon, its screeners and baselines, with outcomes known by ``as_of``. ``iv_field``: the
    one implied-vol field of the run (an outcome that reads one; its source and licence are
    recorded); ``split_from``: the run's own split over the edge's;
    ``random_draws``: random picks drawn per out-of-sample session (``random_picks.py``);
    ``full``: compute every leg, reusing none of the stored ones (``legs/reuse.py``);
    ``screens``: the screens other edges of the run computed (``reads/screens.py``). Raises
    ``ConfigurationError`` for an event class with no declared field and
    ``MissingDataError`` when no outcome is stored for a horizon. An edge with ``base =
    "out_of_window"`` is a time-series edge, measured by ``time_series/`` (``_time_series``)."""
    if edge.base == OUT_OF_WINDOW:
        return _time_series(
            reader, writer, configs, user, edge, start, end, as_of, split_from, random_draws
        )
    variants = _variants(configs, user, edge)
    split, exploratory = effective_split(split_from, edge)
    label = site_regime(configs.load).label  # the site's, not a user's
    session = SessionReads(reader, label, screens, user.user_id)
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
    verdict = load_verdict(configs)
    hashed = run_hash(edge, variants, start, end, as_of, iv_field, split, random_draws)
    features = catalogue(configs, user.user_id)
    spec = _RandomSpec(
        split,
        random_draws,
        expression_hash(features),
        user.user_id,
        edge.id,
        verdict.cost_levels_bps,  # every leg counts hits at the site's cost grid
        verdict.capacity_adv_floor_usd,  # a short leg's liquidity floor (key of such legs only)
    )
    stored = read_legs(reader, user.user_id, edge.id, start, end)
    needs = _needs(plans, variants, schedules, spec)
    reuse = plan_reuse(
        reader,
        stored,
        needs,
        as_of,
        partial(
            _outcome_stamps,
            reader,
            as_of,
            _earnings_horizons(plans),
            _chain(plans),
            residual_plans(plans),
        ),
        "requested" if full else None,
    )
    stats = _measure(reader, session, plans, variants, schedules, as_of, spec, reuse)
    results, randoms, projected = [], [], projection_count(load_verdict(configs))  # (0064)
    # ``projected``: the decision sessions whose exits are stored, read once per run
    reports = None  # the real report dates, read once and only for an earnings_expected edge
    starts, unclosed = dict[int, int](), dict[int, int]()
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
        kept, exits = plan_exits(
            scope.edge, plan.blocks, closed, horizon, start, projected
        )  # the blocks with a closed leg (measured) and the projected exits (ADR 0064)
        for variant in variants:
            legs = stats.randoms.get((plan.key, variant.id), {})
            pooled = [
                pool_random([legs[leg.decision] for leg in block if leg.decision in legs])
                for block in plan.blocks
                if _drawn(block, legs, closed)
            ]
            randoms += _random_sets(
                scope.key,
                horizon,
                variant.id,
                _trial_hash(scope, variant),
                pooled,
                scope.edge.outcome.result_side,
            )
            found = stats.legs.get((plan.key, variant.id), {})
            block_stats = tuple(
                pool_stats([found[leg.decision] for leg in block if leg.entry in closed])
                for block in kept
            )
            block_stats = _turned_over(scope.edge.outcome, block_stats)
            measures, costed = _slice_rows(
                block_stats,
                split,
                exploratory,
                variant.config.config.impl == MODEL_IMPL,
                edge.frozen_from,
                CostGrid(scope.edge.outcome.cost_bps, spec.costs, scope.edge.outcome.sign)
                if is_return(scope.edge)
                and scope.edge.outcome.side != LONG_SHORT
                and scope.edge.outcome.kind != PORTFOLIO_KIND  # a book's cost is its turnover's
                else None,  # a spread has no hit rate to cost
                verdict.capacity_adv_floor_usd,  # statistics stage, not in the leg key
                counts_wins(unit_of(scope.edge)),
                horizon,
                TailSpec(
                    _trial_hash(scope, variant),  # config identity, never a code version (the seed)
                    verdict.tails,
                    bootstrap=variant.role == SCREENER,  # the verdict reads the screener's only
                    base=not _chain([plan]) and scope.edge.outcome.sign > 0,
                ),
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
                    side=scope.edge.outcome.result_side,
                    capital_basis=None
                    if scope.edge.outcome.kind == PORTFOLIO_KIND
                    else capital_basis_of(scope.edge),
                    iv_source=scope.iv_field if needs_iv else None,
                    grid=len(variant.members) or None,
                    licences=trial_licences(
                        features,
                        scope.edge,
                        scope.universe,
                        [m.config for m in variant.members] or [variant.config],
                        licences[scope.key],
                        stats.outcome_licence,
                    ),
                    legs=_details(kept, block_stats, found, closed) if scope.key == MAIN else (),
                    report_containment=diagnostic,
                    series=series_facts(
                        scope.edge,
                        kept,
                        closed,
                        horizon,
                        block_stats,
                        stats.lost.get((plan.key, variant.id), {}),
                        split,
                        exits,
                    ),
                    costs=costed,
                    lost_sessions=dict(
                        Counter(stats.lost.get((plan.key, variant.id), {}).values())
                    ),
                )
            )
    unknown: dict[str, int] = {}
    for events in schedules.values():
        for reason, n in events.unknown_total().items():
            unknown[reason] = unknown.get(reason, 0) + n
    # a trial is a screener: a baseline is a comparison (ADR 0064 amendment 2026-10-11)
    tried = {
        (r.edge_variant, r.variant, r.config_hash, r.horizon) for r in results if r.role == SCREENER
    }
    trials = len(tried | _prior_trials(writer, edge.id, user.user_id))
    snapshot = min(session.snapshots(), default=None)
    return EdgeEvaluation(
        edge_id=edge.id,
        run_hash=hashed,
        screener_hashes={v.id: v.hash for v in variants if v.role != BASELINE},
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
        oos_haircut=None if edge.oos_class is None else verdict.oos_haircut(edge.oos_class),
        bootstrap={
            "draws": verdict.tails.bootstrap_draws,
            "mean_block": verdict.tails.bootstrap_mean_block,
            "seed_version": BOOTSTRAP_SEED_VERSION,
        },
    )


def _time_series(
    reader: StoreReader,
    writer: ResultWriter,
    configs: ConfigStore,
    user: UserContext,
    edge: Edge,
    start: date,
    end: date,
    as_of: datetime,
    split_from: date | None,
    random_draws: int,
) -> EdgeEvaluation:
    """A time-series edge (ADR 0073) as an ``EdgeEvaluation``: one trial per named instrument
    (``variant`` its symbol, ``horizon`` the window's length), its slices and random window sets
    stored as the rows the verdict reads; no per-session series, legs or ledger (there is no
    screen to replay)."""
    split, exploratory = effective_split(split_from, edge)
    session = SessionReads(reader, site_regime(configs.load).label)
    run = evaluate_time_series(
        reader, edge, start, end, as_of, session.label, split, exploratory, random_draws
    )
    keys = {
        r.symbol: hashlib.sha256(
            f"{edge.id}|{run.window}|{r.symbol}|{HARNESS_VERSION}".encode()
        ).hexdigest()
        for r in run.results
    }
    tried = {(MAIN, r.symbol, keys[r.symbol], run.horizon) for r in run.results}
    trials = len(tried | _prior_trials(writer, edge.id, user.user_id))
    pbo = pbo_among({r.symbol: dict(r.paired) for r in run.results if r.paired})
    sharpes = [r.measures[0].sharpe for r in run.results if r.measures[0].sharpe is not None]
    spread = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else None  # as ``deflate`` reads it
    results = [
        VariantResult(
            r.symbol, SCREENER, keys[r.symbol], run.horizon, (),
            (
                deflate_trial(r.measures[0], [v for _, v in r.paired], trials, pbo, spread),
                *r.measures[1:],
            ),
            lost_sessions=r.lost, timing=r.timing,
        )
        for r in run.results
    ]  # fmt: skip
    randoms = tuple(
        RandomPicks(MAIN, run.horizon, r.symbol, keys[r.symbol], r.randoms)
        for r in run.results
        if r.randoms
    )
    return EdgeEvaluation(
        edge_id=edge.id,
        run_hash=run_hash(edge, [], start, end, as_of, split_from=split, random_draws=random_draws),
        user_id=user.user_id,
        benchmark=edge.outcome.benchmark,
        start=start,
        end=end,
        as_of=as_of,
        snapshot=None,
        results=tuple(results),
        trials=trials,
        start_sessions={run.horizon: run.scheduled},
        unclosed_sessions={run.horizon: run.unclosed},
        split_from=split,
        exploratory=exploratory,
        random_picks=randoms,
    )


def _details(
    blocks: Sequence[Sequence[Leg]],
    pooled: Sequence[SessionStat],
    found: Mapping[date, SessionStat],
    closed: Collection[date],
) -> tuple[LegDetail, ...]:
    """The closed legs of the measured blocks, each with its block's first session; a block the
    screen could not measure (``pool_stats``: coverage) has none, as it has no statistic."""
    return tuple(
        LegDetail(leg.decision, leg.entry, block_stat.session, found[leg.decision])
        for block, block_stat in zip(blocks, pooled, strict=True)
        if not block_stat.excluded_coverage
        for leg in block
        if leg.entry in closed
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
    reader: StoreReader,
    as_of: datetime,
    names_for: Collection[int],
    chain: bool,
    residuals: bool,
    entries: Collection[date],
) -> tuple[
    dict[tuple[date, int], datetime], dict[tuple[date, int], frozenset[str]], dict[date, int]
]:
    """What reuse asks of the outcome partitions of ``entries``: per (S, horizon) the latest
    ``knowledge_ts`` known by ``as_of`` with the names of those rows, and per S the commit
    sequence (the harness is the one reader of outcomes)."""
    if chain:  # an option_pnl edge reads the chain grain (EB H13)
        known, names = chain_stamps(reader, entries, as_of, names_for)
        return known, names, chain_seqs(reader, entries)
    known, names = outcome_stamps(reader, entries, as_of, names_for=names_for, residuals=residuals)
    return known, names, outcome_seqs(reader, entries, residuals)


def residual_plans(plans: Sequence[_Plan]) -> bool:
    """Whether any plan measures a residual return: the stamps then cover the residual
    partitions too (a backfill of them re-measures the legs that held ``NO_RESIDUAL_ROW``)."""
    return any(needs_residual(p.scope.edge) for p in plans)


def _earnings_horizons(plans: Sequence[_Plan]) -> frozenset[int]:
    """The horizons of the plans whose report diagnostic needs the names with an outcome row
    (``earnings_expected``): the only ones whose names an incremental run reads."""
    return frozenset(p.horizon for p in plans if p.scope.edge.event_class == "earnings_expected")


def iv_field_of(edge: Edge, run_field: str = IMPLIED_VOL_FIELD) -> str:
    """The implied-vol field an edge's outcome reads: its own ``iv_field``, else the run's."""
    return edge.outcome.iv_field or run_field


def _scopes(configs: ConfigStore, user: UserContext, edge: Edge, iv_field: str) -> list[_Scope]:
    """The edge itself (``main``), then each of its ``[[variants]]`` with its overrides. Each
    reads one implied-vol field: its outcome's ``iv_field``, else the run's."""
    borrow = load_verdict(configs).borrow_bps_annual
    edge = replace(edge, outcome=_borrowing(edge.outcome, borrow))
    scopes = [_Scope(MAIN, edge, edge_universe(configs, user, edge), iv_field_of(edge, iv_field))]
    for v in edge.variants:
        base, picks = v.base or edge.base, v.picks or edge.picks
        applied = replace(
            edge,
            outcome=_borrowing(v.outcome, borrow),
            universe=v.universe,
            base=base,
            picks=picks,
            variants=(),
        )
        field_name = v.outcome.iv_field or iv_field
        marks = (f"base={base}", f"picks={picks}") if v.base or v.picks else ()
        scopes.append(
            _Scope(v.id, applied, edge_universe(configs, user, applied), field_name, marks)
        )
    return scopes


def _borrowing(outcome: Outcome, site_default: float) -> Outcome:
    """``outcome`` with the borrow rate its short leg pays made explicit (its own, else the site's
    ``verdict.toml`` default), so the trial hash and the values see one number; a long outcome has
    no short leg and is returned as it is (a pair spread's short leg is the sibling)."""
    if outcome.borrow_bps_annual is not None or (
        outcome.side == LONG and outcome.kind != PAIR_KIND
    ):
        return outcome
    return replace(outcome, borrow_bps_annual=site_default)


def _events(
    reader: StoreReader, session: SessionReads, scopes: Sequence[_Scope], days: Sequence[date]
) -> dict[str, EventSchedule]:
    """The event names by decision session of each scope with an event schedule (by scope key;
    the others are absent). Scopes with the same event class, subtype and offset share one read of
    the event fields."""
    groups: dict[tuple[str, str | None, int], list[_Scope]] = {}
    for scope in scopes:
        if scope.edge.event_class is not None:
            key = (
                scope.edge.event_class,
                scope.edge.event_subtype,
                scope.edge.outcome.start_offset_sessions,
            )
            groups.setdefault(key, []).append(scope)
    found: dict[str, EventSchedule] = {}
    for (cls, subtype, offset), members in groups.items():
        found.update(
            read_events_for(
                reader,
                cls,
                offset,
                days,
                {m.key: partial(session.eligible, m.universe) for m in members},
                subtype,
            )
        )
    return found


def _licence(configs: ConfigStore, user: UserContext, iv_field: str) -> str:
    """The catalogue licence of ``iv_field`` (a stored rollup column or an expression feature)."""
    found = catalogue(configs, user.user_id).feature(iv_field)
    if found is None:
        raise ConfigurationError(f"iv_field {iv_field!r} is not a catalogue feature")
    return str(found.licence)
