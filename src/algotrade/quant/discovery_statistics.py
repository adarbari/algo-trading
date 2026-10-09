"""Discovery statistics: the numbers behind the ED6 winners study's tells (ADR 0053 amendment).

Pure, deterministic functions over arrays; randomness only through a ``numpy`` generator the
caller seeds. The effect size of one feature at one session is
``edge_statistics.standardised_effect`` (Hedges' g), not repeated here.

    sign_stability         a series of per-block effects agrees in sign in enough blocks and in
                           both halves of the history
    rank_columns           average ranks of each column over its finite entries
    rank_correlation       pairwise-complete correlation of column ranks (Spearman's rho)
    correlated_clusters    connected components of the features whose |rho| beats a threshold
    permute_within         labels (two or more groups) shuffled inside each stratum (the null)
    exceeds_percentile     whether an observed count beats a percentile of the null counts
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

type Array = npt.NDArray[np.float64]

MIN_PAIRS = 3  # fewer common observations: the rank correlation is undefined (NaN)


@dataclass(frozen=True)
class SignStability:
    """``sign``: the sign most blocks share (+1, -1; 0 on a tie or with no block); ``agreeing``:
    blocks with that sign; ``blocks``: blocks with an effect; ``halves_agree``: the mean effect of
    the blocks of each half has that sign, both halves having a block; ``stable``: ``agreeing`` is
    at least the minimum and ``halves_agree``."""

    sign: int
    agreeing: int
    blocks: int
    halves_agree: bool
    stable: bool


def sign_stability(
    block_effects: Sequence[float | None], late: Sequence[bool], min_blocks: int
) -> SignStability:
    """Sign stability of a feature's per-block effects (``None``: the block has none, not
    counted). ``late[i]`` says block ``i`` is in the second half (on or after the split date).
    A zero effect has no sign: it agrees with neither."""
    if len(block_effects) != len(late):
        raise ValueError("one half flag per block")
    have = [(float(g), bool(h)) for g, h in zip(block_effects, late, strict=True) if g is not None]
    positive = sum(1 for g, _ in have if g > 0)
    negative = sum(1 for g, _ in have if g < 0)
    sign = 0 if positive == negative else (1 if positive > negative else -1)
    agreeing = max(positive, negative) if sign else 0
    halves = [[g for g, h in have if h is half] for half in (False, True)]
    both = all(part for part in halves)
    halves_agree = both and sign != 0 and all(float(np.mean(p)) * sign > 0 for p in halves)
    return SignStability(
        sign, agreeing, len(have), halves_agree, agreeing >= min_blocks and halves_agree
    )


def rank_columns(matrix: npt.ArrayLike) -> Array:
    """Each column replaced by the average ranks (1-based, ties share the mean rank) of its
    finite entries; a non-finite entry stays NaN."""
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("a matrix of observations by features")
    out = np.full(m.shape, np.nan)
    for j in range(m.shape[1]):
        ok = np.isfinite(m[:, j])
        out[ok, j] = _average_ranks(m[ok, j])
    return out


def _average_ranks(values: Array) -> Array:
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    ranks = np.empty(values.size, dtype=np.float64)
    start = 0
    while start < values.size:
        stop = start
        while stop + 1 < values.size and sorted_values[stop + 1] == sorted_values[start]:
            stop += 1
        ranks[order[start : stop + 1]] = (start + stop) / 2.0 + 1.0
        start = stop + 1
    return ranks


def rank_correlation(ranked: npt.ArrayLike) -> Array:
    """Pearson correlation of the columns of ``ranked`` (from ``rank_columns``) over the rows
    where both are finite: a features x features matrix, NaN where fewer than ``MIN_PAIRS`` rows
    are common or a column is constant over them; the diagonal is 1 where defined."""
    r = np.asarray(ranked, dtype=np.float64)
    k = r.shape[1]
    out = np.full((k, k), np.nan)
    ok = np.isfinite(r)
    for i in range(k):
        for j in range(i, k):
            both = ok[:, i] & ok[:, j]
            if int(both.sum()) < MIN_PAIRS:
                continue
            a, b = r[both, i], r[both, j]
            da, db = a - a.mean(), b - b.mean()
            denom = float(np.sqrt((da * da).sum() * (db * db).sum()))
            if denom > 0.0:
                out[i, j] = out[j, i] = float((da * db).sum() / denom)
    return out


def correlated_clusters(
    corr: npt.ArrayLike, members: Sequence[int], threshold: float
) -> list[tuple[int, ...]]:
    """The ``members`` (column indexes of ``corr``) grouped into connected components of the
    relation |rho| > ``threshold`` (single linkage: a chain of correlated tells is one tell; an
    undefined rho links nothing). Members ascending inside a cluster, clusters ordered by their
    first member."""
    c = np.asarray(corr, dtype=np.float64)
    todo = sorted(set(members))
    seen: set[int] = set()
    out: list[tuple[int, ...]] = []
    for first in todo:
        if first in seen:
            continue
        group, stack = [], [first]
        seen.add(first)
        while stack:
            i = stack.pop()
            group.append(i)
            for j in todo:
                if j not in seen and abs(c[i, j]) > threshold:  # NaN > t is False
                    seen.add(j)
                    stack.append(j)
        out.append(tuple(sorted(group)))
    return out


def permute_within(
    labels: npt.ArrayLike, strata: Sequence[object], rng: np.random.Generator
) -> npt.NDArray[Any]:
    """``labels`` (booleans, or integer group codes) shuffled inside each stratum: every stratum
    keeps its count of each label. Strata are visited in sorted order of their label, so one seed
    gives one result whatever the row order of the strata's first appearance."""
    flags = np.asarray(labels)
    if flags.size != len(strata):
        raise ValueError("one stratum per label")
    out = flags.copy()
    keys = np.asarray([str(s) for s in strata])
    for key in sorted(set(keys.tolist())):
        at = np.flatnonzero(keys == key)
        out[at] = flags[at][rng.permutation(at.size)]
    return out


def exceeds_percentile(observed: float, null: Sequence[float], percentile: float) -> bool:
    """Whether ``observed`` is above the ``percentile`` (0-100) of the ``null`` draws; False
    for an empty null (nothing to beat is no evidence)."""
    if not len(null):
        return False
    return bool(observed > float(np.percentile(np.asarray(null, dtype=np.float64), percentile)))
