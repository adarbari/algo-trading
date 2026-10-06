"""Fitness tests for feature groups (rollups, ``features/registry.py``, and the groups that
materialise expression features, ``features.site``): every declared group

- is a valid declaration with typed columns, defined in a kind folder of
  ``features/rollups/`` (``price``, ``options``, ``corporate``);
- has a ``config/site/rollups.toml`` section exactly when it takes parameters, and the file
  loads through the one settings loader;
- reads only inputs ``algotrade.data.feature_inputs`` knows how to read, and the
  rollups it reads are registered, acyclic and computed before it (registry order);
- has exactly one producer, its entity's task (``rollups`` for instrument groups,
  ``market-rollups`` for market groups), in ``architecture/tables.toml``;
- is reachable from the selection catalogue as ``rollup.<name>@v<N>.<column>``.
"""

import re
import tomllib
from pathlib import Path

import pytest

from algotrade.config.site.settings import rollup_params
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.fields import FIELD_TYPES
from algotrade.data.feature_inputs import has_input
from algotrade.features.framework.declaration import FeatureGroup, declaration_problems
from algotrade.features.framework.feature import ENTITIES
from algotrade.features.framework.graph import dependencies, dependency_order
from algotrade.features.registry import GROUPS
from algotrade.features.site import site_features
from algotrade.services.configs import field_catalog
from algotrade.storage.configs.files import FileConfigStore
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import MARKET_COUNTS

SITE_ROLLUPS = tomllib.loads((REPO_ROOT / "config" / "site" / "rollups.toml").read_text())
TABLES = tomllib.loads((REPO_ROOT / "architecture" / "tables.toml").read_text())["table"]
DERIVED = "apps/ingestion/algotrade_ingestion/tasks/derived"
PRODUCER = {  # entity -> (registry task, its module): the one producer of that entity's groups
    "instrument": ("rollups", f"{DERIVED}/rollups.py"),
    "market": ("market-rollups", f"{DERIVED}/market_rollups.py"),
}
SITE = site_features(FileConfigStore(REPO_ROOT / "config"))
ALL = SITE.groups  # code groups + materialised expression features, in dependency order


@pytest.mark.parametrize("key", sorted(ALL))
def test_declaration_is_valid_and_typed(key: str) -> None:
    rollup = ALL[key]
    assert rollup.key == key and not declaration_problems(rollup)
    assert set(rollup.columns.values()) <= FIELD_TYPES
    if key not in GROUPS:  # a materialised expression feature
        assert SITE.expressions[rollup.name].materialise and rollup.params is None
        return
    module = Path(str(__import__(rollup.compute.__module__, fromlist=["x"]).__file__))
    assert module.parent.parent == REPO_ROOT / "src" / "algotrade" / "features" / "rollups"


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_params_have_a_site_section_or_none(key: str) -> None:
    has_params = GROUPS[key].params is not None
    assert (key in SITE_ROLLUPS) == has_params, (
        f"{key}: add a ['{key}'] section to config/site/rollups.toml"
        if has_params
        else f"{key} takes no parameters: remove its section"
    )


def test_site_rollups_toml_loads() -> None:
    rollup_params(SITE_ROLLUPS, {k: r.params for k, r in GROUPS.items()})


@pytest.mark.parametrize("key", sorted(ALL))
def test_inputs_have_loaders(key: str) -> None:
    missing = [i.table for i in ALL[key].inputs if not has_input(i.table)]
    assert not missing, f"{key}: no read in data/feature_inputs.py for {missing}"


def test_dependency_graph_is_registered_acyclic_and_in_order() -> None:
    order = list(ALL)
    assert [r.key for r in dependency_order(ALL.values())] == order
    for key, rollup in ALL.items():
        for upstream in dependencies(rollup):
            assert upstream in ALL, f"{key} reads unregistered {upstream}"
            assert order.index(upstream) < order.index(key), f"{key} runs before {upstream}"


def test_every_entity_has_a_producer() -> None:
    assert set(PRODUCER) == set(ENTITIES)
    for task, module in PRODUCER.values():
        assert task in TASKS and TASKS[task].module.__file__ == str(REPO_ROOT / module)


@pytest.mark.parametrize("group", [*ALL.values(), MARKET_COUNTS], ids=lambda g: g.key)
def test_one_producer_per_entity(group: FeatureGroup) -> None:
    """A group of either entity is produced by exactly one task: its entity's."""
    task, module = PRODUCER[group.entity]
    owners = [t["owner"] for t in TABLES if _covers(t["name"], group.table)]
    assert owners == [module]
    others = [n for n, t in TASKS.items() if group.table in t.tables]
    assert others in ([], [task])  # a declared table is registered on that task only


@pytest.mark.parametrize("key", sorted(ALL))
def test_a_declared_group_is_registered_on_its_entity_task(key: str) -> None:
    group = ALL[key]
    assert group.table in TASKS[PRODUCER[group.entity][0]].tables


def _covers(declared: str, table: str) -> bool:
    return declared == table or (declared.endswith("*") and table.startswith(declared[:-1]))


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_reachable_from_the_catalogue(key: str) -> None:
    fields = field_catalog().fields
    for column, kind in GROUPS[key].columns.items():
        assert fields[f"rollup.{key}.{column}"] == kind


def test_expression_features_are_in_the_catalogue_and_stale_fields_say_where_they_went() -> None:
    catalog = field_catalog()
    for name, e in SITE.expressions.items():
        assert catalog.fields[f"feature.{name}"] == e.feature.dtype
    with pytest.raises(ConfigurationError, match=re.escape("use 'feature.pct_from_high_52w'")):
        catalog.check_field("rollup.price_stats@v1.pct_from_high_52w", "sel")
    with pytest.raises(ConfigurationError, match=re.escape("use 'rollup.price_stats@v2.hv30'")):
        catalog.check_field("rollup.price_stats@v1.hv30", "sel")
    with pytest.raises(ConfigurationError, match="retired with no replacement"):
        catalog.check_field("rollup.liquidity_class@v1.rule_hash", "sel")
    with pytest.raises(ConfigurationError, match=re.escape("unknown field 'rollup.nope@v1.x'")):
        catalog.check_field("rollup.nope@v1.x", "sel")


def test_nightly_computes_market_rollups_after_rollups_and_never_blocks_the_screens() -> None:
    names = [s.name for s in NIGHTLY]
    step = next(s for s in NIGHTLY if s.name == "market-rollups")
    assert step.needs == ("rollups",) and not step.critical
    assert names.index("rollups") < names.index("market-rollups") < names.index("screens")
    assert "market-rollups" not in next(s for s in NIGHTLY if s.name == "screens").needs


def test_nightly_computes_rollups_after_the_data_they_read() -> None:
    names = [s.name for s in NIGHTLY]
    for upstream in ("earnings", "bars", "corporate-actions", "chains"):
        assert names.index(upstream) < names.index("rollups")
    assert names.index("rollups") < names.index("screens")
