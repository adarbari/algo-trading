"""``quant.discovery_statistics``: sign stability, rank correlation and its clusters, the
within-stratum permutation and the count against the null."""

import numpy as np
import pytest

from algotrade.quant import discovery_statistics as ds


def test_sign_stability_needs_enough_blocks_and_both_halves() -> None:
    """Five of six blocks with one sign and both halves agreeing is stable; the same count with
    the second half's mean on the other side is not. Catches: counting blocks without the halves."""
    late = [False, False, False, True, True, True]
    ok = ds.sign_stability([0.4, 0.3, -0.1, 0.5, 0.2, 0.6], late, 5)
    assert (ok.sign, ok.agreeing, ok.blocks, ok.halves_agree, ok.stable) == (1, 5, 6, True, True)
    split = ds.sign_stability([0.9, 0.9, 0.9, 0.1, -0.1, 0.2], late, 4)  # 5 positive blocks
    assert split.agreeing == 5 and split.halves_agree and split.stable
    flipped = ds.sign_stability([0.9, 0.9, 0.9, -0.1, -0.2, 0.1], late, 3)  # late mean < 0
    assert flipped.agreeing >= 3 and not flipped.halves_agree and not flipped.stable


def test_sign_stability_ignores_missing_blocks_and_zero_effects() -> None:
    """A block with no effect is not counted; a zero agrees with neither sign; a tie has no sign.
    Catches: a None or 0.0 block read as support."""
    got = ds.sign_stability([None, 0.0, 0.2, 0.3, None, 0.1], [False] * 3 + [True] * 3, 2)
    assert (got.blocks, got.agreeing, got.sign) == (4, 3, 1)
    tie = ds.sign_stability([0.2, -0.2], [False, True], 1)
    assert tie.sign == 0 and not tie.stable


def test_rank_columns_average_ties_and_keep_nan() -> None:
    """Ranks are 1-based, ties share the mean rank, NaN stays NaN. Catches: ordinal ranks on
    ties (which would make a constant look informative)."""
    ranked = ds.rank_columns(np.array([[3.0, 1.0], [1.0, 1.0], [3.0, np.nan], [2.0, 5.0]]))
    assert ranked[:, 0].tolist() == [3.5, 1.0, 3.5, 2.0]
    assert ranked[0, 1] == 1.5 and ranked[1, 1] == 1.5 and np.isnan(ranked[2, 1])


def test_rank_correlation_is_spearman_over_common_rows() -> None:
    """A monotone transform correlates 1, a reversal -1, an unrelated column near 0, and a column
    with under three common rows is undefined. Catches: correlating values (not ranks)."""
    rng = np.random.default_rng(0)
    a = rng.normal(size=200)
    m = np.column_stack([a, np.exp(a), -a, rng.normal(size=200)])
    m[3:, 3] = np.nan  # the last column shares only three rows
    corr = ds.rank_correlation(ds.rank_columns(m))
    assert corr[0, 1] == pytest.approx(1.0) and corr[0, 2] == pytest.approx(-1.0)
    assert corr[0, 0] == pytest.approx(1.0) and np.isfinite(corr[0, 3])
    sparse = ds.rank_correlation(ds.rank_columns(np.array([[1.0, 1.0], [2.0, np.nan]] * 2)))
    assert np.isnan(sparse[0, 1])


def test_clusters_link_by_absolute_correlation_and_chain() -> None:
    """A reversed feature is the same tell; a chain of links is one cluster; a column with an
    undefined correlation links nothing. Catches: sign-blind clustering splitting a tell in two."""
    nan = np.nan
    corr = np.array(
        [
            [1.0, -0.9, 0.0, 0.0, nan],
            [-0.9, 1.0, 0.8, 0.0, nan],
            [0.0, 0.8, 1.0, 0.0, nan],
            [0.0, 0.0, 0.0, 1.0, nan],
            [nan, nan, nan, nan, nan],
        ]
    )
    assert ds.correlated_clusters(corr, [0, 1, 2, 3, 4], 0.7) == [(0, 1, 2), (3,), (4,)]
    assert ds.correlated_clusters(corr, [3, 0], 0.7) == [(0,), (3,)]  # only the members


def test_permute_within_keeps_each_strata_count_and_is_seeded() -> None:
    """Every stratum keeps its number of winners; the same seed gives the same shuffle; labels
    never cross strata. Catches: a shuffle across strata (which would break the matching)."""
    labels = np.array([True, False, False, True, True, False, False, False])
    strata = ["a", "a", "a", "a", "b", "b", "b", "b"]
    one = ds.permute_within(labels, strata, np.random.default_rng(1))
    again = ds.permute_within(labels, strata, np.random.default_rng(1))
    assert one.tolist() == again.tolist()
    assert one[:4].sum() == 2 and one[4:].sum() == 1
    moved = [
        ds.permute_within(labels, strata, np.random.default_rng(k)).tolist() for k in range(20)
    ]
    assert any(m != labels.tolist() for m in moved)


def test_exceeds_percentile() -> None:
    """The observed count must be above the null's percentile; an empty null proves nothing.
    Catches: >= instead of > (a count equal to the null's 95th percentile is not beating it)."""
    assert ds.exceeds_percentile(3, [0, 0, 1, 2], 95)
    assert not ds.exceeds_percentile(2, [0, 0, 1, 2], 100)
    assert not ds.exceeds_percentile(9, [], 95)
