"""Realised-vol estimators: hand-computed small series, a GBM simulation, input errors."""

import math
import statistics

import numpy as np
import pytest

from algotrade.quant import realized_vol as rv

OPEN = np.array([100.0, 101.5, 99.0, 102.0, 103.5, 101.0])
HIGH = np.array([102.0, 103.0, 101.5, 104.0, 105.0, 103.0])
LOW = np.array([99.0, 100.5, 97.5, 100.0, 102.0, 99.5])
CLOSE = np.array([101.0, 100.0, 100.5, 103.0, 102.5, 100.0])
N = 3
ANNUAL = math.sqrt(252)


def test_close_to_close_by_hand() -> None:
    out = rv.close_to_close(CLOSE, N)
    returns = [math.log(CLOSE[i] / CLOSE[i - 1]) for i in range(1, len(CLOSE))]
    expected = [statistics.stdev(returns[i - N : i]) * ANNUAL for i in range(N, len(returns) + 1)]
    assert np.isnan(out[:N]).all()
    np.testing.assert_allclose(out[N:], expected, rtol=1e-12)


def test_parkinson_by_hand() -> None:
    out = rv.parkinson(HIGH, LOW, N)
    last = sum(math.log(HIGH[i] / LOW[i]) ** 2 for i in range(3, 6)) / (4 * math.log(2) * N)
    assert np.isnan(out[: N - 1]).all()
    assert out[-1] == pytest.approx(math.sqrt(last) * ANNUAL, rel=1e-12)


def test_garman_klass_by_hand() -> None:
    out = rv.garman_klass(OPEN, HIGH, LOW, CLOSE, N)
    terms = [
        0.5 * math.log(HIGH[i] / LOW[i]) ** 2
        - (2 * math.log(2) - 1) * math.log(CLOSE[i] / OPEN[i]) ** 2
        for i in range(3, 6)
    ]
    assert out[-1] == pytest.approx(math.sqrt(sum(terms) / N) * ANNUAL, rel=1e-12)


def test_yang_zhang_by_hand() -> None:
    out = rv.yang_zhang(OPEN, HIGH, LOW, CLOSE, N)
    days = range(3, 6)  # the last N bars; each needs the close before it
    overnight = [math.log(OPEN[i] / CLOSE[i - 1]) for i in days]
    open_close = [math.log(CLOSE[i] / OPEN[i]) for i in days]
    rs = [
        math.log(HIGH[i] / CLOSE[i]) * math.log(HIGH[i] / OPEN[i])
        + math.log(LOW[i] / CLOSE[i]) * math.log(LOW[i] / OPEN[i])
        for i in days
    ]
    k = 0.34 / (1.34 + (N + 1) / (N - 1))
    var = statistics.variance(overnight) + k * statistics.variance(open_close)
    var += (1 - k) * sum(rs) / N
    assert np.isnan(out[:N]).all()
    assert out[-1] == pytest.approx(math.sqrt(var) * ANNUAL, rel=1e-12)


def _gbm_ohlc(sigma: float, days: int, steps: int, seed: int = 7) -> tuple[np.ndarray, ...]:
    """Daily OHLC from a fine-grained driftless GBM path (no overnight gap)."""
    rng = np.random.default_rng(seed)
    dt = 1 / (252 * steps)
    increments = rng.normal(-0.5 * sigma**2 * dt, sigma * math.sqrt(dt), (days, steps))
    path = 100 * np.exp(np.cumsum(increments.ravel())).reshape(days, steps)
    opens = np.concatenate([[100.0], path[:-1, -1]])
    highs = np.maximum(path.max(axis=1), opens)
    lows = np.minimum(path.min(axis=1), opens)
    return opens, highs, lows, path[:, -1]


def test_estimators_recover_gbm_volatility() -> None:
    sigma, days = 0.3, 500
    o, h, lo, c = _gbm_ohlc(sigma, days, steps=2000)
    window = days - 1
    estimates = {
        "close_to_close": rv.close_to_close(c, window)[-1],
        "parkinson": rv.parkinson(h, lo, window)[-1],
        "garman_klass": rv.garman_klass(o, h, lo, c, window)[-1],
        "yang_zhang": rv.yang_zhang(o, h, lo, c, window)[-1],
    }
    for name, value in estimates.items():
        assert value == pytest.approx(sigma, rel=0.06), name


def test_short_series_and_bad_inputs() -> None:
    assert np.isnan(rv.close_to_close(CLOSE, 10)).all()
    assert np.isnan(rv.yang_zhang(OPEN, HIGH, LOW, CLOSE, 10)).all()
    with pytest.raises(ValueError, match="window"):
        rv.close_to_close(CLOSE, 1)
    with pytest.raises(ValueError, match="equal length"):
        rv.parkinson(HIGH, LOW[:-1], 2)
    with pytest.raises(ValueError, match="positive"):
        rv.parkinson(HIGH, np.array([1.0, 0.0, 1, 1, 1, 1]), 2)


def test_two_dimensional_input_is_one_series_per_column() -> None:
    other = CLOSE[::-1].copy()
    matrix = np.column_stack([CLOSE, other])
    both = rv.close_to_close(matrix, N)
    assert both.shape == matrix.shape
    np.testing.assert_allclose(both[:, 0], rv.close_to_close(CLOSE, N), equal_nan=True)
    np.testing.assert_allclose(both[:, 1], rv.close_to_close(other, N), equal_nan=True)
    ohlc = [np.column_stack([a, a]) for a in (OPEN, HIGH, LOW, CLOSE)]
    yz = rv.yang_zhang(*ohlc, N)
    np.testing.assert_allclose(yz[:, 1], rv.yang_zhang(OPEN, HIGH, LOW, CLOSE, N), equal_nan=True)


def test_nan_is_a_missing_observation() -> None:
    gapped = CLOSE.copy()
    gapped[3] = np.nan
    out = rv.close_to_close(gapped, 2)
    assert np.isnan(out[3:]).all()  # every window touching session 3 (closes i-2..i) is NaN
    assert not np.isnan(out[2])
    with pytest.raises(ValueError, match="1-d or 2-d"):
        rv.close_to_close(np.ones((2, 2, 2)), 2)
