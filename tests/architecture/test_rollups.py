"""Fitness tests for feature groups (rollups, ``features/registry.py``): every declared group

- is a valid declaration with typed columns, defined in ``features/rollups/``;
- has a ``config/site/rollups.toml`` section exactly when it takes parameters, and the file
  loads through the one settings loader;
- reads only inputs ``algotrade.data.feature_inputs`` knows how to read, and the
  rollups it reads are registered, acyclic and computed before it (registry order);
- has exactly one producer, the ``rollups`` task, in ``architecture/ownership.toml``;
- is reachable from the selection catalogue as ``rollup.<name>@v<N>.<column>``.
"""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.site.settings import rollup_params
from algotrade.core.model.fields import FIELD_TYPES
from algotrade.data.feature_inputs import has_input
from algotrade.features.framework.declaration import declaration_problems
from algotrade.features.framework.graph import dependencies, dependency_order
from algotrade.features.registry import GROUPS
from algotrade.services.configs import field_catalog
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from tests.conftest import REPO_ROOT

SITE_ROLLUPS = tomllib.loads((REPO_ROOT / "config" / "site" / "rollups.toml").read_text())
OWNERSHIP = tomllib.loads((REPO_ROOT / "architecture" / "ownership.toml").read_text())
TASK_MODULE = "apps/ingestion/algotrade_ingestion/tasks/derived/rollups.py"


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_declaration_is_valid_and_typed(key: str) -> None:
    rollup = GROUPS[key]
    assert rollup.key == key and not declaration_problems(rollup)
    assert set(rollup.columns.values()) <= FIELD_TYPES
    module = Path(str(__import__(rollup.compute.__module__, fromlist=["x"]).__file__))
    assert module.parent == REPO_ROOT / "src" / "algotrade" / "features" / "rollups"


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


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_inputs_have_loaders(key: str) -> None:
    missing = [i.table for i in GROUPS[key].inputs if not has_input(i.table)]
    assert not missing, f"{key}: no read in data/feature_inputs.py for {missing}"


def test_dependency_graph_is_registered_acyclic_and_in_order() -> None:
    order = list(GROUPS)
    assert [r.key for r in dependency_order(GROUPS.values())] == order
    for key, rollup in GROUPS.items():
        for upstream in dependencies(rollup):
            assert upstream in GROUPS, f"{key} reads unregistered {upstream}"
            assert order.index(upstream) < order.index(key), f"{key} runs before {upstream}"


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_one_producer_the_rollups_task(key: str) -> None:
    table = GROUPS[key].table
    owners = [t["owner"] for t in OWNERSHIP["table"] if t["name"] == table]
    assert owners == [TASK_MODULE]
    assert table in TASKS["rollups"].tables


@pytest.mark.parametrize("key", sorted(GROUPS))
def test_reachable_from_the_catalogue(key: str) -> None:
    fields = field_catalog().fields
    for column, kind in GROUPS[key].columns.items():
        assert fields[f"rollup.{key}.{column}"] == kind


def test_nightly_computes_rollups_after_the_data_they_read() -> None:
    names = [s.name for s in NIGHTLY]
    for upstream in ("earnings", "bars", "corporate-actions", "chains"):
        assert names.index(upstream) < names.index("rollups")
    assert names.index("rollups") < names.index("screens")
