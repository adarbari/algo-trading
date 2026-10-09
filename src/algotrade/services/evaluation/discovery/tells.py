"""The tells and the gate (ED6 winners study, definitions 3 and 4): pure over the session frames.

Per (feature, grid session) the effect is Hedges' g of the winners over the controls
(``g_W``; ``edge_statistics.standardised_effect``), of the winners over the losers (``g_WL``) and,
for the report only, of the losers over the winners' controls (``g_L``); UNKNOWN values are
dropped and counted. A feature counts
at S only when both groups have at least ``min_coverage`` of it stored and the two coverages differ
by less than ``max_coverage_gap`` (otherwise missingness itself is the signal, and it is
refused). The effects are averaged per block of ``block_sessions`` (reported as "blocks", not
independent sessions: neighbouring blocks' windows overlap), and a feature's sign is *stable*
when at least ``stable_blocks`` blocks share it and the mean of each half (before / from
``split_date``) has it.

A *tell* qualifies when ``g_W`` is stable with |mean g| above ``min_abs_hedges_g`` **and** ``g_WL``
has the same sign as ``g_W``, is sign-stable the same way and has |mean| above
``min_abs_wl_hedges_g``: a feature that only says how much a name moves (volatility, range) is
high in the winners and in the losers alike, so it fails the second test. ``g_L`` labels such a
feature ``variance_like`` (same sign as ``g_W``, at least half its size); it never changes the gate.
Qualifying tells that rank-correlate above ``cluster_rank_corr`` are one cluster (single linkage,
so fewer clusters: conservative; the members are reported). The correlation matrix and the
proposer see the winners and controls only. The gate passes when the clusters number at least
``min_clusters`` and beat the ``null_percentile`` of the same count over ``permutations`` seeded
shuffles of the three labels (winner, control, loser) within (session, cell): the whole
procedure, coverage rules included, is repeated on each.
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

META = ("instrument_id", "winner", "loser", "cell")
CONTROL, WINNER, LOSER = 0, 1, 2  # the codes of the three labels the null shuffles
VARIANCE_SHARE = 0.5  # |g_L| at least this share of |g_W|, same sign: variance-like
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
    field: str,
    session: date,
    values: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    s: WinnersStudySettings,
) -> Effect:
    """One feature at one session: Hedges' g of the ``first`` group over the ``second`` (boolean
    masks over ``values``; NaN: UNKNOWN). The second is an explicit mask, never ``~first``: the
    losers are in the frame and are not controls."""
    won, ctl = values[first], values[second]
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


@dataclass(frozen=True)
class _Pooled:
    """A feature over the blocks: ``mean`` / ``stability`` of g_W, ``mean_wl`` / ``stability_wl``
    of g_WL, ``mean_l`` of g_L, ``qualifies`` and ``variance_like``."""

    mean: float
    stability: ds.SignStability
    mean_wl: float
    stability_wl: ds.SignStability
    mean_l: float
    qualifies: bool
    variance_like: bool


type _Means = dict[tuple[str, int], tuple[float, int]]


def _mean_or_nan(values: list[float | None]) -> float:
    have = [g for g in values if g is not None]
    return float(np.mean(have)) if have else float("nan")


def _per_block(field: str, means: _Means, blocks: _Blocks) -> list[float | None]:
    return [means[field, b][0] if (field, b) in means else None for b in blocks.ids]


def _pooled(
    fields: Sequence[str],
    means: tuple[_Means, _Means, _Means],
    blocks: _Blocks,
    settings: WinnersStudySettings,
) -> dict[str, _Pooled]:
    """feature -> its pooled effects (``means``: g_W, g_WL, g_L per (feature, block)); features
    with no g_W block are out. Qualifies: g_W stable and above the gate, g_WL of the same sign,
    stable and above its own gate."""
    out: dict[str, _Pooled] = {}
    for field in fields:
        per = _per_block(field, means[0], blocks)
        if all(g is None for g in per):
            continue
        per_wl, per_l = _per_block(field, means[1], blocks), _per_block(field, means[2], blocks)
        stability = ds.sign_stability(per, blocks.late, settings.stable_blocks)
        stability_wl = ds.sign_stability(per_wl, blocks.late, settings.stable_blocks)
        mean, mean_wl, mean_l = _mean_or_nan(per), _mean_or_nan(per_wl), _mean_or_nan(per_l)
        separates = (
            stability_wl.stable
            and stability_wl.sign == stability.sign
            and abs(mean_wl) > settings.min_abs_wl_hedges_g
        )
        qualifies = stability.stable and abs(mean) > settings.min_abs_hedges_g and separates
        like = (
            np.isfinite(mean_l)
            and mean != 0.0
            and np.sign(mean_l) == np.sign(mean)
            and abs(mean_l) >= VARIANCE_SHARE * abs(mean)
        )
        out[field] = _Pooled(mean, stability, mean_wl, stability_wl, mean_l, qualifies, bool(like))
    return out


def _qualifying_clusters(
    pooled: dict[str, _Pooled],
    index: dict[str, int],
    corr: np.ndarray,
    settings: WinnersStudySettings,
) -> list[tuple[int, ...]]:
    members = [index[f] for f, p in pooled.items() if p.qualifies]
    return ds.correlated_clusters(corr, members, settings.cluster_rank_corr)


def _matrices(
    frames: Sequence[SessionFrame], fields: Sequence[str], counted: set[tuple[str, date]]
) -> tuple[np.ndarray, np.ndarray]:
    """The rows of every session stacked (rows x fields; a cell that did not count is NaN) and
    the winner flags: the winners and controls only, never the losers (the correlation matrix and
    the proposer compare winners with their matched controls)."""
    parts, flags = [], []
    for f in frames:
        keep = ~f.frame["loser"].to_numpy(dtype=bool)
        m = np.full((int(keep.sum()), len(fields)), np.nan)
        for j, field in enumerate(fields):
            if field in f.frame.columns and (field, f.grid.session) in counted:
                m[:, j] = f.frame[field].to_numpy(dtype=float)[keep]
        parts.append(m)
        flags.append(f.frame["winner"].to_numpy(dtype=bool)[keep])
    return np.vstack(parts), np.concatenate(flags)


def _codes(f: SessionFrame) -> np.ndarray:
    """The label of each row: ``WINNER``, ``LOSER`` or ``CONTROL`` (the rest)."""
    codes = np.full(len(f.frame), CONTROL, dtype=int)
    codes[f.frame["loser"].to_numpy(dtype=bool)] = LOSER
    codes[f.frame["winner"].to_numpy(dtype=bool)] = WINNER
    return codes


def _frame_effects(
    f: SessionFrame, fields: Sequence[str], codes: np.ndarray, s: WinnersStudySettings
) -> tuple[list[Effect], list[Effect], list[Effect]]:
    """g_W (winners over controls), g_WL (winners over losers) and g_L (losers over controls) of
    every field at this session, over the rows labelled ``codes`` (the real labels or a shuffle)."""
    w, c, lo = codes == WINNER, codes == CONTROL, codes == LOSER
    out: tuple[list[Effect], list[Effect], list[Effect]] = ([], [], [])
    for field in fields:
        values = (
            f.frame[field].to_numpy(dtype=float)
            if field in f.frame.columns
            else np.full(len(f.frame), np.nan)
        )
        for into, (a, b) in zip(out, ((w, c), (w, lo), (lo, c)), strict=True):
            into.append(effect_at(field, f.grid.session, values, a, b, s))
    return out


def _all_effects(
    frames: Sequence[SessionFrame],
    fields: Sequence[str],
    codes: Sequence[np.ndarray],
    settings: WinnersStudySettings,
) -> tuple[list[Effect], list[Effect], list[Effect]]:
    out: tuple[list[Effect], list[Effect], list[Effect]] = ([], [], [])
    for f, code in zip(frames, codes, strict=True):
        for into, found in zip(out, _frame_effects(f, fields, code, settings), strict=True):
            into.extend(found)
    return out


def find_tells(frames: Sequence[SessionFrame], settings: WinnersStudySettings) -> DiscoveryResult:
    """The result over ``frames`` (one per grid session, ascending)."""
    if not frames:
        raise MissingDataError("discovery", "no grid session to study", "")
    fields = sorted({c for f in frames for c in f.frame.columns if c not in META})
    index = {name: i for i, name in enumerate(fields)}
    blocks = _blocks(frames, settings)
    block_of = {f.grid.session: f.grid.block for f in frames}
    effects, effects_wl, effects_l = _all_effects(
        frames, fields, [_codes(f) for f in frames], settings
    )
    means = block_means(effects, block_of)
    means_wl, means_l = block_means(effects_wl, block_of), block_means(effects_l, block_of)
    pooled = _pooled(fields, (means, means_wl, means_l), blocks, settings)
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
            BlockEffect(
                field,
                b,
                mean,
                n,
                means_wl.get((field, b), (float("nan"), 0))[0],
                means_l.get((field, b), (float("nan"), 0))[0],
            )
            for (field, b), (mean, n) in sorted(means.items())
        ),
        tells=tuple(
            Tell(
                field,
                p.mean,
                p.stability.blocks,
                p.stability.sign,
                p.stability.agreeing,
                p.stability.halves_agree,
                p.stability.stable,
                p.qualifies,
                cluster_of.get(field),
                p.mean_wl,
                p.mean_l,
                p.variance_like,
            )
            for field, p in sorted(pooled.items())
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
    """Qualifying clusters after shuffling the three labels (winner, control, loser) within
    (session, cell); the rows are in ascending id order, so one seed is one shuffle."""
    shuffled = []
    for f in frames:
        rng = np.random.default_rng([settings.seed, f.grid.session.toordinal(), permutation])
        shuffled.append(ds.permute_within(_codes(f), f.frame["cell"].tolist(), rng))
    effects, effects_wl, effects_l = _all_effects(frames, fields, shuffled, settings)
    means = (
        block_means(effects, block_of),
        block_means(effects_wl, block_of),
        block_means(effects_l, block_of),
    )
    pooled = _pooled(fields, means, blocks, settings)
    return len(_qualifying_clusters(pooled, index, corr, settings))


def _summary(f: SessionFrame) -> SessionSummary:
    won = int(f.frame["winner"].sum())
    lost = int(f.frame["loser"].sum())
    return SessionSummary(
        session=f.grid.session,
        block=f.grid.block,
        eligible=f.labels.eligible,
        winners=won,
        controls_wanted=f.controls_wanted,
        controls_drawn=len(f.frame) - won - lost,
        threshold=f.labels.threshold,
        missing_fraction=f.labels.missing_fraction,
        losers=lost,
        unknown_volatility=f.unknown_volatility,
    )


def _exclusions(frames: Sequence[SessionFrame]) -> tuple[Exclusion, ...]:
    count = Counter((name, why) for f in frames for name, why in f.excluded)
    return tuple(Exclusion(name, why, n) for (name, why), n in sorted(count.items()))
