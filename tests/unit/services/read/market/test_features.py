"""A market's feature values by catalogue name (ADR 0047): the ``MKT:US`` row of the market
groups for exactly the session (never an older partition), expression features over them, and
names outside the market's catalogue refused."""

from dataclasses import replace

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.features.expressions.definitions import build_expressions
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import UnknownFeatureError, feature_infos
from algotrade.services.read.instruments.features import load_feature_values
from algotrade.services.read.market.features import load_market_feature_values
from algotrade.services.read.values import UnknownCode
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import MARKET_COUNTS, write_rows
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with

NAMES = "market.market_counts@v1.names"
SPY = "market.market_counts@v1.spy_close"
SHARE = "feature.share"


def _counts(writer: StoreWriter) -> None:
    for day, names, covered, spy in ((D0, 3, 3, 9.0), (D1, 4, 2, None)):
        row = {"instrument_id": "MKT:US", "names": names, "with_bars": covered, "spy_close": spy}
        write_rows(writer, MARKET_COUNTS.table, day, [row])


def _with_market(ctx: ReadContext) -> ReadContext:
    share = FeatureDefinition(
        "share", "test", "market_counts.with_bars / market_counts.names", "float", "ratio",
        "share of names with a bar", "never",
    )  # fmt: skip
    site = ctx.features
    code = {**site.code, MARKET_COUNTS.key: MARKET_COUNTS}
    added = build_expressions([share], code, base=site.expressions)
    return replace(ctx, features=FeatureSet(code, {**site.expressions, **added}, site.superseded))


def _got(ctx: ReadContext, *names: str) -> dict[str, tuple[object, object]]:
    found = load_market_feature_values(ctx, names)
    return {v.name: (v.value, v.unknown.code if v.unknown else None) for v in found}


def test_values_of_the_market_row_for_exactly_the_session() -> None:
    ctx = _with_market(context(store_with(_counts)))
    got = _got(ctx, NAMES, SHARE, SPY, NAMES)
    assert list(got) == [NAMES, SHARE, SPY]  # in the order asked, repeats dropped
    assert got[NAMES] == (4, None) and got[SHARE] == (0.5, None)
    assert got[SPY] == (None, UnknownCode.NULL)  # D1's null, never D0's 9.0
    [info] = feature_infos(ctx.features, [NAMES], "market").values()
    assert info.source == MARKET_COUNTS.table and info.key == "market_counts.names@v1"


def test_a_session_without_a_partition_is_unknown() -> None:
    def only_d0(writer: StoreWriter) -> None:
        write_rows(writer, MARKET_COUNTS.table, D0, [{"instrument_id": "MKT:US", "names": 3}])

    [value] = load_market_feature_values(_with_market(context(store_with(only_d0))), [NAMES])
    assert value.value is None and value.unknown is not None
    assert value.unknown.code is UnknownCode.NO_PARTITION
    assert value.unknown.detail == f"{MARKET_COUNTS.table} has no partition for {D1.isoformat()}"


def test_names_outside_the_entitys_catalogue_are_refused() -> None:
    ctx = _with_market(context(store_with(_counts)))
    with pytest.raises(UnknownFeatureError, match=r"unknown market feature 'instrument\.symbol'"):
        load_market_feature_values(ctx, ["instrument.symbol"])
    with pytest.raises(UnknownFeatureError, match=r"unknown market feature 'feature\.pct_from"):
        load_market_feature_values(ctx, ["feature.pct_from_high_52w"])
    with pytest.raises(UnknownFeatureError, match=r"unknown field 'market\.market_counts"):
        load_feature_values(ctx, ["EQ:AAA"], [NAMES])
    with pytest.raises(UnknownFeatureError, match=r"unknown field 'feature\.share'"):
        load_feature_values(ctx, ["EQ:AAA"], [SHARE])
    with pytest.raises(ValueError, match="a market read names its ids"):
        load_feature_values(ctx, None, [NAMES], entity="market")
    assert NAMES in feature_infos(ctx.features, None, "market")
