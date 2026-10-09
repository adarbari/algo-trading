"""The tells and the gate (ED6 winners study, definitions 3 and 4): pure over the session frames.

Per (feature, grid session) the effect is Hedges' g of the winners over the controls
(``edge_statistics.standardised_effect``); UNKNOWN values are dropped and counted. A feature counts
at S only when both groups have at least ``min_coverage`` of it stored and the two coverages differ
by less than ``max_coverage_gap`` (otherwise missingness itself is the signal, and it is
refused). The effects are averaged per block of ``block_sessions`` (reported as "blocks", not
independent sessions: neighbouring blocks' windows overlap), and a feature's sign is *stable*
when at least ``stable_blocks`` blocks share it and the mean of each half (before / from
``split_date``) has it.

A *tell* qualifies when stable with |mean g| above ``min_abs_hedges_g``. Qualifying tells that
rank-correlate above ``cluster_rank_corr`` are one cluster (single linkage, so fewer clusters:
conservative). The gate passes when the clusters number at least ``min_clusters`` and beat the
``null_percentile`` of the same count over ``permutations`` seeded shuffles of the winner labels
within (session, cell): the whole procedure, coverage rules included, is repeated on each.
Proposal only: about six blocks are six observations.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from algotrade.config.edges.winners import WinnersStudySettings
from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.quant import discovery_statistics as ds
from algotrade.quant.edge_statistics import standardised_effect
from algotrade.services.evaluation.discovery.frame import (
    SessionFrame,
    first_partitions,
    session_frame,
)
from algotrade.services.evaluation.discovery.grid import first_bar_session, grid_sessions
from algotrade.services.evaluation.discovery.proposer import propose
from algotrade.services.evaluation.discovery.results import (
    BlockEffect,
    DiscoveryResult,
    Effect,
    Exclusion,
    SessionSummary,
    Tell,
)

META = ("instrument_id", "winner", "cell")
LOW_COVERAGE = "coverage below the minimum"
DIFFERENTIAL = "differential missingness"
UNDEFINED = "effect undefined"


@dataclass(frozen=True)
class _Blocks:
    """The blocks of a run (ascending) and whether each starts on or after the split date."""

    ids: tuple[int, ...]
    late: tuple[bool, ...]


def discover(
    reader: StoreReader, settings: WinnersStudySettings, features: FeatureSet
) -> DiscoveryResult:
    """Read every grid session and find the tells. ``MissingDataError`` when there is no grid
    session or one of them lacks stored rollups, outcomes or enough outcome rows."""
    grid = grid_sessions(first_bar_session(reader), settings)
    if not grid:
        raise MissingDataError("bars/1d", "the history is too short for a grid session", "")
    first = first_partitions(reader, features)
    frames = [session_frame(reader, g, settings, features, first) for g in grid]
    return find_tells(frames, settings)


def effect_at(
    field: str, session: date, values: np.ndarray, winner: np.ndarray, s: WinnersStudySettings
) -> Effect:
    """One feature at one session: ``values`` (NaN: UNKNOWN) split by the ``winner`` mask."""
    won, ctl = values[winner], values[~winner]
    wn, cn = int(np.isfinite(won).sum()), int(np.isfinite(ctl).sum())
    cov_w = wn / won.size if won.size else 0.0
    cov_c = cn / ctl.size if ctl.size else 0.0
    reason = ""
    if min(cov_w, cov_c) < s.min_coverage:
        reason = LOW_COVERAGE
    elif abs(cov_w - cov_c) >= s.max_coverage_gap:
        reason = DIFFERENTIAL
    g = None if reason else standardised_effect(won[np.isfinite(won)], ctl[np.isfinite(ctl)])
    if not reason and g is None:
        reason = UNDEFINED
    return Effect(field, session, g, wn, cn, cov_w, cov_c, not reason, reason)


def _blocks(frames: Sequence[SessionFrame], settings: WinnersStudySettings) -> _Blocks:
    first: dict[int, date] = {}
    for f in frames:
        first.setdefault(f.grid.block, f.grid.session)
    ids = tuple(sorted(first))
    return _Blocks(ids, tuple(first[b] >= settings.split_date for b in ids))


def block_means(
    effects: Sequence[Effect], blocks_of: dict[date, int]
) -> dict[tuple[str, int], tuple[float, int]]:
    """(feature, block) -> (mean g, counted sessions) over the counted effects."""
    sums: dict[tuple[str, int], list[float]] = {}
    for e in effects:
        if e.counted and e.g is not None:
            sums.setdefault((e.feature, blocks_of[e.session]), []).append(e.g)
    return {k: (float(np.mean(v)), len(v)) for k, v in sums.items()}


def _pooled(
    fields: Sequence[str],
    means: dict[tuple[str, int], tuple[float, int]],
    blocks: _Blocks,
    settings: WinnersStudySettings,
) -> dict[str, tuple[float, ds.SignStability, bool]]:
    """feature -> (mean over its blocks, sign stability, qualifies); features with no block out."""
    out: dict[str, tuple[float, ds.SignStability, bool]] = {}
    for field in fields:
        per = [means[field, b][0] if (field, b) in means else None for b in blocks.ids]
        have = [g for g in per if g is not None]
        if not have:
            continue
        stability = ds.sign_stability(per, blocks.late, settings.stable_blocks)
        mean = float(np.mean(have))
        out[field] = (mean, stability, stability.stable and abs(mean) > settings.min_abs_hedges_g)
    return out


def _qualifying_clusters(
    pooled: dict[str, tuple[float, ds.SignStability, bool]],
    index: dict[str, int],
    corr: np.ndarray,
    settings: WinnersStudySettings,
) -> list[tuple[int, ...]]:
    members = [index[f] for f, (_, _, q) in pooled.items() if q]
    return ds.correlated_clusters(corr, members, settings.cluster_rank_corr)


def _matrices(
    frames: Sequence[SessionFrame], fields: Sequence[str], counted: set[tuple[str, date]]
) -> tuple[np.ndarray, np.ndarray]:
    """The rows of every session stacked (rows x fields; a cell that did not count is NaN) and
    the winner flags."""
    parts, flags = [], []
    for f in frames:
        m = np.full((len(f.frame), len(fields)), np.nan)
        for j, field in enumerate(fields):
            if field in f.frame.columns and (field, f.grid.session) in counted:
                m[:, j] = f.frame[field].to_numpy(dtype=float)
        parts.append(m)
        flags.append(f.frame["winner"].to_numpy(dtype=bool))
    return np.vstack(parts), np.concatenate(flags)


def _frame_effects(
    f: SessionFrame, fields: Sequence[str], winner: np.ndarray, s: WinnersStudySettings
) -> list[Effect]:
    return [
        effect_at(
            field,
            f.grid.session,
            f.frame[field].to_numpy(dtype=float) if field in f.frame.columns else
            np.full(len(f.frame), np.nan),
            winner,
            s,
        )
        for field in fields
    ]  # fmt: skip


def find_tells(frames: Sequence[SessionFrame], settings: WinnersStudySettings) -> DiscoveryResult:
    """The result over ``frames`` (one per grid session, ascending)."""
    if not frames:
        raise MissingDataError("discovery", "no grid session to study", "")
    fields = sorted({c for f in frames for c in f.frame.columns if c not in META})
    index = {name: i for i, name in enumerate(fields)}
    blocks = _blocks(frames, settings)
    block_of = {f.grid.session: f.grid.block for f in frames}
    effects = [
        e
        for f in frames
        for e in _frame_effects(f, fields, f.frame["winner"].to_numpy(dtype=bool), settings)
    ]
    means = block_means(effects, block_of)
    pooled = _pooled(fields, means, blocks, settings)
    counted = {(e.feature, e.session) for e in effects if e.counted}
    stacked, winner = _matrices(frames, fields, counted)
    corr = ds.rank_correlation(ds.rank_columns(stacked))
    clusters = _qualifying_clusters(pooled, index, corr, settings)
    observed = len(clusters)
    null = tuple(
        _null_count(frames, fields, blocks, block_of, index, corr, settings, k)
        for k in range(settings.permutations)
    )
    cluster_of = {fields[i]: k for k, members in enumerate(clusters) for i in members}
    return DiscoveryResult(
        settings=settings,
        seed=settings.seed,
        sessions=tuple(_summary(f) for f in frames),
        effects=tuple(effects),
        block_effects=tuple(
            BlockEffect(field, b, mean, n) for (field, b), (mean, n) in sorted(means.items())
        ),
        tells=tuple(
            Tell(
                field,
                mean,
                st.blocks,
                st.sign,
                st.agreeing,
                st.halves_agree,
                st.stable,
                q,
                cluster_of.get(field),
            )
            for field, (mean, st, q) in sorted(pooled.items())
        ),
        clusters=tuple(tuple(fields[i] for i in members) for members in clusters),
        excluded=_exclusions(frames),
        observed_clusters=observed,
        null_counts=null,
        null_threshold=float(np.percentile(null, settings.null_percentile)) if null else 0.0,
        passed=gate_passes(observed, null, settings),
        blocks=len(blocks.ids),
        proposals=propose(stacked, winner, fields),
    )


def gate_passes(observed: int, null: Sequence[int], settings: WinnersStudySettings) -> bool:
    """The gate: at least ``min_clusters`` qualifying clusters and a count above the
    ``null_percentile`` of the permutation null."""
    return observed >= settings.min_clusters and ds.exceeds_percentile(
        observed, null, settings.null_percentile
    )


def _null_count(
    frames: Sequence[SessionFrame],
    fields: Sequence[str],
    blocks: _Blocks,
    block_of: dict[date, int],
    index: dict[str, int],
    corr: np.ndarray,
    settings: WinnersStudySettings,
    permutation: int,
) -> int:
    """Qualifying clusters after shuffling the winner labels within (session, cell)."""
    effects: list[Effect] = []
    for f in frames:
        rng = np.random.default_rng([settings.seed, f.grid.session.toordinal(), permutation])
        shuffled = ds.permute_within(
            f.frame["winner"].to_numpy(dtype=bool), f.frame["cell"].tolist(), rng
        )
        effects += _frame_effects(f, fields, shuffled, settings)
    pooled = _pooled(fields, block_means(effects, block_of), blocks, settings)
    return len(_qualifying_clusters(pooled, index, corr, settings))


def _summary(f: SessionFrame) -> SessionSummary:
    won = int(f.frame["winner"].sum())
    return SessionSummary(
        session=f.grid.session,
        block=f.grid.block,
        eligible=f.labels.eligible,
        winners=won,
        controls_wanted=f.controls_wanted,
        controls_drawn=len(f.frame) - won,
        threshold=f.labels.threshold,
        missing_fraction=f.labels.missing_fraction,
    )


def _exclusions(frames: Sequence[SessionFrame]) -> tuple[Exclusion, ...]:
    count = Counter((name, why) for f in frames for name, why in f.excluded)
    return tuple(Exclusion(name, why, n) for (name, why), n in sorted(count.items()))
