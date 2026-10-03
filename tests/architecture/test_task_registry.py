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

from algotrade_ingestion.cli import main as cli
from algotrade_ingestion.sources.framework.registry import FIXTURES, SOURCES
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import FINALLY, NIGHTLY, SCREENS
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
    assert producing <= registered, (
        f"not in tasks/framework/registry.py: {sorted(producing - registered)}"
    )


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
    known = {*SOURCES, *FIXTURES}
    assert names <= known, sorted(names - known)


def test_nightly_is_an_ordered_list_of_registry_tasks() -> None:
    names = [s.name for s in (*NIGHTLY, *FINALLY)]
    assert [n for n in names if n != SCREENS and n not in TASKS] == []
    assert len(set(names)) == len(names)
    assert NIGHTLY[-1].name == "quality" and [s.name for s in FINALLY] == ["purge-raw"]
    for step in NIGHTLY:
        assert set(step.blocked_by) <= set(names[: names.index(step.name)]), step.name


def test_every_nightly_step_has_a_status_in_the_result() -> None:
    from datetime import date  # noqa: PLC0415

    from algotrade.storage.backends.memory import MemoryBackend  # noqa: PLC0415
    from algotrade.storage.tables.writers import StoreWriter  # noqa: PLC0415
    from algotrade_ingestion.workflows.nightly.nightly import run_nightly  # noqa: PLC0415
    from algotrade_ingestion.workflows.nightly.sessions import Plan  # noqa: PLC0415
    from tests.helpers.ingest_fakes import task_ctx  # noqa: PLC0415

    summary = run_nightly(task_ctx(StoreWriter(MemoryBackend())), Plan([date(2026, 10, 2)]))
    steps = summary["runs"][0]["steps"]
    assert list(steps) == [s.name for s in NIGHTLY]
    assert list(summary["steps"]) == [s.name for s in FINALLY]
    for step in [*steps.values(), *summary["steps"].values()]:
        assert step["status"] in ("COMPLETE", "PARTIAL", "FAILED", "SKIPPED", "BLOCKED")
        assert "duration_s" in step
