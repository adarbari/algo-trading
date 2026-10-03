from typing import Any

import pytest

from algotrade.config.strategy.catalog import FieldCatalog, field_source
from algotrade.config.strategy.resolve import BUILTIN_DEFAULTS, deep_merge, resolve
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore

ACTIVE = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}
NOT_LEVERAGED = {"field": "instrument.is_leveraged", "op": "eq", "value": False}
CATALOG = FieldCatalog.build({"liq@v1": {"put_tier": "str", "chain_oi": "int"}})


def store(extra: dict[tuple[str, str, str], Any] | None = None) -> MemoryConfigStore:
    docs: dict[tuple[str, str, str], Any] = {
        ("site", "defaults", "defaults"): {"screening": {"min_coverage": 0.9}},
        ("site", "selections", "active"): {"name": "active", "where": {"all": [ACTIVE]}},
        ("site", "strategies", "scr"): {
            "id": "scr",
            "kind": "screener",
            "impl": "s",
            "selection": "active",
            "params": {"k": 1},
        },
    }
    docs.update(extra or {})
    return MemoryConfigStore(docs)


def test_site_preset_with_defaults() -> None:
    r = resolve("scr", UserContext(SITE_USER), store().load, catalog=CATALOG)
    assert r.layers == ("site/strategies/scr", "site/selections/active")
    assert r.settings["screening"]["min_coverage"] == 0.9  # site default over builtin
    assert r.settings["backtest"] == BUILTIN_DEFAULTS["backtest"]
    assert len(r.hash) == 64


def test_user_narrows_preset_and_inherits_its_rules() -> None:
    s = store(
        {
            ("u1", "strategies", "scr"): {
                "selection_overrides": {"all": [NOT_LEVERAGED]},
                "params": {"k": 2},
            }
        }
    )
    r = resolve("scr", UserContext("u1"), s.load, catalog=CATALOG)
    assert r.config.params == {"k": 2}
    assert [rule.field for rule in r.selection.where.rules()] == [  # type: ignore[union-attr]
        "instrument.status",
        "instrument.is_leveraged",
    ]
    assert r.layers[-2:] == ("u1/strategies/scr", "site/selections/active")


def test_user_replaces_selection_and_extends_other_preset() -> None:
    mine = {"name": "mine", "where": {"all": [NOT_LEVERAGED]}}
    s = store(
        {
            ("u1", "selections", "mine"): mine,
            ("u1", "strategies", "custom"): {"extends": "scr", "selection": "mine"},
        }
    )
    r = resolve("custom", UserContext("u1"), s.load)
    assert r.config.id == "custom"
    assert r.selection.name == "mine"  # type: ignore[union-attr]
    assert "u1/selections/mine" in r.layers


def test_user_only_config_and_run_overrides() -> None:
    own = {"id": "own", "kind": "strategy", "impl": "sma", "selection": "active"}
    s = store({("u1", "strategies", "own"): own})
    r = resolve("own", UserContext("u1"), s.load, overrides={"params": {"fast": 5}})
    assert r.config.params == {"fast": 5}
    assert r.layers[-2] == "run-overrides"


def test_hash_changes_with_anything_that_affects_results() -> None:
    s = store()
    base = resolve("scr", UserContext(SITE_USER), s.load)
    again = resolve("scr", UserContext(SITE_USER), s.load)
    tweaked = resolve("scr", UserContext(SITE_USER), s.load, overrides={"params": {"k": 9}})
    settings = resolve(
        "scr", UserContext(SITE_USER), s.load, overrides={"screening": {"min_coverage": 0.1}}
    )
    assert base.hash == again.hash
    assert len({base.hash, tweaked.hash, settings.hash}) == 3


def test_rebalance_settings_are_in_the_hash_and_absent_by_default() -> None:
    s = store()
    base = resolve("scr", UserContext(SITE_USER), s.load)
    assert "rebalance_selection" not in base.settings["backtest"]  # existing hashes unchanged
    assert base.backtest.rebalance_selection == "none"
    monthly = resolve(
        "scr",
        UserContext(SITE_USER),
        s.load,
        overrides={"backtest": {"rebalance_selection": "monthly"}},
    )
    lagged = resolve(
        "scr",
        UserContext(SITE_USER),
        s.load,
        overrides={"backtest": {"rebalance_selection": "monthly", "selection_lag_sessions": 2}},
    )
    assert len({base.hash, monthly.hash, lagged.hash}) == 3
    with pytest.raises(ConfigurationError, match="rebalance_selection"):
        resolve(
            "scr",
            UserContext(SITE_USER),
            s.load,
            overrides={"backtest": {"rebalance_selection": "yearly"}},
        )


