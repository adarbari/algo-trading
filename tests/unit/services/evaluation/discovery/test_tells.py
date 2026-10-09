"""``tells`` and ``proposer``: the effect of a feature at a session (UNKNOWN dropped, missingness
that differs between the groups refused), the clusters the gate counts and the probit's ranking."""

from collections import Counter
from datetime import date

import numpy as np
import pytest

from algotrade.quant import discovery_statistics as ds
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
    got = effect_at("f", DAY, values, MASK, ~MASK, settings())
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
    got = effect_at("f", DAY, values, MASK, ~MASK, settings())
    assert not got.counted and got.reason == DIFFERENTIAL and got.g is None
    assert (got.coverage_winners, got.coverage_controls) == (1.0, 25 / 30)
    close = signal(np.random.default_rng(2))
    close[WINNERS + 28 :] = np.nan  # 93% covered against 100%: a 7-point gap passes
    assert effect_at("f", DAY, close, MASK, ~MASK, settings()).counted
    gap = signal(np.random.default_rng(2))
    gap[WINNERS + 26 :] = np.nan  # 87% against 100%: 13 points
    assert effect_at("f", DAY, gap, MASK, ~MASK, settings()).reason == DIFFERENTIAL


def test_coverage_below_the_minimum_in_either_group_is_refused() -> None:
    """Both groups must be covered at least ``min_coverage``: equal but thin coverage is still
    refused. Catches: the gap rule alone letting two thinly covered groups through."""
    values = signal(np.random.default_rng(3))
    values[[2, 3, 4, 5]] = np.nan  # winners 60%
    values[WINNERS + 10 : WINNERS + 22] = np.nan  # controls 60%
    got = effect_at("f", DAY, values, MASK, ~MASK, settings())
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


def with_losers(
    values: np.ndarray, winner_shift: float, loser_shift: float, rng: np.random.Generator
) -> np.ndarray:
    """A column of winners, controls then losers: the winners and the losers sit at the shifts
    above the controls (which are standard normal)."""
    base = rng.normal(size=WINNERS + CONTROLS + 10)
    base[:WINNERS] += winner_shift
    base[WINNERS + CONTROLS :] += loser_shift
    return base


def test_variance_feature_rejected() -> None:
    """The defect of the first real run: a volatility-like feature is high in the winners and in
    the losers alike (both are the names that moved most), so it beat the controls in every block
    and passed the gate. It must be ``variance_like``, must not qualify and must not count as a
    cluster. Catches: a gate on winners against controls alone."""
    s = settings(permutations=5)

    def columns(rng: np.random.Generator) -> dict[str, np.ndarray]:
        return {
            "vol": with_losers(np.empty(0), 1.5, 1.5, rng),
            "direction": with_losers(np.empty(0), 1.5, -1.5, rng),
        }

    got = find_tells(frames(columns), s)
    by = {t.feature: t for t in got.tells}
    assert by["vol"].stable and abs(by["vol"].mean_g) > s.min_abs_hedges_g  # beats controls
    assert by["vol"].variance_like and not by["vol"].qualifies
    assert by["vol"].mean_g_l > 0.5 * by["vol"].mean_g
    assert got.clusters == (("direction",),)


def test_directional_feature_kept() -> None:
    """A feature that is high in the winners and low in the losers separates them (g_WL of the same
    sign as g_W, large and stable), is not variance-like, and qualifies; one that is high in the
    winners and about equal to the controls in the losers also qualifies, its g_L being near zero.
    Catches: the winner-loser test rejecting a real tell."""
    s = settings(permutations=5)

    def columns(rng: np.random.Generator) -> dict[str, np.ndarray]:
        return {
            "both_ways": with_losers(np.empty(0), 1.5, -1.5, rng),
            "winners_only": with_losers(np.empty(0), 1.5, 0.0, rng),
        }

    got = find_tells(frames(columns), s)
    by = {t.feature: t for t in got.tells}
    for name in ("both_ways", "winners_only"):
        assert by[name].qualifies and not by[name].variance_like, name
        assert by[name].mean_g_wl > s.min_abs_wl_hedges_g
    assert by["both_ways"].mean_g_l < 0 < by["both_ways"].mean_g


def test_controls_mask_excludes_losers() -> None:
    """Winners are compared with the controls only: a loser row is not a control, so a column that
    is wild in the losers leaves g_W unchanged, and the winner-over-control effect equals the
    one computed over the control rows alone. Catches: controls taken as ``~winner`` (losers
    folded into the controls)."""
    rng = np.random.default_rng(11)
    plain = with_losers(np.empty(0), 1.0, 0.0, rng)
    wild = plain.copy()
    wild[WINNERS + CONTROLS :] += 50.0
    n = WINNERS + CONTROLS + 10
    win = np.arange(n) < WINNERS
    lose = np.arange(n) >= WINNERS + CONTROLS
    ctl = ~win & ~lose
    one = effect_at("f", DAY, plain, win, ctl, settings())
    two = effect_at("f", DAY, wild, win, ctl, settings())
    assert one.g == two.g and one.controls == CONTROLS
    assert effect_at("f", DAY, wild, win, ~win, settings()).g != one.g  # the defect it prevents


def test_null_permutes_three_labels_deterministic() -> None:
    """The permutation null shuffles winner, control and loser together inside a (session, cell):
    every cell keeps its count of each, one seed is one shuffle and another seed another, and the
    null counts reproduce. Catches: a null that shuffles only the winner flag (leaving the
    losers fixed, so a feature separating winners from losers is never tested against chance)."""
    codes = np.array([1] * 3 + [2] * 3 + [0] * 12)
    cells = ["a", "b"] * 9
    one = ds.permute_within(codes, cells, np.random.default_rng(4))
    again = ds.permute_within(codes, cells, np.random.default_rng(4))
    assert one.tolist() == again.tolist()
    for cell in ("a", "b"):
        before = Counter(codes[[i for i, c in enumerate(cells) if c == cell]].tolist())
        after = Counter(one[[i for i, c in enumerate(cells) if c == cell]].tolist())
        assert before == after
    assert any(
        ds.permute_within(codes, cells, np.random.default_rng(k)).tolist() != one.tolist()
        for k in range(10)
    )
    s = settings(permutations=6)
    first = find_tells(frames(independent), s)
    assert first.null_counts == find_tells(frames(independent), s).null_counts


def test_proposer_sees_no_losers() -> None:
    """The correlation matrix and the probit proposer are fed the winners and controls only: wild
    values in the losers leave the proposals and the clusters unchanged. Catches: losers entering
    the probit as non-winners (they would teach it to separate extremes from the middle)."""
    s = settings(permutations=3)

    def plain(rng: np.random.Generator) -> dict[str, np.ndarray]:
        return {"x": with_losers(np.empty(0), 1.5, 0.0, rng), "y": rng.normal(size=50)}

    base = frames(plain)
    wild = frames(plain)
    for f in wild:
        f.frame.loc[f.frame["loser"], ["x", "y"]] += 40.0
    assert find_tells(base, s).proposals == find_tells(wild, s).proposals
