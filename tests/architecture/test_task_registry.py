"""Fitness tests for the ingestion task registry (ADR 0019, "The ingest loop is written once").

- every registry task declares exactly the tables ``architecture/tables.toml`` says its
  module produces (``owner`` or ``also_written_by``), and every producing task module is in
  the registry;
- every task is reachable from the CLI, by its own command and as ``run <task>``;
- every source a task names is declared in the source registry;
- every ``events/*`` table's spec requires a non-null ``known_from`` (ADR 0050 decision 3), or
  the table is a fact of record (``data.events.FACTS_OF_RECORD``) listed with its reason.
"""

import tomllib
from collections import defaultdict
from pathlib import Path

import pytest

from algotrade.data.events import FACTS_OF_RECORD
from algotrade.storage.tables.schemas import KNOWN_FROM, spec_for
from algotrade_ingestion.cli import main as cli
from algotrade_ingestion.tasks.framework.registry import TASKS
from algotrade_ingestion.workflows.nightly.nightly import FINALLY, NIGHTLY, SCREENS
from algotrade_sources.framework.registry import FIXTURES, SESSION_SOURCES, SOURCES
from tests.conftest import REPO_ROOT

TABLES = tomllib.loads((REPO_ROOT / "architecture" / "tables.toml").read_text())["table"]
TASKS_DIR = "apps/ingestion/algotrade_ingestion/tasks/"
# The event tables read without a knowledge bound and stored without ``known_from``, with the
# reason (``data.events.FACTS_OF_RECORD``). Every other event table requires ``known_from``.
FACTS_OF_RECORD_REASONS = {
    "events/split": "applied to bars at read time (ADR 0016): read by event date, unbounded",
    "events/dividend": "applied to bars at read time (ADR 0016), as events/split",
    "events/reference_change": "the diff of two reference snapshots: a fact of record of the "
    "listing, read by event date",
    "events/index_change": "the diff of two reference snapshots (S&P 500 membership), as "
    "events/reference_change",
}


def _module_path(module: object) -> str:
    return Path(str(getattr(module, "__file__", ""))).resolve().relative_to(REPO_ROOT).as_posix()


def _producers() -> dict[str, set[str]]:
    """module path -> concrete tables it produces per tables.toml (wildcards excluded)."""
    out: dict[str, set[str]] = defaultdict(set)
    for table in TABLES:
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
        f"{name}: declared tables {sorted(spec.tables)} differ from tables.toml "
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
    known = {*SOURCES, *SESSION_SOURCES, *FIXTURES}
    assert names <= known, sorted(names - known)


def test_nightly_is_an_ordered_list_of_registry_tasks() -> None:
    names = [s.name for s in (*NIGHTLY, *FINALLY)]
    assert [n for n in names if n != SCREENS and n not in TASKS] == []
    assert len(set(names)) == len(names)
    assert [s.name for s in FINALLY] == ["purge-raw"]
    for step in NIGHTLY:  # a step needs only steps declared before it (ADR 0039)
        assert set(step.needs) <= set(names[: names.index(step.name)]), step.name


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
        assert step["status"] in ("SUCCEEDED", "FAILED", "NOT_RUN", "SKIPPED", "WAIVED")
        assert "duration_s" in step and isinstance(step["critical"], bool)


EVENT_TABLES = sorted(t["name"] for t in TABLES if t["name"].startswith("events/"))


@pytest.mark.parametrize("table", EVENT_TABLES)
def test_every_event_table_requires_known_from_or_is_a_fact_of_record(table: str) -> None:
    spec = spec_for(table)
    if table in FACTS_OF_RECORD:
        assert table in FACTS_OF_RECORD_REASONS, f"{table}: give the reason it is unbounded"
        return
    column = spec.column(KNOWN_FROM)
    assert KNOWN_FROM in spec.required and column is not None and not column.nullable, (
        f"{table} must require a non-null known_from (ADR 0050 decision 3): declare its "
        "TableSpec in storage/tables/schemas.py like EARNINGS_EVENTS"
    )


def test_the_facts_of_record_are_the_listed_stored_tables() -> None:
    assert set(FACTS_OF_RECORD) == set(FACTS_OF_RECORD_REASONS)
    assert set(FACTS_OF_RECORD) <= set(EVENT_TABLES)
