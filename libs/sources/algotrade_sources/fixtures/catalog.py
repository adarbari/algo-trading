"""The golden dataset catalogue.

Every strategy is evaluated against every dataset defined here, on every CI run and
nightly. Add a dataset when you discover a market condition we do not yet cover; never
silently change an existing one (create ``<name>_v2`` instead) because the regression
baseline in ``benchmarks/baseline.json`` is keyed by dataset name. Edit here, then run
``algotrade-ingest golden build`` and commit the CSVs and manifest.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from algotrade.core.views.series import PriceSeries
from algotrade_sources.fixtures.files import GoldenFiles
from algotrade_sources.fixtures.generators import (
    Regime,
    business_days,
    correlated_gbm,
    gbm_closes,
    ohlcv_from_closes,
    ou_closes,
    regime_closes,
)

BARS = 756  # three years of daily bars
START = "2020-01-01"

type Builder = Callable[[np.random.Generator], dict[str, PriceSeries]]


@dataclass(frozen=True)
class GoldenSpec:
    name: str
    description: str
    seed: int
    tags: tuple[str, ...]
    build: Builder


def _single(symbol: str, closes_fn: Callable[[np.random.Generator], np.ndarray]) -> Builder:
    def build(rng: np.random.Generator) -> dict[str, PriceSeries]:
        closes = closes_fn(rng)
        ts = business_days(START, len(closes))
        return {symbol: ohlcv_from_closes(symbol, rng, ts, closes)}

    return build


def _multi_asset(rng: np.random.Generator) -> dict[str, PriceSeries]:
    symbols = ("AAA", "BBB", "CCC", "DDD")
    paths = correlated_gbm(
        rng,
        BARS,
        starts=(50, 120, 80, 200),
        drifts=(0.12, 0.04, -0.05, 0.08),
        vols=(0.25, 0.18, 0.30, 0.22),
        correlation=0.6,
    )
    ts = business_days(START, BARS)
    return {s: ohlcv_from_closes(s, rng, ts, p) for s, p in zip(symbols, paths, strict=True)}


CROSS_SECTION_NAMES = 60
CROSS_SECTION_BARS = 420  # 252 sessions of history for 12-1 momentum, then about 170 to test
CROSS_SECTION_BENCHMARK = "SPY"
CROSS_SECTION_TAG = (
    "cross-section"  # the strategy grid skips it (``run_suite``): it is an edge fixture
)


def cross_section_drift(i: int) -> float:
    """The planted annual drift of name ``i``: persistent, from -30% to +60% across the names."""
    return -0.30 + 0.90 * i / (CROSS_SECTION_NAMES - 1)


def _cross_section(rng: np.random.Generator) -> dict[str, PriceSeries]:
    """60 names (``X01``..``X60``) and ``SPY``: each name's drift is planted and persistent
    (``cross_section_drift``), so the 12-1 momentum decile spread is positive by construction;
    the shocks share a market factor. Volume keeps every name above the liquidity gates."""
    ts = business_days(START, CROSS_SECTION_BARS)
    dt = 1.0 / 252
    market = rng.standard_normal(CROSS_SECTION_BARS)
    idio = rng.standard_normal((CROSS_SECTION_BARS, CROSS_SECTION_NAMES))
    vol = 0.22

    def path(drift: float, shocks: np.ndarray, sigma: float) -> np.ndarray:
        rets = (drift - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
        return np.asarray(100.0 * np.exp(np.concatenate([[0.0], np.cumsum(rets)[:-1]])), np.float64)

    out = {
        CROSS_SECTION_BENCHMARK: ohlcv_from_closes(
            CROSS_SECTION_BENCHMARK, rng, ts, path(0.08, market, 0.15), base_volume=5_000_000.0
        )
    }
    for i in range(CROSS_SECTION_NAMES):
        shocks = np.sqrt(0.3) * market + np.sqrt(0.7) * idio[:, i]
        symbol = f"X{i + 1:02d}"
        out[symbol] = ohlcv_from_closes(
            symbol, rng, ts, path(cross_section_drift(i), shocks, vol), base_volume=3_000_000.0
        )
    return out


GOLDEN_DATASETS: tuple[GoldenSpec, ...] = (
    GoldenSpec(
        "bull_trend", "Steady uptrend, moderate volatility", 101, ("trend",),
        _single("BULL", lambda r: gbm_closes(r, BARS, 100.0, drift=0.18, vol=0.18)),
    ),
    GoldenSpec(
        "bear_trend", "Persistent downtrend", 102, ("trend", "stress"),
        _single("BEAR", lambda r: gbm_closes(r, BARS, 100.0, drift=-0.22, vol=0.25)),
    ),
    GoldenSpec(
        "random_walk", "Driftless random walk: no edge should be found here", 103, ("null",),
        _single("WALK", lambda r: gbm_closes(r, BARS, 100.0, drift=0.0, vol=0.20)),
    ),
    GoldenSpec(
        "sideways_mean_revert", "Range-bound, strongly mean-reverting", 104, ("mean-reversion",),
        _single("CHOP", lambda r: ou_closes(r, BARS, 100.0, half_life=8.0, vol=0.25)),
    ),
    GoldenSpec(
        "crash_recovery", "Calm rally, sharp crash, slow recovery", 105, ("stress",),
        _single("CRSH", lambda r: regime_closes(r, 100.0, [
            Regime(300, 0.15, 0.15), Regime(40, -2.5, 0.70), Regime(416, 0.20, 0.30),
        ])),
    ),
    GoldenSpec(
        "high_volatility", "Small drift buried in very high volatility", 106, ("stress",),
        _single("VOLX", lambda r: gbm_closes(r, BARS, 100.0, drift=0.05, vol=0.65)),
    ),
    GoldenSpec(
        "regime_switching", "Alternating trending and choppy regimes", 107, ("trend", "regime"),
        _single("RGME", lambda r: regime_closes(r, 100.0, [
            Regime(126, 0.35, 0.15), Regime(126, 0.0, 0.30), Regime(126, -0.30, 0.20),
            Regime(126, 0.0, 0.12), Regime(126, 0.40, 0.25), Regime(126, -0.10, 0.35),
        ])),
    ),
    GoldenSpec(
        "multi_asset_correlated", "Four correlated assets with mixed drifts", 108,
        ("multi-asset",), _multi_asset,
    ),
    GoldenSpec(
        "cross_section", "60 names and SPY with a planted persistent drift (edge harness)",
        109, ("edge", CROSS_SECTION_TAG), _cross_section,
    ),
)  # fmt: skip


def build_golden(files: GoldenFiles) -> list[str]:
    """(Re)generate every golden dataset's CSV files. Returns the dataset names."""
    for spec in GOLDEN_DATASETS:
        rng = np.random.default_rng(spec.seed)
        files.write(spec.name, spec.description, spec.build(rng), spec.tags)
    return [s.name for s in GOLDEN_DATASETS]
