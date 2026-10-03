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
from algotrade_ingestion.sources.fixtures.files import GoldenFiles
from algotrade_ingestion.sources.fixtures.generators import (
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
)  # fmt: skip


def build_golden(files: GoldenFiles) -> list[str]:
    """(Re)generate every golden dataset's CSV files. Returns the dataset names."""
    for spec in GOLDEN_DATASETS:
        rng = np.random.default_rng(spec.seed)
        files.write(spec.name, spec.description, spec.build(rng), spec.tags)
    return [s.name for s in GOLDEN_DATASETS]
