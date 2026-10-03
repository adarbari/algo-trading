import numpy as np

from algotrade.core.views.series import PriceSeries, panel
from tests.factories import series_from_closes


def test_panel_keeps_every_timestamp_with_nan_gaps() -> None:
    a = series_from_closes([1.0, 2.0, 3.0], "A")
    b = PriceSeries("B", a.timestamps[1:].copy(), *(np.array([5.0, 6.0]) for _ in range(5)))
    out = panel({"A": a, "B": b})
    assert len(out["B"]) == 3 and np.isnan(out["B"].close[0]) and out["B"].close[2] == 6.0
    assert panel({}) == {}
