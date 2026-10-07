"""``quant.rolling``: rolling mean, variance, max and min by hand, NaN until the window is
full and on any gap (never a shorter window), and trailing runs that stop at an unknown row."""

import numpy as np
import pytest

from algotrade.quant.rolling import (
    rolling_max,
    rolling_mean,
    rolling_min,
    rolling_var,
    trailing_run,
)

COL = np.array([[1.0], [2.0], [4.0], [8.0], [np.nan], [3.0], [5.0]])


def test_rolling_statistics_by_hand() -> None:
    mean = rolling_mean(COL, 2)[:, 0]
    assert np.isnan(mean[0]) and mean[1:4].tolist() == [1.5, 3.0, 6.0]
    assert np.isnan(mean[4]) and np.isnan(mean[5]) and mean[6] == 4.0  # the gap ends windows
    var = rolling_var(COL, 3)[:, 0]
    assert var[2] == pytest.approx(np.var([1, 2, 4], ddof=1)) and var[3] == pytest.approx(
        np.var([2, 4, 8], ddof=1)
    )
    assert all(np.isnan(var[i]) for i in (0, 1, 4, 5, 6))
    assert rolling_max(COL, 3)[3, 0] == 8.0 and rolling_min(COL, 3)[3, 0] == 2.0
    assert np.isnan(rolling_max(COL, 3)[6, 0])  # row 4 is in the window


def test_short_input_and_bad_windows() -> None:
    assert np.isnan(rolling_mean(COL[:2], 3)).all()
    with pytest.raises(ValueError):
        rolling_var(COL, 1)
    with pytest.raises(ValueError):
        rolling_mean(COL, 0)


def test_trailing_run_counts_back_from_the_last_row() -> None:
    holds = np.array(
        [[True, True, False, True], [True, False, True, True], [True, True, True, True]]
    )
    known = np.ones_like(holds)
    assert trailing_run(holds, known).tolist() == [3.0, 1.0, 2.0, 3.0]
    assert trailing_run(~holds, known).tolist() == [0.0, 0.0, 0.0, 0.0]
    known[1, 0] = False  # an unknown row inside the run ends it
    known[2, 3] = False  # an unknown last row: null
    out = trailing_run(holds, known)
    assert out[0] == 1.0 and np.isnan(out[3])
    with pytest.raises(ValueError):
        trailing_run(holds, known[:2])
