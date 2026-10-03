"""Fitness tests for the ingestion task registry (ADR 0019, "The ingest loop is written once").

- every registry task declares exactly the tables ``architecture/ownership.toml`` says its
  module produces (``owner`` or ``also_written_by``), and every producing task module is in
  the registry;
- every task is reachable from the CLI, by its own command and as ``run <task>``;
- every source a task names is declared in the source registry.
"""

import tomllib
from collections import defaultdict
from pathlib import Path

import pytest

from algotrade_ingestion import cli
from algotrade_ingestion.pipeline import NIGHTLY, SCREENS
from algotrade_ingestion.sources.registry import SOURCES
from algotrade_ingestion.tasks.registry import TASKS
from tests.conftest import REPO_ROOT

REGISTRY = tomllib.loads((REPO_ROOT / "architecture" / "ownership.toml").read_text())
TASKS_DIR = "apps/ingestion/algotrade_ingestion/tasks/"


def _module_path(module: object) -> str:
    return Path(str(getattr(module, "__file__", ""))).resolve().relative_to(REPO_ROOT).as_posix()


def _producers() -> dict[str, set[str]]:
    """module path -> concrete tables it produces per ownership.toml (wildcards excluded)."""
    out: dict[str, set[str]] = defaultdict(set)
    for table in REGISTRY["table"]:
        if "*" in table["name"]:
            continue
        for path in [table["owner"], *table.get("also_written_by", [])]:
            out[path].add(table["name"])
    return out


@pytest.mark.parametrize("name", sorted(TASKS))
def test_task_tables_match_the_ownership_registry(name: str) -> None:
    spec = TASKS[name]
    path = _module_path(spec.module)
    assert path.startswith(TASKS_DIR), f"{name}: tasks live in {TASKS_DIR}"
    assert set(spec.tables) == _producers().get(path, set()), (
        f"{name}: declared tables {sorted(spec.tables)} differ from ownership.toml "
        f"[[table]] entries for {path}"
    )


def test_every_producing_task_module_is_registered() -> None:
    registered = {_module_path(t.module) for t in TASKS.values()}
    producing = {p for p in _producers() if p.startswith(TASKS_DIR)}
    assert producing <= registered, f"not in tasks/registry.py: {sorted(producing - registered)}"


@pytest.mark.parametrize("name", sorted(TASKS))
def test_every_task_is_reachable_from_the_cli(name: str) -> None:
    parser = cli._parser()
    required = [f for p in TASKS[name].params if p.required for f in (p.flags[0], "x")]
    assert parser.parse_args(["run", name, *required]).task == name
    command = "golden" if name == "golden-load" else name
    args = ["golden", "load"] if name == "golden-load" else [command, *required]
    parsed = parser.parse_args(args)
    assert parsed.command == command


def test_every_declared_source_can_be_built() -> None:
    names = {s for t in TASKS.values() for s in (*t.sources, *t.optional_sources)}
    assert names <= set(SOURCES), sorted(names - set(SOURCES))


def test_nightly_is_an_ordered_list_of_registry_tasks() -> None:
    assert [n for n in NIGHTLY if n != SCREENS and n not in TASKS] == []
    assert len(set(NIGHTLY)) == len(NIGHTLY)
