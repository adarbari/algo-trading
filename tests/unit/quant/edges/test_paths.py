"""Edge paths: hand-computed curves, episodes and the rejection of a missing value."""

import math

import numpy as np
import pytest

from algotrade.quant.edges import paths


def test_cumulative_is_the_running_sum() -> None:
    assert paths.cumulative([1.0, -0.5, 2.0]).tolist() == [1.0, 0.5, 2.5]


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_missing_value_is_rejected_never_carried_as_zero(bad: float) -> None:
    for fn in (paths.cumulative, paths.underwater, paths.top_episodes):
        with pytest.raises(ValueError, match="not a zero"):
            fn([1.0, bad])


def test_underwater_starts_from_zero_and_is_never_positive() -> None:
    curve = [-1.0, 1.0, 3.0, 2.0, 2.5, 4.0]
    assert paths.underwater(curve).tolist() == [-1.0, 0.0, 0.0, -1.0, -0.5, 0.0]


def test_top_episodes_are_deepest_first_with_their_dates_as_indexes() -> None:
    curve = [1.0, 0.0, 1.5, 1.2, 0.5, 2.0, 1.9, 1.95]
    found = paths.top_episodes(curve, k=2)
    # 1.0 -> 0.0 (index 1) and back at 2; 1.5 -> 0.5 (index 4) and back at 5: equal depths,
    # the earlier first; then 2.0 -> 1.9, still open at the end of the curve
    assert found[0] == paths.Episode(peak=0, trough=1, recovered=2, depth=1.0)
    assert found[1] == paths.Episode(peak=2, trough=4, recovered=5, depth=1.0)
    assert [e.depth for e in paths.top_episodes(curve, k=3)] == [1.0, 1.0, pytest.approx(0.1)]


def test_an_open_episode_has_no_recovery_and_a_start_drop_peaks_at_the_start() -> None:
    found = paths.top_episodes([-0.4, -0.9, -0.2], k=3)
    assert found == [paths.Episode(paths.START, 1, None, 0.9)]
    assert paths.top_episodes([0.0, 1.0, 2.0]) == []


def test_annualised_vol_scales_by_windows_a_year() -> None:
    values = [0.01, -0.01, 0.03, 0.01]
    sd = float(np.std(values, ddof=1))
    assert paths.annualised_vol(values, years=2.0) == pytest.approx(sd * math.sqrt(2.0))
    assert paths.annualised_vol([0.01], years=1.0) is None
    assert paths.annualised_vol(values, years=0.0) is None


def test_excess_wins_are_wins_above_the_base_rate() -> None:
    # 3 of 5 picks won where 20% of the field did: 3 - 5 * 0.2 = 2
    assert paths.excess_wins([3], [5], [4], [20]).tolist() == [2.0]
    with pytest.raises(ValueError, match="no eligible"):
        paths.excess_wins([1], [1], [0], [0])


def test_pooled_lift_pools_the_counts_not_the_rates() -> None:
    # picks won 1/2 then 4/8 = 5 of 10; the field 10/20 then 2/20 = 12 of 40
    assert paths.pooled_lift([1, 4], [2, 8], [10, 2], [20, 20]) == pytest.approx(20.0)
    assert paths.pooled_lift([], [], [], []) is None


def test_sum_by_key_groups_and_counts() -> None:
    keys, sums, counts = paths.sum_by_key([5, 3, 5, 3, 9], [1.0, 2.0, 3.0, 4.0, 5.0])
    assert (keys, sums.tolist(), counts) == ([3, 5, 9], [6.0, 4.0, 5.0], [2, 2, 1])
