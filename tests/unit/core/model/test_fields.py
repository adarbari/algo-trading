"""Field names <-> tables, for instrument and market-entity feature groups (ADR 0047), and the
one market id."""

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import (
    COMPANY_TABLE,
    REFERENCE_TABLE,
    field_source,
    group_field,
    group_of_table,
    rollup_table,
    table_field,
)
from algotrade.core.model.instruments import AssetClass, key_of, market_id


def test_market_id_is_the_one_mkt_id() -> None:
    assert market_id("US") == "MKT:US" == market_id(" us ")
    assert AssetClass.MARKET == "MKT" and key_of(market_id("US")) == "US"


@pytest.mark.parametrize(
    ("entity", "field", "table"),
    [
        ("instrument", "rollup.price_stats@v2.hv30", "rollups/instrument/price_stats@v2"),
        ("market", "market.breadth@v1.pct_above_200d", "rollups/market/breadth@v1"),
    ],
)
def test_group_fields_round_trip(entity: str, field: str, table: str) -> None:
    key, _, column = field.partition(".")[2].rpartition(".")
    assert rollup_table(entity, key) == table
    assert group_field(entity, key, column) == field
    assert field_source(field) == (table, column)
    assert table_field(*field_source(field)) == field
    assert group_of_table(table) == (entity, key)


def test_other_fields_and_tables() -> None:
    assert field_source("instrument.symbol") == (REFERENCE_TABLE, "symbol")
    assert field_source("instrument.sector") == (COMPANY_TABLE, "sector")
    assert group_of_table("bars/1d") is None and group_of_table("rollups/market/") is None
    with pytest.raises(ConfigurationError, match="computed, not read"):
        field_source("feature.near_52w")
    with pytest.raises(ConfigurationError, match=r"'market\.'"):
        field_source("sector.x@v1.y")
    with pytest.raises(ConfigurationError, match="entity 'sector'"):
        rollup_table("sector", "x@v1")
    with pytest.raises(ConfigurationError, match="entity 'sector'"):
        group_field("sector", "x@v1", "y")
    with pytest.raises(ConfigurationError, match="not a feature group table"):
        table_field("bars/1d", "close")
