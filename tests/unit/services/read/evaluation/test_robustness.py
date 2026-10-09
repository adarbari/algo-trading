"""An edge's lift among the random-pick backtests: the share it beats, the bins and the sentence
(the same share the verdict's "Beats random picks" criterion reads), and the edge's own marker."""

import pytest

from algotrade.services.read.evaluation.robustness import (
    BINS,
    beat_share,
    draw_lifts,
    load_robustness,
)
from algotrade.services.read.evaluation.runs import EdgeRow


def draws(
    lifts: list[float], horizon: int = 20, variant: str = "main", screener: str = "scr"
) -> list[EdgeRow]:
    return [
        EdgeRow(
            edge_variant=variant, variant=f"random:{screener}", role="random",
            horizon_sessions=horizon,
            slice_kind="draw", slice_value=str(i), sessions=6, picks=30, hits=12, trials=None,
            pre_snapshot_sessions=0, hit_rate=0.4, base_rate=0.4, lift=x, mean_excess_picks=0.0,
            decile_spread=None, decile_t=None, effect_size=None, sharpe=None,
            deflated_sharpe=None, pbo=None,
        )
        for i, x in enumerate(lifts)
    ]  # fmt: skip


def test_only_the_edges_own_draws_of_the_same_holding_period_count() -> None:
    mixed = [
        *draws([1.0, 1.1]),
        *draws([9.0], horizon=5),
        *draws([9.0], variant="cheap"),
        *draws([9.0], screener="other"),
    ]
    assert draw_lifts(mixed, 20, "scr") == [1.0, 1.1]
    assert beat_share(1.05, mixed, 20, "scr") == (0.5, 2)


def test_the_share_beaten_the_bins_and_the_sentence() -> None:
    found = load_robustness(1.495, draws([1.0 + i / 100 for i in range(100)]), 20, "scr", 3)
    assert found is not None
    assert (found.lift, found.draws) == (1.495, 100)
    assert found.beats == pytest.approx(0.5)  # 1.00 .. 1.99: 50 below 1.495
    assert found.summary == "Beats 50% of 100 random backtests after 3 variants tried."
    assert len(found.bins) == BINS and sum(b.count for b in found.bins) == 100
    assert found.bins[0].start == 1.0 and found.bins[-1].end == pytest.approx(1.99)


def test_the_edges_own_lift_stays_inside_the_axis_and_one_variant_reads_singular() -> None:
    found = load_robustness(3.0, draws([1.0, 1.2, 1.4]), 20, "scr", 1)
    assert found is not None and found.beats == 1.0
    assert found.bins[-1].end == 3.0  # the axis reaches the edge's lift
    assert found.summary.endswith("random backtests after 1 variant tried.")
    one = load_robustness(3.0, draws([1.0]), 20, "scr", None)
    assert one is not None and one.summary == "Beats 100% of 1 random backtests."


def test_identical_draws_make_one_bin_and_nothing_drawn_is_none() -> None:
    same = load_robustness(1.0, draws([1.0, 1.0]), 20, "scr", None)
    assert same is not None and len(same.bins) == 1 and same.bins[0].count == 2
    assert load_robustness(1.0, [], 20, "scr", 3) is None  # a run from before the draws
    assert (
        load_robustness(None, draws([1.0]), 20, "scr", 3) is None
    )  # no lift: base rate not stored
    assert load_robustness(1.0, draws([1.0], horizon=5), 20, "scr", 3) is None
