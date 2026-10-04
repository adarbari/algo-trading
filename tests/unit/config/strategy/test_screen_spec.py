from typing import Any

import pytest

from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.resolve import resolve
from algotrade.config.strategy.schema import parse_strategy
from algotrade.config.strategy.screen_spec import (
    check_screen_spec,
    parse_screen_spec,
    screen_spec,
)
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import Rule
from algotrade.core.model.screen_spec import Mode, Tolerance
from algotrade.storage.configs.files import MemoryConfigStore

CATALOG = FieldCatalog.build(
    {"vol@v1": {"iv30": "float", "spread": "float", "oi": "int", "near": "str"}}
)
IV30 = {"field": "rollup.vol@v1.iv30", "op": "gte", "value": 0.5}
SPREAD = {"field": "rollup.vol@v1.spread", "op": "gte", "value": 0.1}


def spec_doc(**extra: Any) -> dict[str, Any]:
    return {
        "version": 3,
        "criteria": {
            "iv30": IV30,
            "spread": {**SPREAD, "mode": "soft", "tolerance": 0.02, "on_miss": "LIQUIDITY_RISK"},
            "oi": {
                "field": "rollup.vol@v1.oi",
                "op": "gte",
                "value": 1000,
                "mode": "score",
                "tolerance": {"relative": 0.5},
            },
        },
        "flags": {
            "leveraged": {"all": [{"field": "instrument.is_leveraged", "op": "eq", "value": True}]}
        },
        "columns": {"symbol": "instrument.symbol"},
        "rank": {"tie_break": "rollup.vol@v1.spread"},
        **extra,
    }


def test_parse_full_spec_keeps_order_and_modes() -> None:
    spec = parse_screen_spec("vrp", spec_doc(), "vrp")
    assert [c.id for c in spec.criteria] == ["iv30", "spread", "oi"]
    iv30, spread, oi = spec.criteria
    assert iv30.mode is Mode.HARD and iv30.tolerance is None
    assert iv30.rule == Rule("rollup.vol@v1.iv30", "gte", 0.5)
    assert spread.mode is Mode.SOFT and spread.tolerance == Tolerance(0.02)
    assert spread.on_miss == "LIQUIDITY_RISK"
    assert oi.tolerance == Tolerance(0.5, relative=True) and oi.tolerance.width(1000) == 500
    assert not oi.mode.gating and spread.mode.gating
    assert spec.version == 3
    assert spec.tie_break == "rollup.vol@v1.spread" and spec.tie_break_descending
    assert spec.fields() == (
        "instrument.is_leveraged",
        "instrument.symbol",
        "rollup.vol@v1.iv30",
        "rollup.vol@v1.oi",
        "rollup.vol@v1.spread",
    )
    check_screen_spec(spec, CATALOG, "vrp")


def test_disabled_criterion_is_dropped_and_asc_tie_break() -> None:
    doc = spec_doc(rank={"tie_break": "rollup.vol@v1.iv30", "tie_break_order": "asc"})
    doc["criteria"]["oi"] = {**doc["criteria"]["oi"], "enabled": False}
    spec = parse_screen_spec("vrp", doc, "vrp")
    assert [c.id for c in spec.criteria] == ["iv30", "spread"]
    assert not spec.tie_break_descending


