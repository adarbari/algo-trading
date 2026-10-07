"""Building expression features from definitions: names resolve to the registered group
versions, params bind as literals, the dependency graph is ordered and cycles fail, each
takes the entity of what it reads (mixing entities fails, ADR 0047), and every problem names
the file, the feature and (for a formula) the position."""

from dataclasses import replace

import pytest

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.features.expressions.definitions import build_expressions, formula_type
from algotrade.features.expressions.nodes import ExpressionError
from algotrade.features.registry import GROUPS
from tests.helpers.rollup_store import MARKET_COUNTS

WITH_MARKET = {**GROUPS, MARKET_COUNTS.key: MARKET_COUNTS}


def define(name: str, expr: str, dtype: str = "float", **kw: object) -> FeatureDefinition:
    base = FeatureDefinition(name, "test", expr, dtype, "decimal", f"test {name}", "never")
    return replace(base, **kw)  # type: ignore[arg-type]


def test_refs_params_and_order() -> None:
    out = build_expressions(
        [
            define("b", "a * k", params={"k": 2}),
            define("a", "price_stats.close / price_stats.high_52w - 1"),
            define("flag", "exists(option_liquidity) and b > 0", dtype="bool", unit="flag"),
        ],
        GROUPS,
    )
    assert list(out) == ["a", "b", "flag"]  # dependencies first
    a, b, flag = out["a"], out["b"], out["flag"]
    assert a.refs == ("price_stats.close", "price_stats.high_52w") and a.uses == ()
    assert a.feature.inputs == ("price_stats.close@v2", "price_stats.high_52w@v2")
    assert b.uses == ("a",) and b.feature.inputs == ("a@v1",)
    assert flag.exists == ("option_liquidity",) and flag.refs == ()
    assert a.feature.key == "a@v1" and a.feature.field == "feature.a" and not a.materialise


@pytest.mark.parametrize(
    ("defs", "message"),
    [
        ([define("a", "b + 1"), define("b", "c * 2"), define("c", "a")],
         "dependency cycle: a -> b -> c -> a"),
        ([define("a", "a + 1")], "dependency cycle: a -> a"),
        ([define("a", "nope + 1")], "[a] expr, line 1 col 1: unknown name 'nope'"),
        ([define("a", "price_stats.clsoe")], "price_stats@v2 has no feature 'clsoe'"),
        ([define("a", "prices.close")], "unknown feature group 'prices'"),
        ([define("a", "1", params={"k": 1})], "params ['k'] are not used in expr"),
        ([define("a", "price_stats", params={"price_stats": 1})], "taken by a feature"),
        ([define("a", "1"), define("a", "2")], "'a' is already a feature or group name"),
        ([define("price_stats", "1")], "'price_stats' is already a feature or group name"),
        ([define("a", "price_stats.close > 1")], "expr gives bool, but dtype is float"),
        ([define("a", "'HIGH'", dtype="str", unit="category", kind="label",
                 categories=("LOW",))], "expr can give ['HIGH'], not in categories"),
        ([define("a", "'X'", dtype="str", unit="category", kind="label")],
         "a label declares its categories"),
        ([define("a", "1", dtype="decimal")], "dtype must be one of"),
        ([define("a", "1", unit="percent")], "unit 'percent' must be one of"),
        ([define("Bad", "1")], "Bad: name must match"),
        ([define("a", "1 +")], "[a] expr, line 1 col 4: expected a value"),
        ([define("a", "option_liquidity.put_tier == 'E'", dtype="bool", unit="flag")],
         "'E' is never a value here"),
    ],
)  # fmt: skip
def test_errors(defs: list[FeatureDefinition], message: str) -> None:
    with pytest.raises(ExpressionError, match=r"config/site/features/test\.toml") as info:
        build_expressions(defs, GROUPS)
    assert message in str(info.value)


def test_option_liquidity_status_has_open_categories_but_tiers_are_closed() -> None:
    out = build_expressions(
        [define("t", "option_liquidity.put_tier", dtype="str", unit="category", kind="label",
                categories=("A", "B", "C", "D"))],
        GROUPS,
    )  # fmt: skip
    assert out["t"].type.categories == frozenset("ABCD")


def test_an_expression_takes_the_entity_of_what_it_reads() -> None:
    out = build_expressions(
        [
            define("coverage", "market_counts.with_bars / market_counts.names", unit="ratio"),
            define("half", "coverage / 2", unit="ratio"),
            define("seen", "exists(market_counts)", dtype="bool", unit="flag"),
            define("ret", "price_stats.close / price_stats.sma_20 - 1"),
            define("one", "1"),
        ],
        WITH_MARKET,
    )
    assert {n: e.feature.entity for n, e in out.items()} == {
        "coverage": "market", "half": "market", "seen": "market", "ret": "instrument",
        "one": "instrument",
    }  # fmt: skip
    assert out["coverage"].feature.field == "feature.coverage"


@pytest.mark.parametrize(
    ("defs", "names"),
    [
        ([define("a", "price_stats.close * market_counts.spy_close")],
         "market_counts.spy_close (market), price_stats.close (instrument)"),
        ([define("m", "market_counts.spy_close"), define("a", "m - price_stats.close")],
         "m (market), price_stats.close (instrument)"),
        ([define("a", "if(exists(market_counts), price_stats.close, null)")],
         "market_counts (market), price_stats.close (instrument)"),
    ],
)  # fmt: skip
def test_mixing_entities_is_a_definition_error(defs: list[FeatureDefinition], names: str) -> None:
    with pytest.raises(ExpressionError, match=r"config/site/features/test\.toml") as info:
        build_expressions(defs, WITH_MARKET)
    assert "reads features of more than one entity (instrument and market)" in str(info.value)
    assert names in str(info.value)


def test_a_free_formula_may_not_mix_entities_either() -> None:
    assert formula_type("market_counts.names * 2", WITH_MARKET, {}).kind == "num"
    with pytest.raises(ExpressionError, match="more than one entity"):
        formula_type("market_counts.names * price_stats.close", WITH_MARKET, {})
