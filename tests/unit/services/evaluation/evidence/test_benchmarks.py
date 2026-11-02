"""A named option sleeve tracked against a Cboe strategy index (E8b): its return on collateral
plus the bill against the index's over the same window, a window with a level or bill missing
left out and counted, by hand."""

from datetime import date

import numpy as np
import pytest

from algotrade.services.evaluation.evidence.benchmarks import NO_BILL, NO_LEVEL, index_tracking

D = [date(2024, 1, d) for d in range(2, 12)]


def test_the_tracking_error_is_the_spread_of_the_window_differences() -> None:
    levels = {D[1]: 100.0, D[3]: 101.0, D[4]: 101.0, D[6]: 99.0, D[7]: 99.0, D[9]: 100.0}
    windows = [(D[0], D[1], D[3], 0.012), (D[3], D[4], D[6], -0.015), (D[6], D[7], D[9], 0.01)]
    bills = {D[0]: 0.001, D[3]: 0.001, D[6]: 0.001}
    got = index_tracking(windows, levels, bills, "PUT")
    index = [0.01, 99 / 101 - 1, 100 / 99 - 1]
    diff = np.array([0.013, -0.014, 0.011]) - np.array(index)
    assert got["tracks"] == "PUT" and got["tracked_windows"] == 3
    assert got["tracking_error"] == pytest.approx(float(np.std(diff, ddof=1)))
    assert got["tracking_mean_difference"] == pytest.approx(float(diff.mean()))
    assert got["tracking_correlation"] is not None and got["tracking_correlation"] > 0.9


def test_a_window_with_no_level_or_bill_is_counted_not_filled() -> None:
    windows = [(D[0], D[1], D[3], 0.01), (D[3], D[4], D[6], 0.01)]
    got = index_tracking(windows, {D[1]: 100.0, D[3]: 101.0}, {}, "PUT")
    assert got["tracked_windows"] == 0 and got["tracking_error"] is None
    assert (got[f"tracking_lost_{NO_LEVEL}"], got[f"tracking_lost_{NO_BILL}"]) == (1, 1)
