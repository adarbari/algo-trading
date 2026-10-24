"""``cohort_percentile``: the golden cases (ties, unknown values, no cohort, the member floor)."""

import numpy as np
import pytest

from algotrade.quant.cross_section import cohort_percentile

NAN = np.nan


def test_ties_share_their_average_rank() -> None:
    out = cohort_percentile(np.array([1.0, 2.0, 2.0, 4.0]), np.zeros(4, dtype=int), 3)
    assert out.tolist() == [0.0, 0.5, 0.5, 1.0]


def test_cohort_below_the_floor_is_all_nan_and_unknowns_do_not_count() -> None:
    values, codes = np.array([10.0, NAN, 30.0]), np.zeros(3, dtype=int)
    assert np.isnan(cohort_percentile(values, codes, 3)).all()  # 2 known < 3
    out = cohort_percentile(values, codes, 2)
    assert out[0] == 0.0 and np.isnan(out[1]) and out[2] == 1.0


def test_no_cohort_is_nan() -> None:
    out = cohort_percentile(np.array([5.0, 1.0, 2.0]), np.array([-1, 0, 0]), 2)
    assert np.isnan(out[0]) and out[1:].tolist() == [0.0, 1.0]


def test_cohorts_rank_separately() -> None:
    values = np.array([1.0, 100.0, 2.0, 200.0])
    out = cohort_percentile(values, np.array([0, 1, 0, 1]), 2)
    assert out.tolist() == [0.0, 0.0, 1.0, 1.0]


def test_a_single_known_value_never_ranks_even_at_floor_one() -> None:
    assert np.isnan(cohort_percentile(np.array([3.0]), np.array([0]), 1)).all()


def test_shape_mismatch_is_an_error() -> None:
    with pytest.raises(ValueError, match="one shape"):
        cohort_percentile(np.zeros(3), np.zeros(2, dtype=int), 2)
