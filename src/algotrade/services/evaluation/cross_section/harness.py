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
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime
from functools import partial
from typing import Any

import numpy as np

from algotrade.config.edges.document import (
    MAIN,
    Edge,
    Outcome,
)
from algotrade.config.edges.identity import LONG, LONG_SHORT
from algotrade.config.edges.named import DELTA_EQUIVALENT, TIME_SERIES
from algotrade.config.edges.portfolio import PORTFOLIO_KIND
from algotrade.config.edges.positions.chain import CHAIN_KIND
from algotrade.config.edges.positions.spec import exits_digest
from algotrade.config.edges.positions.templates import load_templates
from algotrade.config.edges.verdict import OPTION_LEVELS
from algotrade.config.site.settings import load_verdict
from algotrade.config.strategy.regime import site_regime
from algotrade.config.strategy.schema import MODEL_IMPL
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.data.outcomes import GrainReads, stored_sessions
from algotrade.services.evaluation.cross_section.baselines.variant import (
    Variant,
    _Scope,
    grain_of,
    split_keys,
    variant_scope,
)
from algotrade.services.evaluation.cross_section.detail.gating import (
    gate_domains,
    open_blocks,
    pooled_blocks,
    tagged,
    turned,
    variant_gates,
)
from algotrade.services.evaluation.cross_section.detail.licences import (
    trial_licences,
)
from algotrade.services.evaluation.cross_section.detail.windows import (
    counts_wins,
    plan_exits,
    projection_count,
    series_facts,
    unit_of,
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
    SCREENER,
    CostGrid,
    SessionStat,
    SliceMeasure,
    TailSpec,
    cost_measures,
    deflate,
    edge_slices,
    slice_measures,
)
from algotrade.services.evaluation.cross_section.measuring import (
    _beside,
    _drawn,
    _measure,
    _Measured,
    _needs,
    _Plan,
    _RandomSpec,
    _reads,
    _trial_hash,
    both_seqs,
)
from algotrade.services.evaluation.cross_section.random_picks import (
    DEFAULT_DRAWS,
    SECTOR_RANDOM,
    RandomStat,
    pool_random,
    random_measures,
)
from algotrade.services.evaluation.cross_section.reads.entry import check_entries, check_entry
from algotrade.services.evaluation.cross_section.reads.screens import ScreenCache
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.reporting.report_containment import (
    containment,
    reports_after,
)
from algotrade.services.evaluation.cross_section.reporting.turnover import (
    apply_hold_bands,
    apply_rebalances,
)
from algotrade.services.evaluation.cross_section.run.evaluation import (
    EdgeEvaluation,
    LegDetail,
    RandomPicks,
    VariantResult,
)
from algotrade.services.evaluation.cross_section.run.identity import (
    effective_split,
    prior_trials,
    run_hash,
)
from algotrade.services.evaluation.cross_section.run.scopes import (
    MIXED_SOURCE_IV,
    edge_scopes,
    edge_variants,
    event_schedules,
    iv_licence,
)
from algotrade.services.evaluation.cross_section.sessions import (
    Leg,
    leg_blocks,
)
from algotrade.services.evaluation.evidence.contract import capital_basis_of
from algotrade.services.evaluation.evidence.measures import BOOTSTRAP_SEED_VERSION
from algotrade.services.evaluation.time_series.evaluate import evaluate_time_series
from algotrade.services.evaluation.time_series.measures import deflate_trial, pbo_among
from algotrade.services.evaluation.time_series.sleeve import evaluate_sleeve, sleeve_outcomes
from algotrade.services.features import catalogue
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.tables.result_writer import ResultWriter


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
    "out_of_window"`` or ``"delta_equivalent"`` is measured by ``time_series/``
    (``_time_series``)."""
    if edge.base in TIME_SERIES:
        return _time_series(
            reader, writer, configs, user, edge, start, end, as_of, split_from, random_draws
        )
    variants = edge_variants(configs, user, edge)
    split, exploratory = effective_split(split_from, edge)
    label = site_regime(configs.load).label  # the site's, not a user's
    session = SessionReads(reader, label, screens, user.user_id, gate_domains(configs, edge))
    days = sessions_between(start, end)
    verdict = load_verdict(configs)
    scopes = edge_scopes(configs, user, edge, iv_field, verdict.borrow_bps_annual)
    licences: dict[str, str | None] = {}
    for scope in scopes:
        if scope.iv_field in MIXED_SOURCE_IV:
            raise ConfigurationError(
                f"iv_field {scope.iv_field!r} mixes sources: name one vendor's field"
            )
        licences[scope.key] = (
            iv_licence(configs, user, scope.iv_field) if needs_implied_vol(scope.edge) else None
        )
    schedules = event_schedules(reader, session, scopes, days)
    session.release()  # the eligible sets read for the events are not kept
    plans = [
        _Plan(scope, horizon, leg_blocks(scope.edge, schedules.get(scope.key), days, horizon))
        for scope in scopes
        for horizon in scope.edge.outcome.horizon_sessions
    ]
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
        verdict.option_costs,  # an option_pnl leg's cost levels and commission (its key only)
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
            _reads(plans),
            residual_plans(plans),
            _beside(plans, variants),  # a baseline the setup cannot be valued as fails here
        ),
        # an entry condition is refused here (G9-M3, G9-M4) or its legs are never reused
        check_entries(
            reader,
            [c.edge for c in scopes],
            features,
            start,
            end,
            as_of,
            full or split_keys(plans),
        ),
    )
    stats = _measure(reader, session, plans, variants, schedules, as_of, spec, reuse)
    results, randoms, projected = [], [], projection_count(load_verdict(configs))  # (0064)
    # ``projected``: the decision sessions whose exits are stored, read once per run
    reports = None  # the real report dates, read once and only for an earnings_expected edge
    starts, unclosed = dict[int, int](), dict[int, int]()
    for plan in plans:
        scope, horizon = plan.scope, plan.horizon
        needs_iv = needs_implied_vol(scope.edge)
        closed = stats.plan_closed[plan.key]  # the sessions with a row of this setup's own key
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
            vscope, vclosed, vkept, vexits = _valued_as(
                plan, variant, stats, (closed, kept, exits), start, projected
            )
            legs = stats.randoms.get((plan.key, variant.id), {})
            found = tagged(stats.legs.get((plan.key, variant.id), {}), scope.edge, session)
            every, blocks_open, block_stats = pooled_blocks(scope.edge, found, vkept, vclosed)
            pooled = [
                pool_random([legs[leg.decision] for leg in block if leg.decision in legs])
                for block in open_blocks(scope.edge, plan.blocks, found)
                if _drawn(block, legs, closed)
            ]
            randoms += _random_sets(
                scope.key,
                horizon,
                variant.id,
                _trial_hash(vscope, variant),
                pooled,
                vscope.edge.outcome.result_side,
            )
            every, block_stats = turned(
                every, block_stats, partial(_turned_over, vscope.edge.outcome)
            )
            measures, costed = _slice_rows(
                every,
                split,
                exploratory,
                variant.config.config.impl == MODEL_IMPL,
                edge.frozen_from,
                CostGrid(None, (), vscope.edge.outcome.sign, OPTION_LEVELS)
                if vscope.edge.outcome.kind == CHAIN_KIND
                else CostGrid(vscope.edge.outcome.cost_bps, spec.costs, vscope.edge.outcome.sign)
                if is_return(vscope.edge)
                and vscope.edge.outcome.side != LONG_SHORT
                and vscope.edge.outcome.kind != PORTFOLIO_KIND  # a book's cost is its turnover's
                else None,  # a spread has no hit rate to cost
                verdict.capacity_adv_floor_usd,  # statistics stage, not in the leg key
                counts_wins(unit_of(vscope.edge)),
                horizon,
                TailSpec(
                    _trial_hash(
                        vscope, variant
                    ),  # config identity, never a code version (the seed)
                    verdict.tails,
                    bootstrap=variant.role == SCREENER,  # the verdict reads the screener's only
                    base=vscope.edge.outcome.sign > 0,  # an option's: its stored base_roc
                ),
            )
            results.append(
                VariantResult(
                    variant.id,
                    variant.role,
                    _trial_hash(vscope, variant),
                    horizon,
                    block_stats,
                    measures,
                    edge_variant=scope.key,
                    side=vscope.edge.outcome.result_side,
                    capital_basis=None
                    if vscope.edge.outcome.kind == PORTFOLIO_KIND
                    else capital_basis_of(vscope.edge),
                    iv_source=scope.iv_field if needs_iv else None,
                    grid=len(variant.members) or None,
                    licences=trial_licences(
                        features,
                        vscope.edge,
                        scope.universe,
                        [m.config for m in variant.members] or [variant.config],
                        licences[scope.key],
                        stats.outcome_licence,
                    ),
                    legs=_details(blocks_open, block_stats, found, vclosed)
                    if scope.key == MAIN
                    else (),
                    report_containment=diagnostic,
                    series=series_facts(
                        vscope.edge,
                        blocks_open,
                        vclosed,
                        horizon,
                        block_stats,
                        stats.lost.get((plan.key, variant.id), {}),
                        split,
                        vexits,
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
    trials = len(tried | prior_trials(writer, edge.id, user.user_id))
    snapshot = min(session.snapshots(), default=None)
    return EdgeEvaluation(
        edge_id=edge.id,
        run_hash=hashed,
        screener_hashes={v.id: v.hash for v in variants if v.role != BASELINE},
        exits_digest=exits_digest(edge.outcome.position),
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
    """A time-series edge (ADR 0073) or named option sleeve (ADR 0088) as an ``EdgeEvaluation``:
    one trial per named instrument (``variant`` its symbol, ``horizon`` the window's length or the
    hold; a sleeve's per edge variant and grid point too), its slices and random window sets stored
    as the rows the verdict reads; no per-session series, legs or ledger (no screen to replay)."""
    split, exploratory = effective_split(split_from, edge)
    domains, features = gate_domains(configs, edge), catalogue(configs, user.user_id)
    check_entry(reader, edge, features, start, end, as_of)  # G9-M3, G9-M4 (a sleeve: each trial)
    session = SessionReads(reader, site_regime(configs.load).label, domains=domains)
    gate = None if edge.gate is None else partial(session.gate, edge.gate)
    gates, gate_keys = variant_gates(edge, session)
    run = (
        evaluate_sleeve(reader, edge, sleeve_outcomes(edge, load_templates(configs)), start, end,
                        as_of, session.label, split, exploratory, gate,
                        load_verdict(configs).option_costs, gates, gate_keys, domains, features)
        if edge.base == DELTA_EQUIVALENT
        else evaluate_time_series(
            reader, edge, start, end, as_of, session.label, split, exploratory, random_draws, gate,
            domains,
        )
    )  # fmt: skip
    keys = {
        r.identity: hashlib.sha256(f"{r.identity}|{HARNESS_VERSION}".encode()).hexdigest()
        for r in run.results
    }
    tried = {(r.edge_variant, r.symbol, keys[r.identity], r.horizon) for r in run.results}
    trials = len(tried | prior_trials(writer, edge.id, user.user_id))
    pbo = pbo_among({r.identity: dict(r.paired) for r in run.results if r.paired})
    sharpes = [r.measures[0].sharpe for r in run.results if r.measures[0].sharpe is not None]
    spread = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else None  # as ``deflate`` reads it
    results = [
        VariantResult(
            r.symbol, SCREENER, keys[r.identity], r.horizon, (),
            (
                deflate_trial(r.measures[0], [v for _, v in r.paired], trials, pbo, spread),
                *r.measures[1:],
            ),
            edge_variant=r.edge_variant, lost_sessions=r.lost, timing=r.timing or None,
            book=r.book or None,
        )
        for r in run.results
    ]  # fmt: skip
    randoms = tuple(
        RandomPicks(MAIN, run.horizon, r.symbol, keys[r.identity], r.randoms)
        for r in run.results
        if r.randoms
    )
    return EdgeEvaluation(
        edge_id=edge.id,
        run_hash=run_hash(edge, [], start, end, as_of, split_from=split, random_draws=random_draws),
        exits_digest=exits_digest(edge.outcome.position),
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


def _valued_as(
    plan: _Plan,
    variant: Variant,
    stats: _Measured,
    own: tuple[Collection[date], Any, Any],
    start: date,
    projected: int,
) -> tuple[_Scope, Collection[date], Any, Any]:
    """The scope ``variant`` is valued in (a position baseline's is the template's, on its own
    grain) with the closed sessions, measured blocks and projected exits of that grain; ``own``
    are the plan's."""
    scope = variant_scope(plan.scope, variant)
    if grain_of(scope) == grain_of(plan.scope):
        return scope, *own
    found = stats.legs.get((plan.key, variant.id), {})  # only the sessions it holds a leg for
    held = {leg.entry for block in plan.blocks for leg in block if leg.decision in found}
    closed = stats.closed_other[plan.horizon] & held
    kept, exits = plan_exits(scope.edge, plan.blocks, closed, plan.horizon, start, projected)
    return scope, closed, kept, exits


def _outcome_stamps(
    reader: StoreReader,
    as_of: datetime,
    names_for: Collection[int],
    reads: GrainReads,
    residuals: bool,
    cross: GrainReads | None,
    entries: Collection[date],
) -> tuple[
    dict[tuple[date, int], datetime], dict[tuple[date, int], frozenset[str]], dict[date, int]
]:
    """What reuse asks of the outcome partitions of ``entries``: per (S, horizon) the latest
    ``knowledge_ts`` known by ``as_of`` with the names of those rows, and per S the commit
    sequence (the harness is the one reader of outcomes)."""
    known, names = reads.stamps(reader, entries, as_of, names_for, residuals)  # the plans' grain
    seqs = reads.seqs(reader, entries, residuals)
    return known, names, both_seqs(reader, entries, seqs, cross)


def residual_plans(plans: Sequence[_Plan]) -> bool:
    """Whether any plan measures a residual return: the stamps then cover the residual
    partitions too (a backfill of them re-measures the legs that held ``NO_RESIDUAL_ROW``)."""
    return any(needs_residual(p.scope.edge) for p in plans)


def _earnings_horizons(plans: Sequence[_Plan]) -> frozenset[int]:
    """The horizons of the plans whose report diagnostic needs the names with an outcome row
    (``earnings_expected``): the only ones whose names an incremental run reads."""
    return frozenset(p.horizon for p in plans if p.scope.edge.event_class == "earnings_expected")
