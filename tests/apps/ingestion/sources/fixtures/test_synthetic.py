import numpy as np
import pandas as pd

from algotrade.core.series import FIELDS, align
from algotrade_ingestion.sources.fixtures.files import bar_problems
from algotrade_ingestion.sources.fixtures.generators import (
    Regime,
    business_days,
    correlated_gbm,
    gbm_closes,
    ohlcv_from_closes,
    ou_closes,
    regime_closes,
)
from tests.factories import series_from_closes


def test_business_days_skip_weekends() -> None:
    days = business_days("2024-01-06", 3)  # Saturday
    weekdays = days.astype("datetime64[D]").astype(object)
    assert all(d.weekday() < 5 for d in weekdays)


def test_same_seed_same_path() -> None:
    a = gbm_closes(np.random.default_rng(1), 100, 50.0, 0.1, 0.2)
    b = gbm_closes(np.random.default_rng(1), 100, 50.0, 0.1, 0.2)
    np.testing.assert_array_equal(a, b)
    assert a[0] == 50.0


def test_regimes_concatenate() -> None:
    closes = regime_closes(np.random.default_rng(0), 10.0, [Regime(5, 0, 0.1), Regime(7, 0, 0.1)])
    assert len(closes) == 12


def test_ou_reverts_to_mean() -> None:
    closes = ou_closes(np.random.default_rng(2), 2000, 100.0, half_life=5, vol=0.2)
    assert abs(np.mean(closes) - 100) < 5


def test_correlated_paths_are_correlated() -> None:
    a, b = correlated_gbm(np.random.default_rng(3), 2000, (1, 1), (0, 0), (0.2, 0.2), 0.8)
    corr = np.corrcoef(np.diff(np.log(a)), np.diff(np.log(b)))[0, 1]
    assert 0.7 < corr < 0.9


def test_generated_bars_pass_validation() -> None:
    rng = np.random.default_rng(4)
    closes = gbm_closes(rng, 300, 100.0, 0.0, 0.5)
    series = ohlcv_from_closes("X", rng, business_days("2020-01-01", 300), closes)
    assert bar_problems(pd.DataFrame({f: series.field(f) for f in FIELDS})) == []


def test_align_intersects_timestamps() -> None:
    a = series_from_closes([1, 2, 3, 4], "A")
    b_full = series_from_closes([5, 6, 7, 8], "B")
    b = type(b_full)("B", b_full.timestamps[1:].copy(), *(
        b_full.field(f)[1:].copy() for f in ("open", "high", "low", "close", "volume")
    ))  # fmt: skip
    out = align({"A": a, "B": b})
    assert len(out["A"]) == len(out["B"]) == 3
    assert list(out["A"].close) == [2, 3, 4]
    assert align({}) == {}
