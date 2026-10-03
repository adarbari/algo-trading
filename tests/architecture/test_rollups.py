"""Fitness tests for rollups (``features/registry.py``): every declared rollup

- is a valid declaration with typed columns, defined in ``features/rollups/``;
- has a ``config/site/rollups.toml`` section exactly when it takes parameters, and the file
  loads through the one settings loader;
- reads only inputs the framework knows how to load (through ``algotrade.data``);
- has exactly one producer, the ``rollups`` task, in ``architecture/ownership.toml``;
- is reachable from the selection catalogue as ``rollup.<name>@v<N>.<column>``.
"""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.site.settings import rollup_params
from algotrade.core.model.fields import FIELD_TYPES
from algotrade.features.framework.declaration import declaration_problems
from algotrade.features.framework.inputs import LOADERS
from algotrade.features.registry import ROLLUPS
from algotrade.services.configs import field_catalog
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import NIGHTLY
from tests.conftest import REPO_ROOT

SITE_ROLLUPS = tomllib.loads((REPO_ROOT / "config" / "site" / "rollups.toml").read_text())
OWNERSHIP = tomllib.loads((REPO_ROOT / "architecture" / "ownership.toml").read_text())
TASK_MODULE = "apps/ingestion/algotrade_ingestion/tasks/derived/rollups.py"


@pytest.mark.parametrize("key", sorted(ROLLUPS))
def test_declaration_is_valid_and_typed(key: str) -> None:
    rollup = ROLLUPS[key]
    assert rollup.key == key and not declaration_problems(rollup)
    assert set(rollup.columns.values()) <= FIELD_TYPES
    module = Path(str(__import__(rollup.compute.__module__, fromlist=["x"]).__file__))
    assert module.parent == REPO_ROOT / "src" / "algotrade" / "features" / "rollups"


@pytest.mark.parametrize("key", sorted(ROLLUPS))
def test_params_have_a_site_section_or_none(key: str) -> None:
    has_params = ROLLUPS[key].params is not None
    assert (key in SITE_ROLLUPS) == has_params, (
        f"{key}: add a ['{key}'] section to config/site/rollups.toml"
        if has_params
        else f"{key} takes no parameters: remove its section"
    )


def test_site_rollups_toml_loads() -> None:
    rollup_params(SITE_ROLLUPS, {k: r.params for k, r in ROLLUPS.items()})


@pytest.mark.parametrize("key", sorted(ROLLUPS))
def test_inputs_have_loaders(key: str) -> None:
    missing = [i.table for i in ROLLUPS[key].inputs if i.table not in LOADERS]
    assert not missing, f"{key}: no loader in features/framework/inputs.py for {missing}"


@pytest.mark.parametrize("key", sorted(ROLLUPS))
def test_one_producer_the_rollups_task(key: str) -> None:
    table = ROLLUPS[key].table
    owners = [t["owner"] for t in OWNERSHIP["table"] if t["name"] == table]
    assert owners == [TASK_MODULE]
    assert table in TASKS["rollups"].tables


@pytest.mark.parametrize("key", sorted(ROLLUPS))
def test_reachable_from_the_catalogue(key: str) -> None:
    fields = field_catalog().fields
    for column, kind in ROLLUPS[key].columns.items():
        assert fields[f"rollup.{key}.{column}"] == kind


def test_nightly_computes_rollups_after_the_data_they_read() -> None:
    names = [s.name for s in NIGHTLY]
    for upstream in ("earnings", "bars", "corporate-actions", "chains"):
        assert names.index(upstream) < names.index("rollups")
    assert names.index("rollups") < names.index("screens")
