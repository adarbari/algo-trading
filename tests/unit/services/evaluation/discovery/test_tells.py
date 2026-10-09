"""``tells`` and ``proposer``: the effect of a feature at a session (UNKNOWN dropped, missingness
that differs between the groups refused), the clusters the gate counts and the probit's ranking."""

from datetime import date

import numpy as np
import pytest

from algotrade.quant.edge_statistics import standardised_effect
from algotrade.services.evaluation.discovery.proposer import propose
from algotrade.services.evaluation.discovery.results import PROPOSED_BY
from algotrade.services.evaluation.discovery.tells import (
    DIFFERENTIAL,
    LOW_COVERAGE,
    effect_at,
    find_tells,
    gate_passes,
)
from tests.unit.services.evaluation.discovery.conftest import session_frame_of, settings

DAY = date(2012, 3, 1)
WINNERS, CONTROLS = 10, 30
MASK = np.array([True] * WINNERS + [False] * CONTROLS)
#  2 sessions in each of 6 blocks: three before the 2018 split, three after
DAYS = [
    date(2012 + 2 * (b % 3) + (7 if b >= 3 else 0), 3, 1 + k) for b in range(6) for k in range(2)
]
BLOCKS = [b for b in range(6) for _ in range(2)]


def signal(rng: np.random.Generator, shift: float = 1.5) -> np.ndarray:
    values = rng.normal(size=WINNERS + CONTROLS)
    values[:WINNERS] += shift
    return values


def frames(columns_of, seed: int = 0):  # type: ignore[no-untyped-def]
    """Twelve sessions; ``columns_of(rng)`` gives that session's feature columns."""
    rng = np.random.default_rng(seed)
    return [
        session_frame_of(day, block, columns_of(rng), WINNERS, CONTROLS)
        for day, block in zip(DAYS, BLOCKS, strict=True)
    ]


def independent(rng: np.random.Generator) -> dict[str, np.ndarray]:
    return {f"f{k}": signal(rng) for k in range(6)} | {"noise": rng.normal(size=40)}


def test_unknown_not_imputed() -> None:
    """A missing value is dropped from the effect and from its count, not filled with zero or the
    mean. Catches: an imputation that would change g or the rows counted."""
    rng = np.random.default_rng(1)
    values = signal(rng)
    values[[0, 20, 21]] = np.nan  # 1 of 10 winners, 2 of 30 controls: coverage 0.9 / 0.93
    got = effect_at("f", DAY, values, MASK, settings())
    finite = np.isfinite(values)
    expected = standardised_effect(values[MASK & finite], values[~MASK & finite])
    assert got.counted and got.g == pytest.approx(expected)
    assert (got.winners, got.controls) == (9, 28)
    zero_filled = np.nan_to_num(values)
    assert got.g != pytest.approx(standardised_effect(zero_filled[MASK], zero_filled[~MASK]))


def test_differential_missingness_refused() -> None:
    """A feature stored for every winner but 83% of the controls (or the reverse) is not counted
    at that session: its absence is the signal. Catches: a g computed over a feature whose
    coverage differs by 10 points or more between the groups."""
    values = signal(np.random.default_rng(2))
    values[WINNERS + 25 :] = np.nan  # controls 83% covered, winners 100%
    got = effect_at("f", DAY, values, MASK, settings())
    assert not got.counted and got.reason == DIFFERENTIAL and got.g is None
    assert (got.coverage_winners, got.coverage_controls) == (1.0, 25 / 30)
    close = signal(np.random.default_rng(2))
    close[WINNERS + 28 :] = np.nan  # 93% covered against 100%: a 7-point gap passes
    assert effect_at("f", DAY, close, MASK, settings()).counted
    gap = signal(np.random.default_rng(2))
    gap[WINNERS + 26 :] = np.nan  # 87% against 100%: 13 points
    assert effect_at("f", DAY, gap, MASK, settings()).reason == DIFFERENTIAL


def test_coverage_below_the_minimum_in_either_group_is_refused() -> None:
    """Both groups must be covered at least ``min_coverage``: equal but thin coverage is still
    refused. Catches: the gap rule alone letting two thinly covered groups through."""
    values = signal(np.random.default_rng(3))
    values[[2, 3, 4, 5]] = np.nan  # winners 60%
    values[WINNERS + 10 : WINNERS + 22] = np.nan  # controls 60%
    got = effect_at("f", DAY, values, MASK, settings())
    assert not got.counted and got.reason == LOW_COVERAGE