def test_site_user_never_reads_user_documents() -> None:
    scopes: list[str] = []
    base = store()

    def spy(scope: str, kind: str, name: str) -> Any:
        scopes.append(scope)
        return base.load(scope, kind, name)

    assert resolve("scr", UserContext(SITE_USER), spy).config.params == {"k": 1}
    assert set(scopes) == {"site"}


@pytest.mark.parametrize(
    ("docs", "config_id", "message"),
    [
        ({}, "nope", "unknown config"),
        ({("u1", "strategies", "x"): {"extends": "missing"}}, "x", "extends unknown preset"),
        (
            {
                ("u1", "strategies", "x"): {
                    "id": "x",
                    "kind": "screener",
                    "impl": "s",
                    "selection": "ghost",
                }
            },
            "x",
            "unknown selection",
        ),
        (
            {
                ("u1", "strategies", "x"): {
                    "id": "x",
                    "kind": "screener",
                    "impl": "s",
                    "selection_overrides": {"all": [ACTIVE]},
                }
            },
            "x",
            "need a base",
        ),
    ],
)
def test_resolution_errors(docs: dict, config_id: str, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ConfigurationError, match=message):
        resolve(config_id, UserContext("u1"), store(docs).load)


def test_catalog_validates_fields_and_types() -> None:
    def check(rule: dict[str, Any], **sel: Any) -> None:
        s = store(
            {
                ("site", "selections", "bad"): {"name": "bad", "where": {"all": [rule]}, **sel},
                ("site", "strategies", "b"): {
                    "id": "b",
                    "kind": "screener",
                    "impl": "s",
                    "selection": "bad",
                },
            }
        )
        resolve("b", UserContext(SITE_USER), s.load, catalog=CATALOG)

    check({"field": "rollup.liq@v1.chain_oi", "op": "gte", "value": 100})
    check({"field": "instrument.listed_on", "op": "lt", "value": "2020-01-01"})
    for rule, message in [
        ({"field": "instrument.nope", "op": "eq", "value": 1}, "unknown field"),
        ({"field": "instrument.optionable", "op": "eq", "value": "yes"}, "does not fit"),
        ({"field": "instrument.optionable", "op": "gt", "value": True}, "does not fit"),
        ({"field": "rollup.liq@v1.chain_oi", "op": "gte", "value": 1.5}, "does not fit"),
        ({"field": "instrument.multiplier", "op": "eq", "value": True}, "does not fit"),
    ]:
        with pytest.raises(ConfigurationError, match=message):
            check(rule)
    with pytest.raises(ConfigurationError, match="unknown field"):
        check(ACTIVE, max_instruments=5, order_by="rollup.liq@v1.nope")


def test_field_source_and_catalog_types() -> None:
    assert field_source("instrument.symbol") == ("instruments/reference", "symbol")
    assert field_source("instrument.sector") == ("instruments/company", "sector")
    assert field_source("rollup.option_liquidity@v1.put_tier") == (
        "rollups/instrument/option_liquidity@v1",
        "put_tier",
    )
    with pytest.raises(ConfigurationError, match="must start with"):
        field_source("price.close")
    with pytest.raises(ConfigurationError, match="field types"):
        FieldCatalog.build({"x@v1": {"c": "decimal"}})


def test_deep_merge() -> None:
    assert deep_merge({"a": {"b": 1, "c": 2}, "l": [1]}, {"a": {"b": 3}, "l": [2]}) == {
        "a": {"b": 3, "c": 2},
        "l": [2],
    }


@pytest.mark.parametrize(
    "doc",
    [
        {"id": "x", "kind": "screener", "impl": "s", "selection": "active", "api_key": "abc"},
        {
            "id": "x",
            "kind": "screener",
            "impl": "s",
            "selection": "active",
            "params": {"vendor_token": "abc"},
        },
        {"extends": "scr", "exports": [{"password": "p"}]},
    ],
)
def test_configs_never_hold_secrets(doc: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ConfigurationError, match="looks like a secret"):
        resolve("x", UserContext("u1"), store({("u1", "strategies", "x"): doc}).load)


def test_secret_like_run_overrides_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match=r"run-overrides\.params\.token"):
        resolve("scr", UserContext(SITE_USER), store().load, overrides={"params": {"token": 1}})
