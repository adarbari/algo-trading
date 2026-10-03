"""Run every strategy over every golden dataset through the real data + engine stack."""

import math

import pytest

from algotrade.backtest.engine import run_backtest
from algotrade.data.golden import GOLDEN_DATASETS
from algotrade.data.store import DatasetStore
from algotrade.strategies.registry import STRATEGIES, create_strategy


def test_golden_checksums_match(golden_store: DatasetStore) -> None:
    assert golden_store.verify() == []


def test_manifest_matches_catalogue(golden_store: DatasetStore) -> None:
    assert sorted(golden_store.names()) == sorted(s.name for s in GOLDEN_DATASETS)


@pytest.mark.parametrize("dataset", sorted(s.name for s in GOLDEN_DATASETS))
@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_strategy_runs_cleanly(golden_store: DatasetStore, dataset: str, strategy: str) -> None:
    result = run_backtest(golden_store.load(dataset), create_strategy(strategy))
    assert all(math.isfinite(v) for v in result.metrics.as_dict().values())
    assert result.equity.min() > 0, "strategy went bankrupt"
    assert result.metrics.num_trades > 0, "strategy never traded"
