"""The levels a rule may name and the use-site check (ADR 0088, design 2.13, 2.15): the table
``LEVELS`` decides which fields each site reads (never a level by name in the check); the four new
sites are fail closed (no null test, ``ne`` / ``not_in`` on a string only over a declared domain,
the gate reads only open data); the screener and universe sites keep today's instrument-only
meaning; a level declared only in a test is readable by a gate rule with no other code change."""

import ast
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.strategy import levels as levels_module
from algotrade.config.strategy.catalog import FieldCatalog
from algotrade.config.strategy.levels import LEVELS, SITES, Level, levels_at
from algotrade.config.strategy.schema import parse_group
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import evaluate_group

CATALOG = FieldCatalog.build(
    {"liq@v1": {"put_tier": "str", "chain_oi": "int"}},
    levels={
        "market": {
            "market.vix@v1.close": "float",
            "market.regime@v1.label": "str",
            "market.regime@v1.state": "str",
            "market.skew@v1.close": "float",
        },
        "position": {"position.dte": "int"},
    },
    licences={"market.skew@v1.close": "personal", "market.vix@v1.close": "open"},
    domains={"market.regime@v1.label": ("CALM", "STRESS")},
)


def group(*rules: dict[str, Any]) -> Any:
    return parse_group({"all": list(rules)}, "rule")


def rule(field: str, op: str, value: Any = None) -> Any:
    body = {"field": field, "op": op, **({} if value is None else {"value": value})}
    return group(body)


def test_the_sites_read_the_levels_the_table_gives_them() -> None:
    assert {s: [level.key for level in levels_at(s)] for s in SITES} == {
        "screener": ["instrument"],
        "universe": ["instrument"],
        "gate": ["market", "portfolio"],
        "entry": ["instrument", "market", "portfolio"],
        "case": ["instrument", "market", "portfolio"],
        "exit": ["instrument", "market", "position"],
    }


@pytest.mark.parametrize(
    ("site", "field", "match"),
    [
        ("screener", "market.vix@v1.close", "market-level field.*'screener'"),
        ("universe", "market.vix@v1.close", "market-level field.*'universe'"),
        ("gate", "rollup.liq@v1.chain_oi", "instrument-level field.*'gate'"),
        ("entry", "position.dte", "position-level field.*'entry'"),
        ("case", "position.dte", "position-level field.*'case'"),
        ("gate", "position.dte", "position-level field.*'gate'"),
        ("gate", "market.nope@v1.x", "unknown field"),
        ("exit", "rollup.nope@v1.x", "unknown field"),
    ],
)
def test_a_field_of_a_level_the_site_does_not_allow_is_refused(
    site: str, field: str, match: str
) -> None:
    with pytest.raises(ConfigurationError, match=match):
        CATALOG.check(rule(field, "gt", 1), "rule", site)


def test_each_site_reads_its_own_levels_and_the_default_site_is_todays_check() -> None:
    CATALOG.check(rule("rollup.liq@v1.chain_oi", "gt", 1))  # screener: unchanged call
    CATALOG.check(rule("market.vix@v1.close", "lt", 30), "rule", "gate")
    CATALOG.check(rule("position.dte", "lte", 21), "rule", "exit")
    CATALOG.check(rule("rollup.liq@v1.chain_oi", "gt", 1), "rule", "entry")
    with pytest.raises(ConfigurationError, match="unknown field"):
        CATALOG.check(rule("portfolio.open_positions", "lt", 3), "rule", "gate")  # P2, no fields


@pytest.mark.parametrize("site", ["gate", "entry", "case", "exit"])
@pytest.mark.parametrize("op", ["is_null", "not_null"])
def test_a_null_test_is_refused_at_the_four_new_sites(site: str, op: str) -> None:
    with pytest.raises(ConfigurationError, match="never null-tested"):
        CATALOG.check(rule("market.vix@v1.close", op), "rule", site)


def test_a_null_test_keeps_working_at_the_screener_site() -> None:
    CATALOG.check(rule("rollup.liq@v1.chain_oi", "is_null"))


@pytest.mark.parametrize("op", ["ne", "not_in"])
def test_ne_and_not_in_on_a_string_need_a_declared_domain(op: str) -> None:
    value: Any = "STRESS" if op == "ne" else ["STRESS"]
    CATALOG.check(rule("market.regime@v1.label", op, value), "rule", "gate")
    with pytest.raises(ConfigurationError, match="needs a declared domain"):
        CATALOG.check(rule("market.regime@v1.state", op, value), "rule", "gate")
    for ok in ("eq", "in"):  # fail closed on their own
        v: Any = "X" if ok == "eq" else ["X"]
        CATALOG.check(rule("market.regime@v1.state", ok, v), "rule", "gate")


def test_a_label_outside_the_domain_is_read_as_missing_so_ne_is_unknown() -> None:
    g = rule("market.regime@v1.label", "ne", "STRESS")
    unseen = {"market.regime@v1.label": CATALOG.domain_read("market.regime@v1.label", "NEW")}
    assert evaluate_group(g, unseen) is None  # UNKNOWN, never TRUE
    seen = {"market.regime@v1.label": CATALOG.domain_read("market.regime@v1.label", "CALM")}
    assert evaluate_group(g, seen) is True
    assert CATALOG.domain_read("market.regime@v1.state", "anything") == "anything"


def test_the_gate_reads_only_open_data_other_sites_may_read_personal() -> None:
    with pytest.raises(ConfigurationError, match=r"personal-licensed.*'gate'"):
        CATALOG.check(rule("market.skew@v1.close", "gt", 1), "rule", "gate")
    CATALOG.check(rule("market.skew@v1.close", "gt", 1), "rule", "entry")
    CATALOG.check(rule("market.skew@v1.close", "gt", 1), "rule", "exit")


def test_a_level_declared_only_in_a_test_is_readable_by_a_gate_rule() -> None:
    sector = Level(
        "sector", ("sector",), "stored", None, "(sector, session)", "that session", "broadcast",
        ("gate",), "Feature.licence",
    )  # fmt: skip
    catalog = FieldCatalog.build(
        {}, levels={"sector": {"sector.flow@v1.net": "float"}}, declared=(*LEVELS, sector)
    )
    catalog.check(rule("sector.flow@v1.net", "gt", 0), "rule", "gate")
    with pytest.raises(ConfigurationError, match=r"sector-level field.*'exit'"):
        catalog.check(rule("sector.flow@v1.net", "gt", 0), "rule", "exit")
    with pytest.raises(ConfigurationError, match="undeclared levels"):
        FieldCatalog.build({}, levels={"sector": {}})


def test_levels_name_computed_providers_by_string_and_import_no_engine() -> None:
    assert all(isinstance(level.producer, str) for level in LEVELS if level.provider == "computed")
    tree = ast.parse(Path(levels_module.__file__ or "").read_text())
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not [m for m in imported if m.startswith(("algotrade.engines", "algotrade.services"))]
