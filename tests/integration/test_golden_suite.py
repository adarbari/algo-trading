"""Every strategy over every golden dataset via the real ingestion -> storage -> engine path."""

import math

import pytest

from algotrade.engines.backtest.engine import run_backtest
from algotrade.services.datasets import list_datasets, load_datasets
from algotrade.storage.readers import StoreReader
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy
from algotrade_ingestion.sources.synthetic.catalog import GOLDEN_DATASETS
from algotrade_ingestion.sources.synthetic.files import GoldenFiles

DATASETS = sorted(s.name for s in GOLDEN_DATASETS)


def test_golden_checksums_match(golden_files: GoldenFiles) -> None:
    assert golden_files.verify() == []


def test_store_catalogue_matches_definitions(golden_reader: StoreReader) -> None:
    assert sorted(list_datasets(golden_reader)) == DATASETS


def test_reference_data_loaded(golden_reader: StoreReader) -> None:
    terms = golden_reader.instrument_terms(golden_reader.latest_date("instruments/reference"))  # type: ignore[arg-type]
    assert len(terms) == 11
    assert all(t.multiplier == 1.0 for t in terms.values())


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_strategy_runs_cleanly_everywhere(golden_reader: StoreReader, strategy: str) -> None:
    for dataset, (data, terms) in load_datasets(golden_reader).items():
        result = run_backtest(data, create_strategy(strategy), instruments=terms)
        assert all(math.isfinite(v) for v in result.metrics.as_dict().values()), dataset
        assert result.equity.min() > 0, f"{strategy} went bankrupt on {dataset}"
        assert result.metrics.num_trades > 0, f"{strategy} never traded on {dataset}"