@pytest.mark.parametrize(
    ("criterion", "message"),
    [
        ({**IV30, "tolerance": 0.1}, "strict: no tolerance"),
        ({**SPREAD, "mode": "soft"}, "needs a tolerance"),
        ({**SPREAD, "mode": "fuzzy"}, "mode: must be one of"),
        ({**SPREAD, "mode": "soft", "tolerance": 0}, "greater than 0"),
        ({**SPREAD, "mode": "soft", "tolerance": -1}, "greater than 0"),
        ({**SPREAD, "mode": "soft", "tolerance": "2%"}, "absolute"),
        ({**SPREAD, "mode": "soft", "tolerance": {"rel": 0.1}}, "absolute"),
        ({**SPREAD, "value": 0, "mode": "soft", "tolerance": {"relative": 0.1}}, "non-zero"),
        (
            {
                "field": "rollup.vol@v1.near",
                "op": "eq",
                "value": "HIGH",
                "mode": "soft",
                "tolerance": 1,
            },
            "numeric comparison",
        ),
        (
            {
                "field": "rollup.vol@v1.near",
                "op": "gt",
                "value": "A",
                "mode": "soft",
                "tolerance": 1,
            },
            "numeric thresholds",
        ),
        ({**SPREAD, "on_miss": "WATCH"}, "only a soft criterion"),
        ({**SPREAD, "mode": "soft", "tolerance": 1, "on_miss": "REJECT"}, "must be one of"),
        ({**SPREAD, "enabled": "no"}, "true or false"),
        ({**SPREAD, "weight": 3}, "unknown keys"),
        ({"field": "x"}, "op must be one of"),
    ],
)
def test_criterion_errors_name_the_path(criterion: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message) as error:
        parse_screen_spec("vrp", {"criteria": {"c": criterion}}, "vrp")
    assert "vrp.criteria.c" in str(error.value)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({}, "expected a table"),
        ({"criteria": {}}, "at least one enabled"),
        ({"criteria": {"c": {**IV30, "enabled": False}}}, "at least one enabled"),
        ({"criteria": {"Bad Id": IV30}}, "invalid criterion id"),
        ({"criteria": {"c": IV30}, "version": 0}, "positive integer"),
        ({"criteria": {"c": IV30}, "version": "2"}, "positive integer"),
        ({"criteria": {"c": IV30}, "flags": {"a b": {"all": [IV30]}}}, "A-Za-z"),
        ({"criteria": {"c": IV30}, "flags": {"T": [IV30]}}, "expected a table"),
        ({"criteria": {"c": IV30}, "columns": {"x": 3}}, "field name"),
        ({"criteria": {"c": IV30}, "rank": {"tie_break_order": "up"}}, "'asc' or 'desc'"),
        ({"criteria": {"c": IV30}, "rank": {"by": "x"}}, "unknown keys"),
    ],
)
def test_spec_errors(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_screen_spec("vrp", doc, "vrp")


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"criteria": {"c": {**IV30, "field": "rollup.vol@v1.nope"}}}, "unknown field"),
        ({"criteria": {"c": {**IV30, "value": "high"}}}, "does not fit"),
        (
            {
                "criteria": {
                    "c": {
                        "field": "instrument.symbol",
                        "op": "gte",
                        "value": 1,
                        "mode": "soft",
                        "tolerance": 1,
                    }
                }
            },
            "does not fit",
        ),
        (
            {"criteria": {"c": IV30}, "flags": {"T": {"all": [{**IV30, "field": "x.y"}]}}},
            "unknown field",
        ),
        (
            {"criteria": {"c": IV30}, "flags": {"f": {"all": [{**IV30, "value": "a"}]}}},
            "does not fit",
        ),
        ({"criteria": {"c": IV30}, "columns": {"x": "instrument.nope"}}, "unknown field"),
        ({"criteria": {"c": IV30}, "rank": {"tie_break": "instrument.symbol"}}, "numeric"),
    ],
)
def test_catalog_check_fails_closed(doc: dict[str, Any], message: str) -> None:
    spec = parse_screen_spec("vrp", doc, "vrp")
    with pytest.raises(ConfigurationError, match=message):
        check_screen_spec(spec, CATALOG, "vrp")


def test_tolerance_needs_a_numeric_field_type() -> None:
    catalog = FieldCatalog.build({"vol@v1": {"day": "date"}})
    criterion = {
        "field": "rollup.vol@v1.day",
        "op": "gt",
        "value": 1,
        "mode": "score",
        "tolerance": 1,
    }
    spec = parse_screen_spec("s", {"criteria": {"c": criterion}}, "s")
    with pytest.raises(ConfigurationError, match=r"does not fit|needs a number"):
        check_screen_spec(spec, catalog, "s")


def test_legacy_tiers_classify_and_label_parse_and_are_ignored() -> None:
    """v1 / v2 presets are immutable and still carry them (ADR 0030)."""
    legacy = {
        "criteria": {"c": {**IV30, "label": "IV30 >= 50%"}},
        "tiers": {"STRONG": {"all": [IV30]}},
        "classify": "rollup.vol@v1.near",
    }
    spec = parse_screen_spec("vrp", legacy, "vrp")
    assert spec == parse_screen_spec("vrp", {"criteria": {"c": IV30}}, "vrp")


