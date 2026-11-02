"""The grain dispatch (``data/outcomes/grains.py``): each grain's reads under one signature, the
columns a leg keeps per grain, and a name that is no grain refused."""

from datetime import date

import pytest

from algotrade.data.outcomes import (
    CHAIN,
    CHAIN_COLUMNS,
    GRAINS,
    SHARE_COLUMNS,
    SHARE_PATH,
    STOCK,
    reads_of,
)
from algotrade.data.outcomes.grains import STOCK_COLUMNS
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader

DAY = date(2026, 10, 5)


def test_each_grain_has_its_reads_and_the_columns_a_leg_keeps() -> None:
    columns = {STOCK: STOCK_COLUMNS, CHAIN: tuple(CHAIN_COLUMNS), SHARE_PATH: SHARE_COLUMNS}
    assert set(columns) == set(GRAINS)
    for grain, kept in columns.items():
        reads = reads_of(grain, [("k", "SPY")])
        assert (reads.grain, reads.columns) == (grain, kept)


def test_every_grain_reads_an_empty_store_as_nothing_stored() -> None:
    reader = StoreReader(MemoryBackend())
    for grain in GRAINS:
        reads = reads_of(grain, [("k", "SPY")])
        assert reads.read_stored(reader, [DAY]) is None or reads.read_stored(reader, [DAY]).empty
        assert reads.seqs(reader, [DAY]) == {}
        assert reads.licence(reader, [DAY]) == []
        assert reads.missing([DAY]).args  # a MissingDataError naming the grain's writer


def test_a_name_that_is_no_grain_is_refused() -> None:
    with pytest.raises(ValueError, match="no outcome grain"):
        reads_of("bonds")
