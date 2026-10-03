"""Every strategy over every golden dataset via the real ingestion -> storage -> engine path."""

import math

import pytest

from algotrade.data import StoreReader
from algotrade.data.reference import instrument_terms, snapshot
from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.datasets import list_datasets, load_datasets
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy
from algotrade_ingestion.sources.base import FixtureSource
from algotrade_ingestion.sources.synthetic.catalog import GOLDEN_DATASETS

DATASETS = sorted(s.name for s in GOLDEN_DATASETS)


def test_golden_checksums_match(golden_source: FixtureSource) -> None:
    assert golden_source.verify() == []


def test_store_catalogue_matches_definitions(golden_reader: StoreReader) -> None:
    assert sorted(list_datasets(golden_reader)) == DATASETS


def test_reference_data_loaded(golden_reader: StoreReader) -> None:
    snap = snapshot(golden_reader, "instruments/reference")
    assert snap is not None and not snap.pre_snapshot
    terms = instrument_terms(golden_reader, snap.snapshot_date)
    assert len(terms) == 11
    assert all(t.multiplier == 1.0 for t in terms.values())


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_strategy_runs_cleanly_everywhere(golden_reader: StoreReader, strategy: str) -> None:
    for dataset, (data, terms) in load_datasets(golden_reader).items():
        result = run_backtest(data, create_strategy(strategy), instruments=terms)
        assert all(math.isfinite(v) for v in result.metrics.as_dict().values()), dataset
        assert result.equity.min() > 0, f"{strategy} went bankrupt on {dataset}"
        assert result.metrics.num_trades > 0, f"{strategy} never traded on {dataset}"