def test_strategy_keeps_rule_keys_only_for_rule_screens() -> None:
    base = {"id": "vrp", "kind": "screener", "impl": "rules"}
    config = parse_strategy({**base, **spec_doc()}, "vrp")
    assert set(config.rules) == {
        "version",
        "criteria",
        "flags",
        "columns",
        "rank",
    }
    assert screen_spec(config).id == "vrp"
    with pytest.raises(ConfigurationError, match="needs \\[criteria\\]"):
        parse_strategy(base, "vrp")
    with pytest.raises(ConfigurationError, match="rule screens"):
        parse_strategy({**base, "impl": "short_premium_liquidity", "criteria": {}}, "x")
    plain = parse_strategy({**base, "impl": "short_premium_liquidity"}, "x")
    with pytest.raises(ConfigurationError, match="not a rule screen"):
        screen_spec(plain)


def _store(user_doc: dict[str, Any] | None = None) -> MemoryConfigStore:
    docs: dict[tuple[str, str, str], Any] = {
        ("site", "selections", "all"): {
            "name": "all",
            "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
        },
        ("site", "strategies", "vrp"): {
            "id": "vrp",
            "kind": "screener",
            "impl": "rules",
            "selection": "all",
            **spec_doc(),
        },
    }
    if user_doc is not None:
        docs[("u1", "strategies", "mine")] = user_doc
    return MemoryConfigStore(docs)


def test_resolve_merges_criteria_by_id_and_hashes_the_spec() -> None:
    site = resolve("vrp", UserContext(SITE_USER), _store().load, catalog=CATALOG)
    assert site.screen_spec.criteria[0].rule.value == 0.5
    user_doc = {
        "id": "mine",
        "extends": "vrp",
        "criteria": {"iv30": {"value": 0.4}, "oi": {"enabled": False}},
    }
    mine = resolve("mine", UserContext("u1"), _store(user_doc).load, catalog=CATALOG)
    assert [c.id for c in mine.screen_spec.criteria] == ["iv30", "spread"]
    assert mine.screen_spec.criteria[0].rule.value == 0.4
    assert mine.screen_spec.criteria[0].mode is Mode.HARD  # the rest of the criterion is kept
    assert mine.hash != site.hash
    again = resolve("vrp", UserContext(SITE_USER), _store().load, catalog=CATALOG)
    assert again.hash == site.hash


def test_resolve_rejects_an_invalid_rule_screen() -> None:
    bad = {"id": "mine", "extends": "vrp", "criteria": {"iv30": {"tolerance": 0.1}}}
    with pytest.raises(ConfigurationError, match="strict: no tolerance"):
        resolve("mine", UserContext("u1"), _store(bad).load)
    unknown = {"id": "mine", "extends": "vrp", "criteria": {"iv30": {"field": "rollup.vol@v1.x"}}}
    with pytest.raises(ConfigurationError, match="unknown field"):
        resolve("mine", UserContext("u1"), _store(unknown).load, catalog=CATALOG)


@pytest.mark.parametrize(
    ("criterion", "path"),
    [
        ({**IV30, "field": "rollup.vol@v1.nope"}, "vrp.criteria.c.field"),
        ({**IV30, "value": "high"}, "vrp.criteria.c.value"),
    ],
)
def test_catalog_errors_name_the_criterion_and_its_field(
    criterion: dict[str, Any], path: str
) -> None:
    other = {"c2": IV30}
    spec = parse_screen_spec("vrp", {"criteria": {**other, "c": criterion}}, "vrp")
    with pytest.raises(ConfigurationError) as error:
        check_screen_spec(spec, CATALOG, "vrp")
    assert str(error.value).startswith(path)


def test_an_empty_tie_break_clears_one() -> None:
    doc = spec_doc(rank={"tie_break": "", "tie_break_order": "asc"})
    spec = parse_screen_spec("vrp", doc, "vrp")
    assert spec.tie_break is None