def test_gate_counts_clusters() -> None:
    """The gate counts rank-correlation clusters, not features: six independent stable tells are
    six clusters and pass; the same strength as six monotone copies of one is one cluster and
    fails the minimum. Catches: counting features (inflating the evidence with duplicates)."""
    s = settings(permutations=25)
    many = find_tells(frames(independent), s)
    assert many.observed_clusters == 6 and many.passed
    assert sorted(t.feature for t in many.tells if t.qualifies) == [f"f{k}" for k in range(6)]
    assert all(len(c) == 1 for c in many.clusters) and "noise" not in sum(many.clusters, ())

    def copies(rng: np.random.Generator) -> dict[str, np.ndarray]:
        base = signal(rng)
        return {f"c{k}": base * (k + 1) + 3.0 * k for k in range(6)} | {"alone": signal(rng)}

    dup = find_tells(frames(copies), s)
    assert sorted(len(c) for c in dup.clusters) == [1, 6]  # six copies: one cluster
    assert dup.observed_clusters == 2 and not dup.passed
    assert len(dup.null_counts) == 25 and dup.blocks == 6


def test_the_gate_needs_the_minimum_and_a_count_above_the_null() -> None:
    """Five clusters pass against a null of none, but not against a null that often finds five;
    four never pass. Catches: a gate on the minimum alone, or on the null alone."""
    s = settings()
    assert gate_passes(5, [0] * 200, s)
    assert not gate_passes(4, [0] * 200, s)
    assert not gate_passes(5, [5] * 200, s)
    assert not gate_passes(5, [], s)
    assert gate_passes(6, [0] * 190 + [5] * 10, s)  # 95th percentile of the null is 0


def test_a_sign_that_flips_between_the_halves_is_not_stable() -> None:
    """A feature whose winners-minus-controls effect is positive before 2018 and negative after
    never qualifies, however large; one that holds in both halves does. Catches: pooling the
    blocks into one mean and ignoring the halves."""
    s = settings(permutations=5)

    def flip(rng: np.random.Generator) -> dict[str, np.ndarray]:
        return {"steady": signal(rng), "flip": signal(rng)}

    fs = frames(flip)
    for f in fs:
        if f.grid.session >= s.split_date:
            f.frame["flip"] = -f.frame["flip"] + 2 * f.frame["flip"].mean()  # mirror the effect
    got = find_tells(fs, s)
    by = {t.feature: t for t in got.tells}
    assert by["steady"].qualifies and not by["flip"].qualifies and not by["flip"].halves_agree


def test_the_result_records_the_seed_sessions_exclusions_and_blocks() -> None:
    """The typed result carries what the job persists: the seed, one summary per session, the
    effect per (feature, session) and the exclusions with their counts. Catches: a result the
    job cannot reproduce or audit."""
    fs = frames(independent)
    fs[0] = type(fs[0])(
        fs[0].grid, fs[0].labels, fs[0].controls_wanted, fs[0].seed, fs[0].frame,
        (("rollup.x@v1.late", "input t first stored 2026-01-01, after the session"),),
    )  # fmt: skip
    got = find_tells(fs, settings(permutations=3))
    assert got.seed == settings().seed and len(got.sessions) == 12
    assert got.sessions[0].winners == WINNERS and got.sessions[0].controls_drawn == CONTROLS
    assert len(got.effects) == 12 * 7
    assert [(e.feature, e.reason, e.sessions) for e in got.excluded] == [
        ("rollup.x@v1.late", "input t first stored 2026-01-01, after the session", 1)
    ]
    assert {b.block for b in got.block_effects} == set(range(6))


def test_the_proposer_ranks_the_separating_feature_first_and_gives_no_verdict() -> None:
    """The probit ranks a feature that separates winners above noise; rows are model proposals
    with no verdict field. Catches: the proposer judging, or ranking noise first."""
    rng = np.random.default_rng(5)
    n = 400
    y = rng.random(n) < 0.3
    x = np.column_stack([rng.normal(size=n) + 1.5 * y, rng.normal(size=n), np.full(n, 7.0)])
    got = propose(x, y, ["good", "noise", "constant"])
    assert [p.feature for p in got] == ["good", "noise"]  # no variance: not ranked
    assert got[0].rank == 1 and got[0].gain > got[1].gain and got[0].coefficient > 0
    assert all(p.proposed_by == PROPOSED_BY == "model" for p in got)
    assert not hasattr(got[0], "verdict")
