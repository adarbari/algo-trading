"""The feature set: lookups, the read plan (only the stored columns needed; a materialised
expression read from its table), joining group rows with ``exists``, evaluation over a
range, materialised groups in the dependency order (a market-entity one in rollups/market/),
and fields of superseded groups."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.expressions.frame import join
from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS, SUPERSEDED
from tests.helpers.rollup_store import MARKET_COUNTS, store, write_rows

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
PS = "rollups/instrument/price_stats@v2"
OL = "rollups/instrument/option_liquidity@v1"


def define(name: str, expr: str, dtype: str = "float", **kw: object) -> FeatureDefinition:
    base = FeatureDefinition(name, "t", expr, dtype, "decimal", f"test {name}", "never")
    return replace(base, **kw)  # type: ignore[arg-type]


DEFS = [
    define("div_yield", "if(price_stats.close > 0, dividends.div_ttm / price_stats.close, null)",
           dtype="float32", materialise=True),
    define("double_yield", "div_yield * 2"),
    define("ret", "price_stats.close / price_stats.sma_20 - 1"),
    define("listed", "exists(option_liquidity)", dtype="bool", unit="flag"),
]  # fmt: skip


@pytest.fixture(scope="module")
def fs() -> FeatureSet:
    return FeatureSet.build(GROUPS, DEFS, SUPERSEDED)


def test_lookups_and_fields(fs: FeatureSet) -> None:
    assert fs.feature("ret") is fs.feature("ret@v1") is fs.feature("feature.ret")
    assert fs.feature("rollup.price_stats@v2.hv30") is fs.feature("price_stats.hv30@v2")
    assert fs.feature("nope") is None
    types = fs.field_types()
    assert types["feature.listed"] == "bool" and types["rollup.price_stats@v2.close"] == "float32"
    assert "rollup.div_yield@v1.div_yield" not in types  # a materialised one is feature.<name>


def test_plan_reads_only_what_is_needed(fs: FeatureSet) -> None:
    assert fs.stored_columns(["ret"]) == {PS: {"close", "sma_20"}}
    assert fs.stored_columns(["double_yield"]) == {"rollups/instrument/div_yield@v1": {"div_yield"}}
    assert fs.stored_columns(["listed"]) == {OL: set()}
    stored, todo = fs.plan(["div_yield"], compute=["div_yield"])
    assert stored == {"price_stats": {"close"}, "dividends": {"div_ttm"}} and todo == ["div_yield"]
    with pytest.raises(KeyError, match="unknown expression feature 'nope'"):
        fs.plan(["nope"])


def test_materialised_groups_join_the_dependency_order(fs: FeatureSet) -> None:
    keys = list(fs.groups)
    assert keys.index("dividends@v2") < keys.index("div_yield@v1") < keys.index("iv30@v1")
    group = fs.groups["div_yield@v1"]
    assert group.table == "rollups/instrument/div_yield@v1"
    assert {i.table for i in group.inputs} == {PS, "rollups/instrument/dividends@v2"}
    assert not any(i.required for i in group.inputs)
    with pytest.raises(
        ConfigurationError, match=r"iv30@v1 reads unregistered rollups.*materialise"
    ):
        FeatureSet.build(GROUPS, [replace(DEFS[0], materialise=False)])


def test_join_marks_rows_present_absent_and_unknown() -> None:
    a = pd.DataFrame({"session_date": [D1, D1, D2], "instrument_id": ["X", "Y", "X"],
                      "v": [1.0, 2.0, 3.0]})  # fmt: skip
    b = pd.DataFrame({"session_date": [D1], "instrument_id": ["X"], "w": ["k"]})
    keys, cols = join({"a": a, "b": b, "c": None}, {"a": {"v"}, "b": {"w"}, "c": {"z"}})
    assert keys.to_dict("list") == {"session_date": [D1, D1, D2], "instrument_id": ["X", "Y", "X"]}
    assert list(cols["exists:b"][:2]) == [1.0, 0.0] and np.isnan(cols["exists:b"][2])  # no D2 rows
    assert np.isnan(cols["exists:c"]).all() and list(cols["c.z"]) == [None] * 3
    assert pd.Series(cols["b.w"]).isna().tolist() == [False, True, True]
    empty_keys, _ = join({"a": None}, {"a": {"v"}})
    assert len(empty_keys) == 0


def test_evaluate_a_range_and_a_materialised_compute(fs: FeatureSet) -> None:
    ps = pd.DataFrame({"session_date": [D1, D2, D2], "instrument_id": ["X", "X", "Y"],
                       "close": [10.0, 11.0, 0.0], "sma_20": [10.0, 10.0, 5.0]})  # fmt: skip
    dv = pd.DataFrame({"session_date": [D2], "instrument_id": ["X"], "div_ttm": [0.55]})
    out = fs.evaluate({PS: ps, "rollups/instrument/dividends@v2": dv}, ["ret", "div_yield"],
                      compute=["div_yield"])  # fmt: skip
    assert out["ret"].round(6).tolist()[:2] == [0.0, 0.1]
    assert out["div_yield"].isna().tolist() == [True, False, True]
    assert out.loc[1, "div_yield"] == pytest.approx(0.05)
    stored = pd.DataFrame({"session_date": [D2], "instrument_id": ["X"], "div_yield": [0.05]})
    read = fs.evaluate({"rollups/instrument/div_yield@v1": stored}, ["double_yield"])
    assert read["double_yield"].tolist() == pytest.approx([0.1])


def test_the_runner_stores_a_materialised_expression(fs: FeatureSet) -> None:
    writer, reader = store()
    write_rows(writer, PS, D2, [{"instrument_id": "X", "close": 50.0, "sma_20": 1.0}])
    write_rows(writer, "rollups/instrument/dividends@v2", D2,
                 [{"instrument_id": "X", "div_ttm": 1.0}])  # fmt: skip
    result = compute_one(reader, fs.groups["div_yield@v1"], D2)
    assert result.frame is not None
    assert result.frame.to_dict("list") == {
        "instrument_id": ["X"],
        "div_yield": [pytest.approx(0.02)],
    }
    assert str(result.frame["div_yield"].dtype) == "float32"
    nothing = compute_one(reader, fs.groups["div_yield@v1"], D1)
    assert nothing.frame is None and nothing.no_input == f"no input for {D1}"


def test_fields_of_superseded_groups(fs: FeatureSet) -> None:
    assert fs.moved_field("rollup.price_stats@v1.hv30") == "rollup.price_stats@v2.hv30"
    assert fs.moved_field("rollup.liquidity_class@v1.chain_oi") == "feature.option_chain_oi"
    assert fs.moved_field("rollup.liquidity_class@v1.rule_hash") == ""
    assert fs.moved_field("rollup.dividends@v1.div_yield") == "feature.div_yield"
    assert fs.moved_field("rollup.price_stats@v1.nope") == ""
    assert fs.moved_field("rollup.price_stats@v2.hv30") is None
    assert fs.moved_field("instrument.symbol") is None


def test_a_market_expression_is_a_market_feature_and_stored_as_one() -> None:
    groups = {**GROUPS, MARKET_COUNTS.key: MARKET_COUNTS}
    share = define("share", "market_counts.with_bars / market_counts.names", materialise=True)
    fs = FeatureSet.build(groups, [*DEFS, share])
    assert fs.table("share") == "rollups/market/share@v1"
    group = fs.groups["share@v1"]
    assert group.entity == "market" and group.table == "rollups/market/share@v1"
    assert list(fs.groups).index("market_counts@v1") < list(fs.groups).index("share@v1")
    market = fs.field_types("market")
    assert market["feature.share"] == "float" and "market.market_counts@v1.names" in market
    assert "feature.ret" not in market and "feature.share" not in fs.field_types("instrument")
    writer, reader = store()
    write_rows(writer, MARKET_COUNTS.table, D2,
               [{"instrument_id": "MKT:US", "names": 4, "with_bars": 3}])  # fmt: skip
    result = compute_one(reader, group, D2)
    assert result.frame is not None
    assert result.frame.to_dict("list") == {"instrument_id": ["MKT:US"], "share": [0.75]}
